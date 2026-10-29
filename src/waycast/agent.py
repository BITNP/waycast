"""The Agent: builds a LangChain v1 create_agent with structured output,
multi-round tool calling, and routing of output units to registered output
modules.  It also carries previous output results into the state of the next
invocation.
"""
from __future__ import annotations

from typing import Annotated, Any

from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentState
from langchain.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from waycast.blocks import results_as_message
from waycast.protocols import ModuleRegistry, OutputUnit, UnifiedInput
from waycast.state import OutputResult, OutputResultState
from waycast.tools import default_tools
from typing_extensions import NotRequired, Required, TypedDict


class AgentOutput(BaseModel):
    """Structured output the Agent must produce: a list of output units.

    The list may be empty (do nothing).  Each unit targets a registered
    output module and carries a payload matching that module's schema.
    """

    units: list[OutputUnit] = Field(default_factory=list)


class WaycastAgentState(AgentState[AgentOutput]):
    """AgentState extended with the global output-results feed."""

    messages: Required[Annotated[list, add_messages]]
    structured_response: NotRequired[AgentOutput]
    output_results: NotRequired[dict[str, Any]]


def _make_checkpointer() -> InMemorySaver:
    """In-memory checkpointer whose msgpack serializer allows AgentOutput."""
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[("waycast.agent", "AgentOutput")]
    )
    return InMemorySaver(serde=serde)


class InvocationResult(BaseModel):
    """Everything one invocation produced, returned to the caller."""

    input: UnifiedInput | None = None
    units: list[OutputUnit] = Field(default_factory=list)
    results: list[OutputResult] = Field(default_factory=list)
    structured: AgentOutput | dict[str, Any] | None = None


SYSTEM_PROMPT_TEMPLATE = """You are the Waycast agent.  You receive one unified input at a time.
You may call tools over multiple rounds to gather what you need.
Your final answer must be the structured output describing which output
modules to deliver, and with what payload.

Available output modules and the JSON schema each accepts:
{output_module_catalog}

Rules:
- Emit an empty units list when there is nothing to do.
- Each unit must target exactly one registered module name.
- Never invent a module name or payload field that the schema forbids.
"""


def _build_system_prompt(
    registry: ModuleRegistry,
    user_system_prompt: str | None = None,
) -> str:
    """Build the system prompt: user instructions (if any) plus the
    auto-generated catalog and rules.
    """
    from waycast.prompt_config import build_system_prompt_with_user

    catalog = registry.describe_output_modules()
    return build_system_prompt_with_user(catalog, user_system_prompt)


class Agent:
    """A Waycast agent: registry + LangChain agent + routing memory."""

    def __init__(
        self,
        registry: ModuleRegistry,
        model: Any,
        *,
        tools: list[Any] | None = None,
        checkpointer: Any | None = None,
        thread_id: str = "waycast-global",
        system_prompt: str | None = None,
        user_system_prompt: str | None = None,
    ) -> None:
        self.registry = registry
        self.model = model
        self.tools = tools if tools is not None else default_tools()
        self.checkpointer = checkpointer or _make_checkpointer()
        self.thread_id = thread_id
        self._output_results = OutputResultState()
        prompt = system_prompt or _build_system_prompt(
            registry, user_system_prompt=user_system_prompt
        )
        self.langchain_agent = create_agent(
            model=model,
            tools=self.tools,
            system_prompt=prompt,
            response_format=AgentOutput,
            state_schema=WaycastAgentState,
            checkpointer=self.checkpointer,
        )

    @property
    def pending_output_results(self) -> OutputResultState:
        return self._output_results

    def _config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self.thread_id}}

    def remember_output_result(self, r: OutputResult) -> None:
        """Record an output result to feed the next invocation."""
        self._output_results.add(r)

    def _prepare(self, inp: UnifiedInput) -> dict[str, Any]:
        """Build the graph input for one invocation."""
        messages = [SystemMessage(content=inp.content)]
        pending = results_as_message(self._output_results)
        if pending is not None:
            messages.append(pending)
        return {"messages": messages, "output_results": self._output_results.model_dump()}

    def _finish(self, structured: Any, inp: UnifiedInput) -> InvocationResult:
        """Turn the model's structured response into dispatched units."""
        stored = (
            structured.model_dump()
            if isinstance(structured, AgentOutput)
            else structured
        )
        result = InvocationResult(input=inp, structured=stored)
        if structured is None:
            return result
        if isinstance(structured, AgentOutput):
            units = structured.units
        else:
            units = AgentOutput.model_validate(structured).units
        for unit in units:
            result.units.append(unit)
            result.results.append(self._dispatch_unit(unit))
        return result

    def invoke(self, inp: UnifiedInput) -> InvocationResult:
        """Run one invocation synchronously (blocking)."""
        state = self.langchain_agent.invoke(
            self._prepare(inp), config=self._config()
        )
        return self._finish(state.get("structured_response"), inp)

    async def ainvoke(self, inp: UnifiedInput) -> InvocationResult:
        """Run one invocation asynchronously (non-blocking)."""
        state = await self.langchain_agent.ainvoke(
            self._prepare(inp),
            config=self._config(),
        )
        return self._finish(state.get("structured_response"), inp)

    def _dispatch_unit(self, unit: OutputUnit) -> OutputResult:
        """Send one unit to its output module; remember the result.

        Unknown modules or schema-invalid payloads are degraded: the unit is
        dropped, and a failure OutputResult is remembered for the next round.
        Returns the OutputResult produced by the dispatch.
        """
        err: OutputResult
        try:
            mod = self.registry.get_output(unit.module)
        except Exception as exc:
            err = OutputResult(module=unit.module, status="error", detail=f"unknown module: {exc}")
            self.remember_output_result(err)
            return err
        try:
            schema = mod.output_schema
            payload = schema.model_validate(unit.payload)
        except Exception as exc:
            err = OutputResult(module=unit.module, status="error", detail=f"schema validation failed: {exc}")
            self.remember_output_result(err)
            return err
        try:
            out = mod.accept(payload.model_dump())
        except Exception as exc:
            err = OutputResult(module=unit.module, status="error", detail=f"accept failed: {exc}")
            self.remember_output_result(err)
            return err
        self.remember_output_result(out)
        return out


def build_agent(reg: ModuleRegistry, model: Any, **kwargs: Any) -> Agent:
    return Agent(registry=reg, model=model, **kwargs)


def run_invocation(agent: Agent, inp: UnifiedInput) -> InvocationResult:
    """Convenience: run one invocation on an Agent."""
    return agent.invoke(inp)


__all__ = [
    "Agent",
    "AgentOutput",
    "InvocationResult",
    "WaycastAgentState",
    "build_agent",
    "run_invocation",
]

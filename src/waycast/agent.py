"""The Agent: a hub-side LangChain agent over connected modules.

The Agent builds a LangChain v1 create_agent with structured output and
multi-round tool calling.  It does not hold a registry of in-process module
objects: modules are connected over the network (ADR-0008) and their
capabilities live in a CapabilityCatalog.  The CapabilityBridge middleware
rebuilds the system prompt every invocation from the live catalog (A20),
exposes per-module status tools (A15/A19), and routes output units through
the hub to the owning module connections.  Output results accumulate into
the next invocation (ADR-0002).
"""
from __future__ import annotations

from typing import Annotated, Any, Awaitable, Callable

from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentState
from langchain.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from waycast.blocks import results_as_message
from waycast.bridge import CapabilityBridge, DEFAULT_RULES
from waycast.capabilities import CapabilityCatalog
from waycast.protocols import OutputUnit, UnifiedInput
from waycast.state import OutputResult, OutputResultState
from typing_extensions import NotRequired, Required


class AgentOutput(BaseModel):
    """Structured output the Agent must produce: a list of output units.

    The list may be empty (do nothing).  Each unit targets a connected
    output module and carries a payload matching that module schema.
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


BASE_SYSTEM_PROMPT = """You are the Waycast agent.  You receive one unified input
at a time.  You may call tools over multiple rounds to gather what you need.
Your final answer must be the structured output describing which output modules
to deliver, and with what payload."""


class Agent:
    """A Waycast agent: capability catalog + LangChain agent + routing memory."""

    def __init__(
        self,
        catalog: CapabilityCatalog,
        model: Any,
        *args: Any,
        tools: list[Any] | None = None,
        checkpointer: Any | None = None,
        thread_id: str = "waycast-global",
        user_system_prompt: str | None = None,
        base_system_prompt: str | None = None,
    ) -> None:
        if args:
            raise TypeError("Agent() takes no positional args beyond catalog/model; use keywords")
        self.catalog = catalog
        self.model = model
        self.tools = tools if tools is not None else []
        self.checkpointer = checkpointer or _make_checkpointer()
        self.thread_id = thread_id
        self._output_results = OutputResultState()

        self.bridge = CapabilityBridge(
            catalog,
            user_system_prompt=user_system_prompt,
        )
        base = base_system_prompt or BASE_SYSTEM_PROMPT
        self.langchain_agent = create_agent(
            model=model,
            tools=self.tools,
            system_prompt=base,
            middleware=[self.bridge],
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

    def set_dispatch(self, fn: Callable[[str, dict[str, Any]], Any]) -> None:
        """Wire the sync unit-delivery callable (tests use a sync fake)."""
        self.bridge.set_dispatch(fn)

    def set_adispatch(self, fn: Callable[[str, dict[str, Any]], Awaitable[Any]]) -> None:
        """Wire the async unit-delivery callable (the hub dispatches
        output_unit frames and awaits the module's result frame)."""
        self.bridge.set_adispatch(fn)

    def set_status_query(self, fn: Callable[[str], Any]) -> None:
        """Wire the status-query callable (the hub sends status_query frames)."""
        self.bridge.set_status_query(fn)

    def _prepare(self, inp: UnifiedInput) -> dict[str, Any]:
        """Build the graph input for one invocation."""
        messages = [SystemMessage(content=inp.content)]
        pending = results_as_message(self._output_results)
        if pending is not None:
            messages.append(pending)
        return {"messages": messages, "output_results": self._output_results.model_dump()}

    def _normalize_units(self, structured: Any) -> list[OutputUnit]:
        if structured is None:
            return []
        if isinstance(structured, AgentOutput):
            return structured.units
        return AgentOutput.model_validate(structured).units

    def _finish(self, structured: Any, inp: UnifiedInput) -> InvocationResult:
        """Sync finish: dispatch units through the sync path."""
        stored = (
            structured.model_dump()
            if isinstance(structured, AgentOutput)
            else structured
        )
        result = InvocationResult(input=inp, structured=stored)
        for unit in self._normalize_units(structured):
            result.units.append(unit)
            out = self.bridge.dispatch_unit(unit)
            result.results.append(out)
            # Only remember errors here; the hub's result frame is the
            # single authoritative success path (ADR-0002) and is
            # accumulated by the service.
            if not out.ok:
                self.remember_output_result(out)
        return result

    def invoke(self, inp: UnifiedInput) -> InvocationResult:
        """Run one invocation synchronously (blocking)."""
        state = self.langchain_agent.invoke(self._prepare(inp), config=self._config())
        return self._finish(state.get("structured_response"), inp)

    async def _afinish(self, structured: Any, inp: UnifiedInput) -> InvocationResult:
        """Async finish: dispatch units through the async hub path."""
        stored = (
            structured.model_dump()
            if isinstance(structured, AgentOutput)
            else structured
        )
        result = InvocationResult(input=inp, structured=stored)
        for unit in self._normalize_units(structured):
            result.units.append(unit)
            out = await self.bridge.adispatch_unit(unit)
            result.results.append(out)
            if not out.ok:
                self.remember_output_result(out)
        return result

    async def ainvoke(self, inp: UnifiedInput) -> InvocationResult:
        """Run one invocation asynchronously (non-blocking)."""
        state = await self.langchain_agent.ainvoke(
            self._prepare(inp),
            config=self._config(),
        )
        return await self._afinish(state.get("structured_response"), inp)


def build_agent(catalog: CapabilityCatalog, model: Any, **kwargs: Any) -> Agent:
    return Agent(catalog=catalog, model=model, **kwargs)


def run_invocation(agent: Agent, inp: UnifiedInput) -> InvocationResult:
    """Convenience: run one invocation on an Agent."""
    return agent.invoke(inp)


__all__ = [
    "Agent",
    "AgentOutput",
    "BASE_SYSTEM_PROMPT",
    "DEFAULT_RULES",
    "InvocationResult",
    "WaycastAgentState",
    "build_agent",
    "run_invocation",
]

"""The Agent: a hub-side LangChain agent over connected modules.

The Agent builds a LangChain v1 create_agent with structured output and
multi-round tool calling.  It does not hold a registry of in-process module
objects: modules are connected over the network (ADR-0008) and their
capabilities live in a CapabilityCatalog.  The CapabilityBridge middleware
rebuilds the system prompt every invocation from the live catalog (A20) and
exposes per-module status tools (A15/A19).  The one-shot output-results
feed rides at the head of the next invocation's human message, once, and
ages out with the history (ADR-0002 / ADR-0014).  Output units are routed
through the hub to the owning module connections.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel, Field

from waycast.bridge import DEFAULT_RULES, CapabilityBridge
from waycast.capabilities import CapabilityCatalog
from waycast.protocols import OutputUnit, UnifiedInput
from waycast.state import OutputResult, OutputResultState, input_content_with_feed


class AgentOutput(BaseModel):
    """Structured output the Agent must produce: a list of output units.

    The list may be empty (do nothing).  Each unit targets a connected
    output module and carries a payload matching that module schema.
    """

    units: list[OutputUnit] = Field(default_factory=list)


# History control is the built-in SummarizationMiddleware's job (official
# LangChain wheel, no hand-rolled trimming): it compresses the global
# single-thread history (ADR-0005) when either bound is hit.  The token
# counter is approximate, so a message-count bound guards CJK-heavy chats
# where characters-per-token underestimates.
SUMMARIZE_TRIGGER = [("tokens", 60_000), ("messages", 240)]
SUMMARIZE_KEEP = ("messages", 40)


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
            raise TypeError(
                "Agent() takes no positional args beyond catalog/model; use keywords"
            )
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
            middleware=[
                self.bridge,
                SummarizationMiddleware(
                    model=model,
                    trigger=SUMMARIZE_TRIGGER,
                    keep=SUMMARIZE_KEEP,
                ),
            ],
            response_format=AgentOutput,
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

    def set_adispatch(
        self, fn: Callable[[str, dict[str, Any]], Awaitable[Any]]
    ) -> None:
        """Wire the async unit-delivery callable (the hub dispatches
        output_unit frames and awaits the module's result frame)."""
        self.bridge.set_adispatch(fn)

    def set_status_query(self, fn: Callable[[str], Any]) -> None:
        """Wire the status-query callable (the hub sends status_query frames)."""
        self.bridge.set_status_query(fn)

    def _prepare(self, inp: UnifiedInput, feed: list[OutputResult]) -> dict[str, Any]:
        """Build the graph input for one invocation.

        The unified input enters the conversation as a human message (the
        LangChain conversation convention) with the drained output-results
        feed mounted at its head: the feed is conversational evidence of the
        previous turn's deliveries, not an instruction, so it rides the user
        turn, never the system prompt (ADR-0014).
        """
        return {
            "messages": [
                HumanMessage(content=input_content_with_feed(feed, inp.content))
            ]
        }

    def _normalize_units(self, structured: Any) -> list[OutputUnit]:
        if structured is None:
            return []
        if isinstance(structured, AgentOutput):
            return structured.units
        return AgentOutput.model_validate(structured).units

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
        """Run one invocation asynchronously (non-blocking).

        Starts by draining the pending output-results feed and mounting it
        at the head of this invocation's human message: every result reaches
        exactly the next invocation, exactly once (ADR-0002 / ADR-0014).
        Results arriving while this invocation runs wait for the next one.
        """
        feed = self._output_results.drain()
        state = await self.langchain_agent.ainvoke(
            self._prepare(inp, feed),
            config=self._config(),
        )
        return await self._afinish(state.get("structured_response"), inp)


__all__ = [
    "BASE_SYSTEM_PROMPT",
    "DEFAULT_RULES",
    "Agent",
    "AgentOutput",
    "InvocationResult",
]

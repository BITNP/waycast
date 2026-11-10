"""The capability bridge: connects the Agent to connected modules.

This is the middleware through which the Agent sees and reaches modules
(A13):

- On every invocation it rebuilds the dynamic system prompt from
  ``[base prompt] + [user prompt] + [current capability catalog] +
  [status tools] + [default rules]`` (A20), so module joins/leaves are
  reflected immediately without rebuilding the agent graph.  The prompt
  carries no per-invocation output-results feed: the feed rides at the head
  of the next invocation's human message instead (ADR-0002 / ADR-0014), so
  between module joins/leaves the system prompt stays byte-identical.
- It exposes a per-module ``status_<module>`` tool for modules that opt in
  to status querying (A15/A19).  The tool is a plain LangChain tool whose
  implementation sends a status_query frame on the module's connection and
  awaits the status_result; status semantics are defined by the module.
  Execution happens through the ``wrap_tool_call`` interceptor because the
  tool is only registered at invocation time (runtime tool registration).
- Output units produced by the model are dispatched through the hub to the
  owning connection's ``output_unit`` frame; the module answers with a
  ``result`` frame that the hub accumulates for the next invocation
  (ADR-0002).

The bridge keeps the two tracks separate (A14): structured-output unit
dispatch stays the primary path, and tools (status query, real data tools)
remain a secondary tool-calling track.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from waycast.capabilities import CapabilityCatalog, ModuleEndpoint
from waycast.prompt_config import build_system_prompt_with_user
from waycast.state import OutputResult

LOGGER = logging.getLogger(__name__)


DEFAULT_RULES = """Rules:
- Emit an empty units list when there is nothing to do.
- Each unit must target exactly one connected module name.
- Never invent a module name or payload field that the schema forbids.
With the structured output, only describe which modules to deliver to and with
what payload; the system (not you) dispatches the units."""


def _extends(previous: list[Any], messages: list[Any]) -> bool:
    """True when ``messages`` replays exactly ``previous`` and then continues
    (identity or value equality), i.e. the conversation grew unrewritten."""
    if len(messages) < len(previous):
        return False
    return all(old is new or old == new for old, new in zip(previous, messages))


class CapabilityBridge(AgentMiddleware):
    """Middleware that injects the module catalog into the prompt and routes
    output units / status queries to connected modules."""

    def __init__(
        self,
        catalog: CapabilityCatalog,
        *,
        user_system_prompt: str | None = None,
        default_rules: str = DEFAULT_RULES,
        llm_log_messages: str = "incremental",
    ) -> None:
        super().__init__()
        self.catalog = catalog
        self.user_system_prompt = user_system_prompt
        self.default_rules = default_rules
        normalized_log_mode = llm_log_messages.strip().lower()
        if normalized_log_mode not in ("incremental", "full"):
            LOGGER.warning(
                "unknown llm_log_messages %r, falling back to 'incremental'",
                llm_log_messages,
            )
            normalized_log_mode = "incremental"
        self._log_full_messages = normalized_log_mode == "full"
        # The message list logged by the previous request, for incremental mode.
        self._logged_messages: list[Any] = []
        self._adispatch: (
            Callable[[str, dict[str, Any]], Awaitable[OutputResult]] | None
        ) = None
        self._status_query: Callable[[str], Awaitable[dict[str, Any] | None]] | None = (
            None
        )
        self._status_tool_impls: dict[str, Callable[[], Awaitable[str]]] = {}

    # -- wiring ----------------------------------------------------------

    def set_adispatch(
        self, adispatch: Callable[[str, dict[str, Any]], Awaitable[OutputResult]]
    ) -> None:
        """Wire the async unit-delivery callable (hub side)."""

        self._adispatch = adispatch

    def set_status_query(
        self, query: Callable[[str], Awaitable[dict[str, Any] | None]]
    ) -> None:
        """Wire the status-query callable (hub sends status_query, awaits result)."""

        self._status_query = query

    # -- prompt assembly (A20) -------------------------------------------

    def _build_prompt(self, base: str = "") -> str:
        """Assemble [base] + [user] + [catalog] + [status] + [rules]."""

        return build_system_prompt_with_user(
            self.user_system_prompt,
            base=base,
            catalog=self.catalog.describe_output_modules(),
            status=self.catalog.describe_status_tools(),
            rules=self.default_rules,
        )

    def _prompt_for(self, request: ModelRequest) -> str:
        base = ""
        if request.system_message is not None:
            content = request.system_message.content
            base = content if isinstance(content, str) else str(content)
        return self._build_prompt(base)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        updated = request.override(
            tools=[*request.tools, *self._status_tools()],
            system_message=SystemMessage(content=self._prompt_for(request)),
        )
        return handler(updated)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Async variant of wrap_model_call (used by create_agent under ainvoke)."""

        updated = request.override(
            tools=[*request.tools, *self._status_tools()],
            system_message=SystemMessage(content=self._prompt_for(request)),
        )
        self._log_request(updated)
        response = await handler(updated)
        self._log_response(response)
        return response

    # -- debugging logs ----------------------------------------------------

    def _log_request(self, request: ModelRequest) -> None:
        """Log what is sent to the model (system prompt is assembled per-call;
        keep the request log to the conversation, not the static prompt).

        The LLM API is stateless, so every request carries the whole history
        again.  In the default ``incremental`` mode only the messages the
        previous request did not already log are printed: repeating the whole
        history on every request made one old input look like many inputs
        (2026-11-10 实机日志复盘).  A request whose list does not extend the
        logged prefix (first request, summarization rewrite...) logs the full
        list again; ``full`` keeps the per-request full dump.
        """
        system_chars = (
            len(request.system_message.content)
            if request.system_message is not None
            else 0
        )
        LOGGER.debug(
            "llm request: model=%s messages=%d system_chars=%d tools=%s",
            getattr(request.model, "model_name", "?"),
            len(request.messages),
            system_chars,
            [getattr(t, "name", str(t)) for t in request.tools],
        )
        messages = list(request.messages)
        new_messages = messages
        if not self._log_full_messages and _extends(self._logged_messages, messages):
            new_messages = messages[len(self._logged_messages) :]
        self._logged_messages = messages
        for message in new_messages:
            LOGGER.debug("llm request message %s: %r", message.type, message.content)
        collapsed = len(messages) - len(new_messages)
        if collapsed:
            LOGGER.debug(
                "llm request: %d earlier message(s) unchanged "
                "(WAYCAST_LLM_LOG_MESSAGES=full logs all)",
                collapsed,
            )

    @staticmethod
    def _log_response(response: ModelResponse) -> None:
        for result in response.result:
            tool_calls = getattr(result, "tool_calls", None)
            if tool_calls:
                LOGGER.debug(
                    "llm response tool_calls: %s",
                    [(tc.get("name"), tc.get("args")) for tc in tool_calls],
                )
            LOGGER.debug("llm response %s: %r", result.type, result.content)
        if response.structured_response is not None:
            LOGGER.debug(
                "llm response structured: %s",
                json.dumps(
                    response.structured_response, ensure_ascii=False, default=str
                ),
            )

    # -- runtime status tools (A15/A19) ----------------------------------

    def _status_tools(self) -> list[Any]:
        return [self._make_status_tool(e) for e in self.catalog.status_tools()]

    def _make_status_tool(self, endpoint: ModuleEndpoint) -> Any:
        name = f"status_{endpoint.name}"
        description = (
            f"Query the current status of the '{endpoint.name}' module. "
            f"{endpoint.status_description}".strip()
        )

        async def _status() -> str:
            if self._status_query is None:
                return f"status tool for {endpoint.name} is not wired"
            result = await self._status_query(endpoint.name)
            if result is None:
                return f"module {endpoint.name!r} did not answer the status query"
            return json.dumps(result, ensure_ascii=False)

        impl = _status
        impl.__name__ = name
        self._status_tool_impls[name] = impl
        return tool(name, description=description)(impl)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Async interceptor for runtime-registered status tools (A15/A19)."""
        impl = self._status_tool_impls.get(request.tool_call["name"])
        if impl is None:
            return await handler(request)
        try:
            content = await impl()
        except Exception as exc:  # noqa: BLE001 - 注册工具可抛任意异常，统一转成工具结果文本，不得击穿 agent 循环
            content = f"status query for {request.tool_call['name']!r} failed: {exc}"
        return ToolMessage(
            content=content,
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
        )

    async def adispatch_unit(self, unit: Any) -> OutputResult:
        """Route one output unit asynchronously; return the immediate outcome."""
        if self._adispatch is not None:
            return await self._adispatch(unit.module, unit.payload)
        return OutputResult(
            module=unit.module,
            status="error",
            detail="capability bridge is not wired to a hub connection",
        )


__all__ = ["DEFAULT_RULES", "CapabilityBridge"]

"""The capability bridge: connects the Agent to connected modules.

This is the middleware through which the Agent sees and reaches modules
(A13):

- On every invocation it rebuilds the dynamic system prompt from
  ``[base prompt] + [user prompt] + [current capability catalog] +
  [default rules]`` (A20), so module joins/leaves are reflected
  immediately without rebuilding the agent graph.
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

from waycast.capabilities import CapabilityCatalog, ModuleEndpoint
from waycast.prompt_config import build_system_prompt_with_user
from waycast.state import OutputResult


DEFAULT_RULES = """Rules:
- Emit an empty units list when there is nothing to do.
- Each unit must target exactly one connected module name.
- Never invent a module name or payload field that the schema forbids.
With the structured output, only describe which modules to deliver to and with
what payload; the system (not you) dispatches the units."""


class CapabilityBridge(AgentMiddleware):
    """Middleware that injects the module catalog into the prompt and routes
    output units / status queries to connected modules."""

    def __init__(
        self,
        catalog: CapabilityCatalog,
        *,
        user_system_prompt: str | None = None,
        default_rules: str = DEFAULT_RULES,
    ) -> None:
        super().__init__()
        self.catalog = catalog
        self.user_system_prompt = user_system_prompt
        self.default_rules = default_rules
        self._adispatch: Callable[
            [str, dict[str, Any]], Awaitable[OutputResult]
        ] | None = None
        self._status_query: (
            Callable[[str], Awaitable[dict[str, Any] | None]] | None
        ) = None
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
        return await handler(updated)

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
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        """Async interceptor for runtime-registered status tools (A15/A19)."""
        impl = self._status_tool_impls.get(request.tool_call["name"])
        if impl is None:
            return await handler(request)
        try:
            content = await impl()
        except Exception as exc:
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


__all__ = ["CapabilityBridge", "DEFAULT_RULES"]

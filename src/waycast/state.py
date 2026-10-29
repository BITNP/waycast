"""Agent state: output results, memory hops, and the unified state carrier.
The user chose global single-state memory (ADR-0005): there is no session or
per-source isolation; every invocation appends to one shared conversation
history and one shared feed of output results, because inputs are processed
one at a time by a single consumer.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, Field


class OutputResult(BaseModel):
    """The immediate value an output module returns after accepting a unit.

    status is one of "ok" | "error"; detail carries a textual summary.
    This result is carried into the state of the next invocation.
    """

    module: str
    status: str = "ok"
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class OutputResultState(BaseModel):
    """Cumulative, global collection of output results fed to the next invocation."""

    results: list[OutputResult] = Field(default_factory=list)

    def add(self, r: OutputResult) -> None:
        self.results.append(r)

    def as_memory_text(self) -> str:
        """Render the pending results as prose for the Agent prompt."""
        if not self.results:
            return ""
        lines = ["Output module results from previous deliveries:"]
        for r in self.results:
            lines.append(f"- {r.module}: {r.status} {r.detail}".strip())
        return "\n".join(lines)


MemoryHop = list[OutputResult]
"""Alias: a hop is one invocation's worth of output results."""


def build_state(*, messages: list[Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Build the LangGraph agent state dict.

    The state carries ``messages`` (conversation history) plus a global
    ``output_results`` field holding cumulative OutputResultState.
    """
    state: dict[str, Any] = {}
    if messages is not None:
        state["messages"] = list(messages)
    else:
        state["messages"] = []
    state["output_results"] = kwargs.get("output_results", OutputResultState())
    return state

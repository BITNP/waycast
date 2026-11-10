"""Agent state: output results, memory hops, and the unified state carrier.
The user chose global single-state memory (ADR-0005): there is no session or
per-source isolation; every invocation appends to one shared conversation
history and shares one feed of output results, because inputs are processed
one at a time by a single consumer.

The output-results feed is one-shot: each invocation drains the feed at its
start and mounts the drained results at the head of its own human message
exactly once (ADR-0002 / ADR-0014); results arriving while an invocation
runs wait for the invocation after it.  Each result therefore appears once
in the conversation history and ages out through summarization - never a
re-rendered cumulative snapshot (that was the bug fixed by ADR-0013).
"""
from __future__ import annotations
from collections import Counter
from pydantic import BaseModel, Field


class OutputResult(BaseModel):
    """The immediate value an output module returns after accepting a unit.

    status is one of "ok" | "error"; detail carries a textual summary.
    The result is delivered to the next invocation exactly once, riding at
    the head of that invocation's input message.
    """

    module: str
    status: str = "ok"
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class OutputResultState(BaseModel):
    """Feed of output results waiting to be delivered to the next invocation."""

    results: list[OutputResult] = Field(default_factory=list)

    def add(self, r: OutputResult) -> None:
        self.results.append(r)

    def drain(self) -> list[OutputResult]:
        """Take everything pending; the feed is empty until new results land."""
        drained = self.results
        self.results = []
        return drained


def results_as_text(results: list[OutputResult]) -> str:
    """Render pending output results as prose for the Agent prompt.

    Identical results collapse into a single counted line so routine
    acknowledgements (e.g. "ok queued" x 26) stay one line (ADR-0013);
    errors keep their full verbatim detail.
    """
    if not results:
        return ""
    counts: Counter[tuple[str, str, str]] = Counter(
        (r.module, r.status, r.detail) for r in results
    )
    lines = ["Output module results from previous deliveries:"]
    for (module, status, detail), n in counts.items():
        line = f"- {module}: {status} {detail}".strip()
        lines.append(f"{line} (x{n})" if n > 1 else line)
    return "\n".join(lines)


def input_content_with_feed(results: list[OutputResult], content: str) -> str:
    """Compose one invocation's human-message content.

    The drained output-results feed rides at the head of the newest unified
    input, separated by a blank line (ADR-0014); an empty feed leaves the
    content untouched.
    """
    feed = results_as_text(results)
    return f"{feed}\n\n{content}" if feed else content


__all__ = [
    "OutputResult",
    "OutputResultState",
    "input_content_with_feed",
    "results_as_text",
]

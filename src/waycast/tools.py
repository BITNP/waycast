"""Built-in production tools for the Agent.

Only tools backed by a real, non-mocked implementation live here.  Demo or
test-only placeholder tools (weather lookups against mock data, in-process
notification blobs, URL bookkeeping, ...) live in ``tests/demo_tools.py`` so
production code stays free of stubs (see AGENTS.md: no placeholders).
"""
from __future__ import annotations

import time
from typing import Any

from langchain_core.tools import tool


@tool
def get_time() -> str:
    """Return the current UTC time. Use when the user asks about time or dates."""
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def default_tools() -> list[Any]:
    """The production tool set, ready to pass to create_agent."""
    return [get_time]


__all__ = [
    "default_tools",
    "get_time",
]

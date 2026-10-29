"""Message building blocks used by Waycast agents.

We keep this minimal: right now we need a way to attach pending output
results to the conversation for the next invocation.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage

from waycast.state import OutputResultState


class BlockError(RuntimeError):
    """Raised when a message block cannot be built."""


class TextBlock:
    """A plain text content block."""

    def __init__(self, text: str) -> None:
        if not isinstance(text, str):
            raise BlockError(f"TextBlock expects str, got {type(text)!r}")
        self.text = text

    def to_block(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


class ExpressionBlock:
    """A structured JSON block for machine-verifiable data in a message."""

    def __init__(self, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise BlockError(f"ExpressionBlock expects dict, got {type(data)!r}")
        self.data = data

    def to_block(self) -> dict[str, Any]:
        return {"type": "json", "data": self.data}


def results_as_message(results: OutputResultState) -> SystemMessage | None:
    """Turn the pending output results into a message for the model.

    Returns None when there is nothing to say.  The message is a SystemMessage
    carrying the prose of the results so the LLM sees what happened to its
    previous deliveries on the next invocation.
    """
    text = results.as_memory_text()
    if not text:
        return None
    return SystemMessage(content=text)


__all__ = [
    "BlockError",
    "TextBlock",
    "ExpressionBlock",
    "results_as_message",
]

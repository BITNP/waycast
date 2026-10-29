"""Message building blocks used by Waycast agents.

We keep this minimal: right now we need a way to attach pending output
results to the conversation for the next invocation.
"""
from __future__ import annotations

from langchain_core.messages import SystemMessage

from waycast.state import OutputResultState


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


__all__ = ["results_as_message"]

"""Shared fixtures: a fake chat model that supports the structured-output
tool-calling loop used by Waycast agents."""

from __future__ import annotations

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeAgentChat(BaseChatModel):
    """A chat model that answers every agent loop with a structured-output
    tool call describing which units to dispatch."""

    units: list[dict] = []

    @property
    def _llm_type(self) -> str:
        return "fake-agent-chat"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        ai = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "AgentOutput",
                    "args": {"units": self.units},
                    "id": "call_fake",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=ai)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@pytest.fixture
def fake_chat():
    return FakeAgentChat()

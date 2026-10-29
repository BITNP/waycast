"""A minimal uvicorn server for smoke-testing the real lifespan path.

Run: PYTHONPATH=src .venv/bin/python tests/fake_server.py
Assumes WAYCAST_BASE_URL / WAYCAST_API_KEY are set (or uses a fake model).
"""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from waycast.agent import Agent
from waycast.modules import (
    HttpInputModule,
    MemoryLogOutputModule,
    NotifyOutputModule,
)
from waycast.protocols import ModuleRegistry
from waycast.service import Service


class FakeChat(BaseChatModel):
    """Emits a notify unit for every input, so smoke tests exercise dispatch."""

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "AgentOutput",
                                "args": {
                                    "units": [
                                        {
                                            "module": "notify",
                                            "payload": {
                                                "message": "via http",
                                                "level": "info",
                                            },
                                        }
                                    ]
                                },
                                "id": "c1",
                            }
                        ],
                    )
                )
            ]
        )

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def build_app():
    reg = ModuleRegistry()
    reg.register_input(HttpInputModule())
    reg.register_output(NotifyOutputModule())
    reg.register_output(MemoryLogOutputModule())
    agent = Agent(registry=reg, model=FakeChat(), tools=[])
    svc = Service(agent=agent, registry=reg, queue_size=10)
    return svc.app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WAYCAST_PORT", "8765"))
    uvicorn.run(build_app(), host="127.0.0.1", port=port, log_level="warning")

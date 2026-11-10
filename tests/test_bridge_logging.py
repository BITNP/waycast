"""Request-message DEBUG logging is incremental by default.

The LLM API is stateless: every request replays the whole history, so a
per-request full dump repeats one old input on every later request and reads
as if the same input arrived many times (2026-11-10 实机日志复盘).  Default
mode logs only the messages the previous request did not already log;
``full`` keeps the old dump.  Logging is route-layer and stays offline per
AGENTS.md; messages are real langchain message objects, not fakes.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from waycast.bridge import CapabilityBridge
from waycast.capabilities import CapabilityCatalog


def _bridge(mode: str = "incremental") -> CapabilityBridge:
    return CapabilityBridge(CapabilityCatalog(), llm_log_messages=mode)


def _request(messages: list[Any]) -> Any:
    return SimpleNamespace(model=None, messages=messages, system_message=None, tools=[])


def _logged_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    prefix = "llm request message "
    return [
        r.message.removeprefix(prefix)
        for r in caplog.records
        if r.message.startswith(prefix)
    ]


def _logged_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.message for r in caplog.records if r.name == "waycast.bridge"]


def test_default_logs_only_messages_new_since_last_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = _bridge()
    greeting = HumanMessage(content="你好")
    answer = AIMessage(content="很高兴见到你")
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        bridge._log_request(_request([greeting]))
        assert _logged_messages(caplog) == ["human: '你好'"]
        caplog.clear()
        # Second request replays the history plus the round's ai/tool messages.
        bridge._log_request(
            _request([greeting, answer, ToolMessage("ok", tool_call_id="1")])
        )
    assert _logged_messages(caplog) == ["ai: '很高兴见到你'", "tool: 'ok'"]
    assert any(
        "1 earlier message(s) unchanged" in line for line in _logged_lines(caplog)
    )


def test_full_mode_relogs_the_whole_history_every_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = _bridge("full")
    greeting = HumanMessage(content="你好")
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        bridge._log_request(_request([greeting]))
        caplog.clear()
        bridge._log_request(_request([greeting, AIMessage(content="你好！")]))
    assert _logged_messages(caplog) == ["human: '你好'", "ai: '你好！'"]


def test_rewritten_history_prefix_falls_back_to_full_dump(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # SummarizationMiddleware replaces the head with a summary: the logged
    # prefix no longer matches, so everything is dumped again once.
    bridge = _bridge()
    old = [HumanMessage(content=f"m{i}") for i in range(3)]
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        bridge._log_request(_request(old))
        caplog.clear()
        summarized = [HumanMessage(content="<summary>"), old[2]]
        bridge._log_request(_request(summarized))
    assert _logged_messages(caplog) == ["human: '<summary>'", "human: 'm2'"]


def test_unknown_mode_warns_and_falls_back_to_incremental(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        bridge = _bridge("everythign")
    assert any(
        "falling back to 'incremental'" in line for line in _logged_lines(caplog)
    )
    greeting = HumanMessage(content="你好")
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        bridge._log_request(_request([greeting]))
        caplog.clear()
        bridge._log_request(_request([greeting, AIMessage(content="你好！")]))
    assert _logged_messages(caplog) == ["ai: '你好！'"]

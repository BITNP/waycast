"""Request-message DEBUG logging is incremental by default.

The LLM API is stateless: every request replays the whole history, so a
per-request full dump repeats one old input on every later request and reads
as if the same input arrived many times (2026-11-10 实机日志复盘).  Default
mode logs only the messages the previous request did not already log;
``full`` keeps the old dump.  Response-side logging carries token usage so a
slow request can be attributed to provider-side thinking (reasoning tokens).
Logging is route-layer and stays offline per AGENTS.md; messages are real
langchain message objects, not fakes.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents.middleware import ModelResponse
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


def _usage_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    prefix = "llm response usage: "
    return [
        r.message
        for r in caplog.records
        if r.name == "waycast.bridge" and r.message.startswith(prefix)
    ]


def _totals_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    prefix = "llm usage totals: "
    return [
        r.message
        for r in caplog.records
        if r.name == "waycast.bridge" and r.message.startswith(prefix)
    ]


def test_response_usage_logs_reasoning_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A thinking-mode response must be attributable in the DEBUG log
    # (2026-11-10: 63.9s/85.7s LLM requests had no usage lines to explain them).
    thinking = AIMessage(
        content="",
        usage_metadata={
            "input_tokens": 900,
            "output_tokens": 4200,
            "total_tokens": 5100,
            "output_token_details": {"reasoning": 4100},
        },
        additional_kwargs={"reasoning_content": "x" * 50},
    )
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        _bridge()._log_response(
            ModelResponse(result=[thinking], structured_response=None)
        )
    assert _usage_lines(caplog) == [
        "llm response usage: in=900 out=4200 reasoning_tokens=4100 reasoning_chars=50"
    ]
    assert _totals_lines(caplog) == [
        "llm usage totals: calls=1 in=900 out=4200 reasoning=4100"
    ]


def test_response_usage_logs_cache_hit_rate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The prompt is replayed whole on every request; cache_read is the part
    # the provider's KV(prompt) cache actually served.
    cached = AIMessage(
        content="好的",
        usage_metadata={
            "input_tokens": 900,
            "output_tokens": 20,
            "total_tokens": 920,
            "input_token_details": {"cache_read": 832},
        },
    )
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        _bridge()._log_response(
            ModelResponse(result=[cached], structured_response=None)
        )
    assert _usage_lines(caplog) == [
        "llm response usage: in=900 out=20 cached=832 cache_hit=92.4%"
    ]
    expected_totals = (
        "llm usage totals: calls=1 in=900 out=20 reasoning=0 "
        "cache_hit=92.4% (832/900 prompt tokens)"
    )
    assert _totals_lines(caplog) == [expected_totals]


def test_response_usage_totals_accumulate_across_responses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = _bridge()

    def _message(in_tokens: int, out_tokens: int, cached: int | None) -> AIMessage:
        usage: dict[str, Any] = {
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": in_tokens + out_tokens,
        }
        if cached is not None:
            usage["input_token_details"] = {"cache_read": cached}
        return AIMessage(content="", usage_metadata=usage)  # type: ignore[arg-type]

    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        bridge._log_response(
            ModelResponse(result=[_message(1000, 10, 500)], structured_response=None)
        )
        caplog.clear()
        # A response without cache reporting still counts toward the token
        # totals but not the cache-rate denominator.
        bridge._log_response(
            ModelResponse(result=[_message(500, 5, None)], structured_response=None)
        )
    assert _usage_lines(caplog) == ["llm response usage: in=500 out=5"]
    expected_totals = (
        "llm usage totals: calls=2 in=1500 out=15 reasoning=0 "
        "cache_hit=50.0% (500/1000 prompt tokens)"
    )
    assert _totals_lines(caplog) == [expected_totals]


def test_response_usage_silent_when_provider_returns_no_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="waycast.bridge"):
        _bridge()._log_response(
            ModelResponse(result=[AIMessage(content="好的")], structured_response=None)
        )
    assert _usage_lines(caplog) == []
    assert _totals_lines(caplog) == []

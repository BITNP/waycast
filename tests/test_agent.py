"""End-to-end behavior of the Waycast Agent: unified input in, validated
units out, immediate output results feeding the next invocation."""

from __future__ import annotations

import asyncio

import pytest

from waycast.agent import Agent
from waycast.modules import (
    HttpInputModule,
    MemoryLogOutputModule,
    NotifyOutputModule,
    _echo_log,
    _notifications,
)
from waycast.protocols import (
    ModuleRegistry,
    UnifiedInput,
    WaycastError,
)


def build_registry() -> ModuleRegistry:
    reg = ModuleRegistry()
    reg.register_input(HttpInputModule())
    reg.register_output(NotifyOutputModule())
    reg.register_output(MemoryLogOutputModule())
    return reg


def test_registry_enforces_unique_names():
    reg = build_registry()
    with pytest.raises(WaycastError):
        reg.register_output(NotifyOutputModule())
    with pytest.raises(WaycastError):
        reg.register_input(HttpInputModule())


def test_system_prompt_includes_module_json_schemas(fake_chat):
    reg = build_registry()
    agent = Agent(registry=reg, model=fake_chat, tools=[])
    # catalog is embedded in the system prompt text
    from waycast.agent import _build_system_prompt

    catalog = _build_system_prompt(reg)
    assert '"title": "NotificationSchema"' in catalog
    assert '"required": ["message"]' in catalog
    assert "memory_log" in catalog
    assert "notify" in catalog


def test_invoke_dispatches_units_and_collects_results(fake_chat):
    _notifications.clear()
    _echo_log.clear()
    fake_chat.units = [
        {"module": "notify", "payload": {"message": "hello", "level": "info"}},
        {"module": "memory_log", "payload": {"text": "logged hello"}},
    ]
    agent = Agent(registry=build_registry(), model=fake_chat, tools=[])
    res = agent.invoke(UnifiedInput(content="go", source="http"))

    assert [u.module for u in res.units] == ["notify", "memory_log"]
    assert all(r.status == "ok" for r in res.results)
    assert _notifications == [{"message": "hello", "level": "info"}]
    assert _echo_log == [{"text": "logged hello", "tags": []}]
    assert [r.module for r in agent.pending_output_results.results] == [
        "notify",
        "memory_log",
    ]


def test_unknown_module_is_degraded_to_error_result(fake_chat):
    fake_chat.units = [{"module": "nope", "payload": {}}]
    agent = Agent(registry=build_registry(), model=fake_chat, tools=[])
    res = agent.invoke(UnifiedInput(content="go", source="http"))

    assert res.units[0].module == "nope"
    assert res.results[0].status == "error"
    assert "unknown" in res.results[0].detail
    assert res.results[0].module == "nope"


def test_schema_mismatch_is_degraded_to_error_result(fake_chat):
    # notify requires a string message; a number should fail validation.
    fake_chat.units = [{"module": "notify", "payload": {"message": 123}}]
    agent = Agent(registry=build_registry(), model=fake_chat, tools=[])
    res = agent.invoke(UnifiedInput(content="go", source="http"))

    assert res.results[0].status == "error"
    assert "validation failed" in res.results[0].detail


def test_empty_units_means_do_nothing(fake_chat):
    fake_chat.units = []
    agent = Agent(registry=build_registry(), model=fake_chat, tools=[])
    res = agent.invoke(UnifiedInput(content="nothing to do", source="http"))
    assert res.units == []
    assert res.results == []


def test_ainvoke_syncs_and_feeds_next_round(fake_chat):
    _notifications.clear()
    fake_chat.units = [
        {"module": "notify", "payload": {"message": "first", "level": "info"}}
    ]
    agent = Agent(registry=build_registry(), model=fake_chat, tools=[])
    res1 = asyncio.run(agent.ainvoke(UnifiedInput(content="one", source="http")))
    assert res1.results[0].status == "ok"

    # second invocation's model sees the previous results as a message
    fake_chat.units = [
        {"module": "notify", "payload": {"message": "second", "level": "info"}}
    ]
    res2 = asyncio.run(agent.ainvoke(UnifiedInput(content="two", source="http")))
    assert res2.results[0].status == "ok"
    assert _notifications == [
        {"message": "first", "level": "info"},
        {"message": "second", "level": "info"},
    ]
    # global memory: outputs accumulated across invocations
    assert len(agent.pending_output_results.results) == 2

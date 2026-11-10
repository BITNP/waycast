"""Offline tests for the one-shot output-results feed (ADR-0002 / ADR-0013).

Covers the state carrier (drain semantics), the prose renderer (aggregation),
and prompt assembly (the feed rides the dynamic system prompt, before the
rules, never as a conversation message).  Prompt assembly is route-layer and
stays offline per AGENTS.md; the end-to-end "model sees the failure" loop
stays covered by the real-model smoke in test_agent_real.py.
"""
from __future__ import annotations

from waycast.bridge import DEFAULT_RULES, CapabilityBridge
from waycast.capabilities import CapabilityCatalog
from waycast.state import OutputResult, OutputResultState, results_as_text


def test_results_as_text_renders_and_aggregates():
    assert results_as_text([]) == ""
    results = (
        [OutputResult(module="presenter", status="ok", detail="queued")] * 26
        + [OutputResult(module="presenter", status="error", detail="'nod' is not valid")]
        + [OutputResult(module="presenter", status="ok", detail="queued")]
    )
    text = results_as_text(results)
    assert "Output module results from previous deliveries:" in text
    assert "- presenter: ok queued (x27)" in text
    assert "- presenter: error 'nod' is not valid" in text
    # ok acknowledgements collapse; the 27th queued result joins the count
    assert text.count("- presenter: ok queued") == 1


def test_drain_delivers_everything_once():
    state = OutputResultState()
    state.add(OutputResult(module="m", status="error", detail="boom"))
    state.add(OutputResult(module="m", status="ok", detail="queued"))
    drained = state.drain()
    assert [r.detail for r in drained] == ["boom", "queued"]
    assert state.drain() == []
    state.add(OutputResult(module="m", status="ok", detail="queued"))
    assert len(state.drain()) == 1


def test_bridge_injects_feed_into_prompt_once():
    bridge = CapabilityBridge(CapabilityCatalog())
    assert "previous deliveries" not in bridge._build_prompt()

    bridge.begin_invocation([OutputResult(module="m", status="error", detail="boom")])
    prompt = bridge._build_prompt()
    assert "- m: error boom" in prompt
    # feed rides before the rules block; rules stay at the bottom
    assert prompt.index("previous deliveries") < prompt.index(DEFAULT_RULES.splitlines()[0])

    # the snapshot is stable across model calls and is replaced next invocation
    assert bridge._build_prompt() == prompt
    bridge.begin_invocation([])
    assert "previous deliveries" not in bridge._build_prompt()

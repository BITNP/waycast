"""Offline tests for the one-shot output-results feed (ADR-0002 / ADR-0014).

Covers the state carrier (drain semantics), the prose renderer (aggregation),
and message composition (the feed rides at the head of the next invocation's
human message, and the system prompt never carries it).  Composition is
route-layer and stays offline per AGENTS.md; the end-to-end "model sees the
failure" loop stays covered by the real-model smoke in test_agent_real.py.
"""

from __future__ import annotations

from waycast.bridge import CapabilityBridge
from waycast.capabilities import CapabilityCatalog
from waycast.state import (
    OutputResult,
    OutputResultState,
    input_content_with_feed,
    results_as_text,
)


def test_results_as_text_renders_and_aggregates():
    assert results_as_text([]) == ""
    results = (
        [OutputResult(module="presenter", status="ok", detail="queued")] * 26
        + [
            OutputResult(
                module="presenter", status="error", detail="'nod' is not valid"
            )
        ]
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


def test_feed_rides_at_head_of_input_message():
    assert input_content_with_feed([], "你好") == "你好"
    feed = [
        OutputResult(module="presenter", status="ok", detail="queued"),
        OutputResult(module="presenter", status="ok", detail="queued"),
        OutputResult(module="presenter", status="error", detail="boom"),
    ]
    content = input_content_with_feed(feed, "介绍一下北理工")
    assert content.startswith("Output module results from previous deliveries:")
    assert content.endswith("\n\n介绍一下北理工")
    assert "- presenter: ok queued (x2)" in content
    assert "- presenter: error boom" in content


def test_system_prompt_never_carries_the_feed():
    # the bridge no longer knows the feed at all (ADR-0014): whatever
    # results are pending, the system prompt stays the static assembly
    bridge = CapabilityBridge(CapabilityCatalog())
    assert "Output module results" not in bridge._build_prompt()

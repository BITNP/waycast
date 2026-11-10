"""Behavior of the demo/test-only placeholder tools.

These tools moved out of the production package (``waycast.tools``) because
they are mocked/demo stubs; they belong under tests so production code
carries no placeholders.
"""

from __future__ import annotations

import demo_tools


def test_echo_roundtrips():
    assert demo_tools.echo.invoke("hi") == "hi"


def test_look_up_weather_mock_data():
    assert "Sunny" in demo_tools.look_up_weather.invoke("beijing")
    assert "No data" in demo_tools.look_up_weather.invoke("atlantis")


def test_store_blob_records_in_demo_memory():
    demo_tools.blob_store.clear()
    assert demo_tools.store_blob.invoke({"key": "k", "value": "v"}) == "k"
    assert demo_tools.blob_store == {"k": "v"}


def test_notify_queues_message():
    demo_tools.notifications.clear()
    out = demo_tools.notify.invoke("hello")
    assert out.startswith("notification queued")
    assert demo_tools.notifications == [{"message": "hello", "level": "info"}]


def test_emit_seen_url_records():
    demo_tools.seen_urls.clear()
    out = demo_tools.emit_seen_url.invoke("https://example.com")
    assert out.startswith("recorded url")
    assert demo_tools.seen_urls == ["https://example.com"]


def test_demo_tools_returns_all():
    names = {t.name for t in demo_tools.demo_tools()}
    assert names == {"echo", "look_up_weather", "store_blob", "notify", "emit_seen_url"}

"""Demo/test-only placeholder tools.

These tools exist only to exercise the multi-round tool-calling loop in
tests and demos (mocked weather, in-process notifications, blob store,
URL bookkeeping).  They are intentionally not part of the production
package (``waycast.tools``), so production code carries no stubs.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


blob_store: dict[str, str] = {}
notifications: list[str] = []
seen_urls: list[str] = []


@tool
def echo(text: str) -> str:
    """Echo back exactly the given text."""
    return text


@tool
def look_up_weather(city: str) -> str:
    """Look up the current weather for a city (mocked demo data)."""
    mock: dict[str, str] = {
        "beijing": "Sunny, 22C",
        "shanghai": "Cloudy, 19C",
        "shenzhen": "Rain, 27C",
    }
    return mock.get(city.lower(), f"No data for {city!r}")


@tool
def store_blob(key: str, value: str) -> str:
    """Store a string blob under a key in demo memory. Returns the key."""
    blob_store[key] = value
    return key


@tool
def notify(message: str) -> str:
    """Send a demo notification with the given message."""
    notifications.append({"message": message, "level": "info"})
    return f"notification queued: {message!r}"


@tool
def emit_seen_url(url: str) -> str:
    """Record that we have visited/examined the given URL (demo)."""
    seen_urls.append(url)
    return f"recorded url: {url!r}"


def demo_tools() -> list[Any]:
    """All demo tools, ready to pass to create_agent."""
    return [echo, look_up_weather, store_blob, notify, emit_seen_url]


__all__ = [
    "demo_tools",
    "echo",
    "look_up_weather",
    "store_blob",
    "notify",
    "emit_seen_url",
    "blob_store",
    "notifications",
    "seen_urls",
]

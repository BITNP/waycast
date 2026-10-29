"""Built-in tools for the Agent: query-style and side-effect tools so the
multi-round tool-calling loop has something real to exercise.
"""
from __future__ import annotations

import time
from typing import Any

from langchain_core.tools import tool


@tool
def get_time() -> str:
    """Return the current UTC time. Use when the user asks about time or dates."""
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


@tool
def echo(text: str) -> str:
    """Echo back exactly the given text."""
    return text


@tool
def look_up_weather(city: str) -> str:
    """Look up the current weather for a city. Data is mocked for the demo."""
    mock: dict[str, str] = {
        "beijing": "Sunny, 22C",
        "shanghai": "Cloudy, 19C",
        "shenzhen": "Rain, 27C",
    }
    return mock.get(city.lower(), f"No data for {city!r}")


@tool
def store_blob(key: str, value: str) -> str:
    """Store a string blob under a key in demo memory. Returns the key."""
    from waycast.modules import _blob_store
    _blob_store[key] = value
    return key


@tool
def notify(message: str) -> str:
    """Send a notification with the given message. Side-effect tool for the demo."""
    from waycast.modules import NotificationSchema, _notifications
    _notifications.append(
        NotificationSchema(message=message, level="info").model_dump()
    )
    return f"notification queued: {message!r}"


@tool
def emit_seen_url(url: str) -> str:
    """Record that we have visited/examined the given URL. Side-effect tool."""
    from waycast.modules import _seen_urls
    _seen_urls.append(url)
    return f"recorded url: {url!r}"


def default_tools() -> list[Any]:
    """All built-in tools, ready to pass to create_agent."""
    return [get_time, echo, look_up_weather, store_blob, notify, emit_seen_url]


__all__ = [
    "default_tools",
    "get_time",
    "echo",
    "look_up_weather",
    "store_blob",
    "notify",
    "emit_seen_url",
]

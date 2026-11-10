"""Configuration: reads base URL + API key for the OpenAI Chat Completions
model from environment or a .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional at import time
    pass


@dataclass
class WaycastConfig:
    """Runtime configuration for the Waycast service."""

    base_url: str = ""
    api_key: str = ""
    model_name: str = "gpt-4o-mini"
    queue_size: int = 100
    host: str = "0.0.0.0"
    port: int = 8000
    thread_id: str = "waycast-global"

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.getenv("WAYCAST_BASE_URL", "")
            or os.getenv("OPENAI_BASE_URL", ""),
            api_key=os.getenv("WAYCAST_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""),
            model_name=os.getenv("WAYCAST_MODEL", "gpt-4o-mini"),
            queue_size=int(os.getenv("WAYCAST_QUEUE_SIZE", "100")),
            host=os.getenv("WAYCAST_HOST", "0.0.0.0"),
            port=int(os.getenv("WAYCAST_PORT", "8000")),
            thread_id=os.getenv("WAYCAST_THREAD_ID", "waycast-global"),
        )


def make_model(config: WaycastConfig, http_async_client=None):
    """Build a ChatOpenAI model pointed at config.base_url.

    Uses Chat Completions (the standard OpenAI-compatible path) with the
    user-supplied base URL and API key.  Raises if credentials are missing.

    ``http_async_client`` (optional) injects a pre-built httpx2.AsyncClient
    (openai SDK 3.x is built on httpx2);
    when omitted ChatOpenAI uses langchain_openai's process-cached default
    client (shared per base URL).  Callers that manage client lifetime
    themselves (e.g. tests that close their client per scenario) should pass
    their own client so closing it does not poison the shared cache.
    """
    from langchain_openai import ChatOpenAI

    if not config.base_url or not config.api_key:
        raise RuntimeError(
            "Missing OpenAI credentials: set WAYCAST_BASE_URL and WAYCAST_API_KEY"
            " (or OPENAI_BASE_URL / OPENAI_API_KEY)."
        )
    return ChatOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model_name,
        http_async_client=http_async_client,
    )


__all__ = ["WaycastConfig", "make_model"]

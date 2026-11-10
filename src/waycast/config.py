"""Configuration: reads base URL + API key for the OpenAI Chat Completions
model from environment or a .env file.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import httpx2
    from langchain_openai import ChatOpenAI

with contextlib.suppress(Exception):  # dotenv is optional at import time
    from dotenv import load_dotenv

    load_dotenv()


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
    # LLM 请求消息的 DEBUG 记录方式：incremental 只打相对上次请求新增的消息，
    # full 每次全量打（校验与回退在 CapabilityBridge，见 bridge.py）。
    llm_log_messages: str = "incremental"
    # 单次 LLM HTTP 请求超时与 SDK 重试次数。openai SDK 默认 600s×(1+2 retries)
    # 能把挂死的 provider 请求静默阻塞近半小时；收紧后失败快速进入
    # "agent invocation failed" 错误日志，worker 继续消费下一条输入。
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 1
    # 逐请求透传给 OpenAI 兼容端的额外 JSON 字段（openai SDK extra_body），
    # 用于 provider 专属开关。实测 maas.bit.edu.cn deepseek-v4-flash 默认开
    # 思考（reasoning_tokens 计入每次响应），置
    # {"reasoning_effort": "none"} 后 reasoning_tokens=0（2026-11-10 实测）。
    # 空 dict = 不发任何额外字段。
    llm_extra_body: dict[str, Any] = field(default_factory=dict)

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
            llm_log_messages=os.getenv("WAYCAST_LLM_LOG_MESSAGES", "incremental"),
            llm_timeout_seconds=float(
                os.getenv("WAYCAST_LLM_TIMEOUT", str(cls.llm_timeout_seconds))
            ),
            llm_max_retries=int(
                os.getenv("WAYCAST_LLM_MAX_RETRIES", str(cls.llm_max_retries))
            ),
            llm_extra_body=_parse_extra_body(os.getenv("WAYCAST_LLM_EXTRA_BODY", "")),
        )


def _parse_extra_body(raw: str) -> dict[str, Any]:
    """Parse WAYCAST_LLM_EXTRA_BODY (a JSON object) into the extra_body dict.

    Blank = no extra fields.  Anything that is not a JSON object is a config
    error and must fail loudly at startup rather than be silently dropped.
    """
    if not raw.strip():
        return {}
    parsed: Any = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError(
            "WAYCAST_LLM_EXTRA_BODY must be a JSON object, e.g."
            ' {"reasoning_effort": "none"}'
        )
    return cast("dict[str, Any]", parsed)


def make_model(
    config: WaycastConfig, http_async_client: httpx2.AsyncClient | None = None
) -> ChatOpenAI:
    """Build a ChatOpenAI model pointed at config.base_url.

    Uses Chat Completions (the standard OpenAI-compatible path) with the
    user-supplied base URL and API key.  Raises if credentials are missing.

    ``timeout`` / ``max_retries`` come from the config (fail fast on a stalled
    provider instead of the openai SDK default 600s × 3 attempts, which would
    silently block the invocation worker for up to ~30 minutes).  They apply
    to the client ChatOpenAI builds itself; an injected ``http_async_client``
    carries its own settings instead.

    ``http_async_client`` (optional) injects a pre-built httpx2.AsyncClient
    (openai SDK 3.x is built on httpx2);
    when omitted ChatOpenAI uses langchain_openai's process-cached default
    client (shared per base URL).  Callers that manage client lifetime
    themselves (e.g. tests that close their client per scenario) should pass
    their own client so closing it does not poison the shared cache.

    ``llm_extra_body`` (if non-empty) is forwarded as ``extra_body`` so every
    request carries provider-specific fields verbatim (e.g. disabling a
    provider-default thinking mode).
    """
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    if not config.base_url or not config.api_key:
        raise RuntimeError(
            "Missing OpenAI credentials: set WAYCAST_BASE_URL and WAYCAST_API_KEY"
            " (or OPENAI_BASE_URL / OPENAI_API_KEY)."
        )
    return ChatOpenAI(
        base_url=config.base_url,
        api_key=SecretStr(config.api_key),
        model=config.model_name,
        timeout=config.llm_timeout_seconds,
        max_retries=config.llm_max_retries,
        extra_body=config.llm_extra_body or None,
        http_async_client=http_async_client,
    )


__all__ = ["WaycastConfig", "make_model"]

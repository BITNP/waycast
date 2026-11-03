"""waycast command-line entry point.

  waycast serve   # start the WebSocket hub service (uvicorn)

Reads WAYCAST_BASE_URL / WAYCAST_API_KEY (or OPENAI_*) and WAYCAST_HUB_TOKEN
from the environment.
"""
from __future__ import annotations

import argparse
import logging
import os

import uvicorn

from waycast.agent import Agent
from waycast.capabilities import CapabilityCatalog
from waycast.config import WaycastConfig, make_model
from waycast.prompt_config import read_user_system_prompt
from waycast.service import Service
from waycast.tools import default_tools

# 第三方噪音源（LLM SDK、HTTP、WS、事件循环）默认钉在 WARNING，
# waycast 自己的 DEBUG 日志不受影响；WAYCAST_DEPS_LOG_LEVEL 可单独放开。
_THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "websockets", "openai", "asyncio", "urllib3")


def _configure_logging() -> str:
    """Configure first-party logging (WAYCAST_LOG_LEVEL, default INFO) and the
    dependency level (WAYCAST_DEPS_LOG_LEVEL, default WARNING).  Returns the
    dependency level so the caller can decide whether uvicorn keeps access logs."""
    level = os.getenv("WAYCAST_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    deps = os.getenv("WAYCAST_DEPS_LOG_LEVEL", "WARNING").strip().upper() or "WARNING"
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for name in _THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(deps)
    return deps


def _build_app(config: WaycastConfig):
    catalog = CapabilityCatalog()
    agent = Agent(
        catalog=catalog,
        model=make_model(config),
        tools=default_tools(),
        thread_id=config.thread_id,
        user_system_prompt=read_user_system_prompt(),
    )
    return Service(
        agent=agent,
        catalog=catalog,
        queue_size=config.queue_size,
        hub_token=os.getenv("WAYCAST_HUB_TOKEN", ""),
    ).app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="waycast")
    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="start the WebSocket hub service")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        config = WaycastConfig.from_env()
        if args.host:
            config.host = args.host
        if args.port:
            config.port = args.port
        deps_level = _configure_logging()
        app = _build_app(config)
        # 访问日志（每请求一行）属依赖级噪音：默认关闭，放开依赖级别时才出现。
        uvicorn.run(
            app,
            host=config.host,
            port=config.port,
            access_log=deps_level in ("INFO", "DEBUG"),
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

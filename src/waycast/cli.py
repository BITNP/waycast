"""waycast command-line entry point.

  waycast serve   # start the WebSocket hub service (uvicorn)

Reads WAYCAST_BASE_URL / WAYCAST_API_KEY (or OPENAI_*) and WAYCAST_HUB_TOKEN
from the environment.
"""
from __future__ import annotations

import argparse
import os

import uvicorn

from waycast.agent import Agent
from waycast.capabilities import CapabilityCatalog
from waycast.config import WaycastConfig, make_model
from waycast.prompt_config import read_user_system_prompt
from waycast.service import Service
from waycast.tools import default_tools


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
        app = _build_app(config)
        uvicorn.run(app, host=config.host, port=config.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

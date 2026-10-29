"""waycast command-line entry point.

  waycast serve   # start the HTTP service (uvicorn)

Uses WAYCAST_BASE_URL / WAYCAST_API_KEY (or OPENAI_*) from the environment.
"""
from __future__ import annotations

import argparse
import os

import uvicorn

from waycast.config import WaycastConfig
from waycast.demo import build_agent, build_registry, build_service


def _build_app(config: WaycastConfig):
    reg = build_registry()
    agent = build_agent(reg, config)
    service = build_service(reg, agent, config)
    return service.app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="waycast")
    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="start the HTTP service")
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

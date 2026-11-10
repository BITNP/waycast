"""Input-only reference module.

Connects, advertises an input-only capability, and pushes one unified input
every --interval seconds constructed from the current UTC time.  It
does not receive output_unit frames (kind=input), demonstrating a pure
input module.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

from waycast.wire import make_frame

from waycast_examples.client import connect_module


CAPABILITY = {
    "name": "cron_source",
    "kind": "input",
    "input": {"description": "emits the current UTC time every interval seconds"},
}


async def _run(args: argparse.Namespace) -> None:
    async with connect_module(
        hub_url=args.hub, token=args.token, capability=CAPABILITY
    ) as ws:
        while True:
            now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            print("cron_source tick: " + now, flush=True)
            await ws.send(
                make_frame(
                    "input",
                    "cron_source",
                    {"content": "tick " + now, "metadata": {"interval": args.interval}},
                ).model_dump_json()
            )
            await asyncio.sleep(args.interval)


def main() -> None:
    parser = argparse.ArgumentParser(prog="waycast-example-cron-source")
    parser.add_argument("--hub", default="ws://127.0.0.1:8000")
    parser.add_argument("--token", default="")
    parser.add_argument("--interval", type=float, default=60.0)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()

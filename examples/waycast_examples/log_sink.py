"""Output-only reference module (no status channel).

Demonstrates the minimal output module: connect, advertise an output-only
capability, handle output_unit frames, answer with result frames.  Because
it does not advertise a status channel, the hub creates no status tool for
it (A19) - an explicit demonstration that status is optional.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from waycast.wire import make_frame

from waycast_examples.client import connect_module


CAPABILITY = {
    "name": "log_sink",
    "kind": "output",
    "output": {
        "schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
            "required": ["text"],
            "additionalProperties": False,
        },
        "description": "append a structured log line to the local journal (log_sink)",
    },
}


async def _run(args: argparse.Namespace) -> None:
    async with connect_module(hub_url=args.hub, token=args.token, capability=CAPABILITY) as ws:
        async for raw in ws:
            frame = json.loads(raw)
            if frame["type"] != "output_unit":
                continue
            print("log_sink: " + json.dumps(frame["payload"], ensure_ascii=False), flush=True)
            await ws.send(
                make_frame("result", "log_sink", {"module": "log_sink", "status": "ok", "detail": "logged"}).model_dump_json()
            )


def main() -> None:
    parser = argparse.ArgumentParser(prog="waycast-example-log-sink")
    parser.add_argument("--hub", default="ws://127.0.0.1:8000")
    parser.add_argument("--token", default="")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()

"""Combined input+output reference module with an optional status channel.

This module demonstrates every frame type of the Wire protocol on one
multiplexed connection (A25):

- capability first frame, kind='both', with an optional status channel.
- input frames: the module reads lines from stdin and sends them to the
  hub as unified inputs.
- output_unit frames: the hub dispatches units here; the module echoes
  the payload to stdout and answers with a result frame.
- status_query / status_result: answers status queries with a small
  module-defined status document.

Run:

    PYTHONPATH=src:examples .venv/bin/python -m waycast_examples.echo_bell \
        --hub ws://127.0.0.1:8000 --token W
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from httpx2.websockets import WebSocketDisconnect

from waycast.wire import make_frame

from waycast_examples.client import connect_module


CAPABILITY = {
    "name": "echo_bell",
    "kind": "both",
    "input": {"description": "standard input lines of text"},
    "output": {
        "schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        "description": "echo a text payload to stdout (echo_bell)",
    },
    "status": {
        "enabled": True,
        "description": "echo_bell liveness and delivered-unit count",
    },
}


async def _reader(ws: Any) -> None:
    while True:
        line = await asyncio.to_thread(input, "echo_bell> ")
        await ws.send_text(
            make_frame("input", "echo_bell", {"content": line}).model_dump_json()
        )


async def _run(args: argparse.Namespace) -> None:
    async with connect_module(
        hub_url=args.hub, token=args.token, capability=CAPABILITY
    ) as ws:
        reader = asyncio.create_task(_reader(ws))
        count = 0
        try:
            while True:
                frame = json.loads(await ws.receive_text())
                if frame["type"] == "output_unit":
                    count += 1
                    print(
                        "unit #"
                        + str(count)
                        + ": "
                        + json.dumps(frame["payload"], ensure_ascii=False),
                        flush=True,
                    )
                    await ws.send_text(
                        make_frame(
                            "result",
                            "echo_bell",
                            {
                                "module": "echo_bell",
                                "status": "ok",
                                "detail": "echoed unit #" + str(count),
                            },
                        ).model_dump_json()
                    )
                elif frame["type"] == "status_query":
                    await ws.send_text(
                        make_frame(
                            "status_result",
                            "echo_bell",
                            {"state": "up", "delivered_units": count},
                            request_id=frame.get("request_id"),
                        ).model_dump_json()
                    )
        except WebSocketDisconnect:
            pass  # hub closed the connection: shut the module down
        reader.cancel()


def main() -> None:
    parser = argparse.ArgumentParser(prog="waycast-example-echo-bell")
    parser.add_argument("--hub", default="ws://127.0.0.1:8000")
    parser.add_argument("--token", default="")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()

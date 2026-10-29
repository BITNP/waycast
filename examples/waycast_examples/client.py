"""Shared WebSocket client helpers for reference modules.

A Waycast module is a WebSocket client that connects to the hub's
/ws/modules endpoint, presents its connection token, and sends a
capability advertisement as the very first frame (ADR-0008).  After that the
connection is full-duplex: every frame type travels over the same socket,
distinguished by the type field.

This module provides connect_module: a small context manager that handles
connect, token query param, capability handshake and the accept
acknowledgement, so each example module only implements its own frame
handling.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import websockets


@asynccontextmanager
async def connect_module(*, hub_url: str, token: str, capability: dict[str, Any],) -> AsyncIterator[Any]:
    """Connect to the hub and announce a capability.

    Yields the open websocket.  The caller is then free to send input,
    output_unit, result, status_query / status_result frames.
    """
    uri = hub_url.rstrip("/") + "/ws/modules" + (("?token=" + token) if token else "")
    async with websockets.connect(uri) as ws:
        frame = {"protocol_version": 1, "type": "capability", "module": capability["name"], "payload": capability}
        await ws.send(json.dumps(frame))
        ack_raw = json.loads(await ws.recv())
        if ack_raw.get("type") != "capability" or not ack_raw.get("payload", {}).get("accepted"):
            raise RuntimeError("hub did not accept capability: " + repr(ack_raw))
        yield ws

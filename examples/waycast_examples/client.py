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

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx2
from urllib.parse import urlencode, urlparse, urlunparse

from waycast.wire import make_frame, parse_frame


@asynccontextmanager
async def _open_ws(uri: str) -> AsyncIterator[Any]:
    """One hub connection: httpx2 client with an upgraded WebSocket session."""
    async with httpx2.AsyncClient() as http, http.websocket(uri) as ws:
        yield ws


@asynccontextmanager
async def connect_module(
    *,
    hub_url: str,
    token: str,
    capability: dict[str, Any],
) -> AsyncIterator[Any]:
    """Connect to the hub and announce a capability.

    Yields the open websocket (httpx2 WebSocketSession: send_text /
    receive_text).  The caller is then free to send input, output_unit,
    result, status_query / status_result frames.
    """
    parts = urlparse(hub_url.rstrip("/") + "/ws/modules")
    query = urlencode({"token": token}) if token else parts.query
    uri = urlunparse(parts._replace(query=query))
    async with _open_ws(uri) as ws:
        await ws.send_text(
            make_frame("capability", capability["name"], capability).model_dump_json()
        )
        ack = parse_frame(await ws.receive_text())
        if ack.type != "capability" or not ack.payload.get("accepted"):
            raise RuntimeError(
                "hub did not accept capability: " + ack.model_dump_json()
            )
        yield ws

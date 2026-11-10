"""Offline tests for the reference module client (examples/waycast_examples).

These exercise connect_module's capability handshake and URL construction
against a fake websocket (no network, no model).  The example modules
themselves are thin frame loops over connect_module; the wire format they
produce is covered here and in test_wire.py.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest
from waycast_examples.client import connect_module

from waycast.wire import parse_frame


class FakeWS:
    """In-memory websocket capturing what the client sends."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._acks: asyncio.Queue[str] = asyncio.Queue()

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return await asyncio.wait_for(self._acks.get(), timeout=5.0)


def _fake_connect(ws: FakeWS, captured: dict[str, str]):
    """Patched websockets.connect: record the URI, yield the fake ws."""
    import json
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory(uri: str, **kwargs: Any):
        captured["uri"] = uri
        # the hub's accept ack frame
        await ws._acks.put(
            json.dumps(
                {
                    "protocol_version": 1,
                    "type": "capability",
                    "module": "x",
                    "payload": {"accepted": True},
                }
            )
        )
        yield ws

    return factory


def test_connect_module_handshake_and_token_query(monkeypatch):
    from waycast_examples import client

    ws = FakeWS()
    captured: dict[str, str] = {}
    monkeypatch.setattr(client.websockets, "connect", _fake_connect(ws, captured))

    capability = {
        "name": "alert",
        "kind": "output",
        "output": {"schema": {"type": "object"}, "description": "send alerts"},
    }

    async def scenario():
        async with connect_module(
            hub_url="ws://127.0.0.1:8000", token="tok", capability=capability
        ) as ws_:
            assert ws_ is ws

    asyncio.run(scenario())

    assert captured["uri"] == "ws://127.0.0.1:8000/ws/modules?token=tok"
    # first thing sent is the capability frame, using make_frame so the
    # envelope/protocol version come from waycast.wire, not a hand-written clone
    frame = parse_frame(ws.sent[0])
    assert frame.type == "capability"
    assert frame.module == "alert"
    assert frame.protocol_version == 1
    assert frame.payload["name"] == "alert"


def test_connect_module_no_token_query(monkeypatch):
    from waycast_examples import client

    ws = FakeWS()
    captured: dict[str, str] = {}
    monkeypatch.setattr(client.websockets, "connect", _fake_connect(ws, captured))

    async def scenario():
        async with connect_module(
            hub_url="ws://127.0.0.1:9000",
            token="",
            capability={
                "name": "x",
                "kind": "output",
                "output": {"schema": {}, "description": ""},
            },
        ):
            pass

    asyncio.run(scenario())
    assert captured["uri"] == "ws://127.0.0.1:9000/ws/modules"


def test_connect_module_rejects_bad_ack(monkeypatch):
    import json

    from waycast_examples import client

    ws = FakeWS()

    @asynccontextmanager
    async def factory(uri: str, **kwargs: Any):
        await ws._acks.put(
            json.dumps(
                {
                    "protocol_version": 1,
                    "type": "capability",
                    "module": "x",
                    "payload": {"accepted": False},
                }
            )
        )
        yield ws

    monkeypatch.setattr(client.websockets, "connect", factory)

    async def scenario():
        async with connect_module(
            hub_url="ws://127.0.0.1:8000",
            token="",
            capability={
                "name": "x",
                "kind": "output",
                "output": {"schema": {}, "description": ""},
            },
        ):
            pass

    with pytest.raises(RuntimeError, match="did not accept"):
        asyncio.run(scenario())

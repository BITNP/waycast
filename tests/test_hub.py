"""Hub frame routing over a real module websocket.

These tests run the hub accept loop and a module client on one event loop,
using an in-memory websocket pair (there is no HTTP server, no uvicorn, no
fake model).  The hub never touches the Agent model, so this stays offline;
Agent model behavior is covered by real-model smokes.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from waycast.capabilities import CapabilityCatalog
from waycast.hub import Hub
from waycast.protocols import UnifiedInput
from waycast.wire import make_frame, parse_frame


class PairWS:
    """A minimal full-duplex websocket pair for driving the hub without HTTP."""

    def __init__(self) -> None:
        self._server: asyncio.Queue[str] = asyncio.Queue()  # hub -> module
        self._client: asyncio.Queue[str] = asyncio.Queue()  # module -> hub
        self._closed = False
        self.query_params: dict[str, str] = {}

    async def accept(self) -> None:
        pass

    async def receive_text(self) -> str:
        if self._closed:
            raise asyncio.CancelledError
        return await asyncio.wait_for(self._client.get(), timeout=10.0)

    async def send_text(self, text: str) -> None:
        await self._server.put(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self._closed = True

    async def recv(self) -> str:
        return await asyncio.wait_for(self._server.get(), timeout=10.0)


echo_cap = {
    "name": "echo",
    "kind": "both",
    "input": {"description": "text lines"},
    "output": {
        "schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        "description": "echo text back",
    },
    "status": {"enabled": True, "description": "liveness"},
}


def run(coro):
    """Run an async hub interaction on a fresh event loop."""
    import asyncio

    return asyncio.run(coro)


def _make_env():
    cat = CapabilityCatalog()
    received: list[UnifiedInput] = []
    results: list = []

    async def enqueue(input_: UnifiedInput) -> None:
        received.append(input_)

    hub = Hub(cat, token="tok", enqueue_input=enqueue, on_result=results.append)
    return hub, cat, received, results


def test_first_frame_must_be_capability():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "tok"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.01)
        # hub is now waiting for the first text
        await ws._client.put(
            make_frame("input", "echo", {"content": "x"}).model_dump_json()
        )
        # hub should reject; the accept task should end
        try:
            await asyncio.wait_for(task, timeout=2.0)
            # either it raised (WaycastError path closed) or ended
        except Exception:
            pass
        assert cat.names() == []

    run(scenario())


def test_capability_and_input_enqueue():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "tok"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.01)
        await ws._client.put(
            make_frame(
                "capability", "echo", echo_cap, request_id=None
            ).model_dump_json()
        )
        ack = parse_frame(await ws.recv())
        assert ack.payload == {"accepted": True}
        # now the module is in the read loop; send an input (allow a beat)
        await ws._client.put(
            make_frame(
                "input", "echo", {"content": "ping", "source": "echo"}
            ).model_dump_json()
        )
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.02)
        assert len(received) == 1
        assert received[0].content == "ping"
        assert received[0].source == "echo"
        # stop the accept loop
        task.cancel()

    run(scenario())


def test_bad_token_rejected():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "wrong"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.05)
        assert task.done()  # rejected before first frame
        assert cat.names() == []

    run(scenario())


def test_dispatch_validates_and_sends():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "tok"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.01)
        await ws._client.put(
            make_frame(
                "capability", "echo", echo_cap, request_id=None
            ).model_dump_json()
        )
        await ws.recv()  # ack
        # dispatch from the hub side
        out = await hub.dispatch_unit("echo", {"text": "hi"})
        assert out.status == "ok"
        frame = parse_frame(await ws.recv())
        assert frame.type == "output_unit"
        assert frame.payload == {"text": "hi"}
        task.cancel()

    run(scenario())


def test_dispatch_rejects_bad_schema():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "tok"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.01)
        await ws._client.put(
            make_frame(
                "capability", "echo", echo_cap, request_id=None
            ).model_dump_json()
        )
        await ws.recv()  # ack
        out = await hub.dispatch_unit("echo", {"text": 123})
        assert out.status == "error"
        assert "schema validation failed" in out.detail
        task.cancel()

    run(scenario())


def test_dispatch_unknown_module():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "tok"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.01)
        await ws._client.put(
            make_frame(
                "capability", "echo", echo_cap, request_id=None
            ).model_dump_json()
        )
        await ws.recv()
        out = await hub.dispatch_unit("nope", {"text": "x"})
        assert out.status == "error"
        assert "no connected output module" in out.detail
        task.cancel()

    run(scenario())


def test_status_roundtrip():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "tok"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.01)
        await ws._client.put(
            make_frame(
                "capability", "echo", echo_cap, request_id=None
            ).model_dump_json()
        )
        await ws.recv()  # ack
        # status query
        qtask = asyncio.create_task(hub.query_status("echo"))
        sq = parse_frame(await ws.recv())
        assert sq.type == "status_query"
        assert sq.request_id is not None
        await ws._client.put(
            make_frame(
                "status_result", "echo", {"state": "up"}, request_id=sq.request_id
            ).model_dump_json()
        )
        result = await asyncio.wait_for(qtask, timeout=5.0)
        assert result == {"state": "up"}
        task.cancel()

    run(scenario())


def test_catalog_output_accumulates_result_frames():
    hub, cat, received, results = _make_env()

    async def scenario():
        ws = PairWS()
        ws.query_params = {"token": "tok"}
        task = asyncio.create_task(hub.accept(ws))
        await asyncio.sleep(0.01)
        await ws._client.put(
            make_frame(
                "capability", "echo", echo_cap, request_id=None
            ).model_dump_json()
        )
        await ws.recv()
        await ws._client.put(
            make_frame(
                "result", "echo", {"module": "echo", "status": "ok", "detail": "done"}
            ).model_dump_json()
        )
        for _ in range(50):
            if results:
                break
            await asyncio.sleep(0.02)
        assert len(results) == 1
        assert results[0].module == "echo"
        assert results[0].status == "ok"
        task.cancel()

    run(scenario())

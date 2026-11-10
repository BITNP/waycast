"""The WebSocket hub: modules connect here over the wire protocol.

This is the network half of the Agent-as-a-hub architecture (ADR-0008).  It
owns the module connections and keeps the capability catalog in sync:

- ``/ws/modules`` accepts one multiplexed, full-duplex connection per module.
- The first frame must be a capability advertisement; the module name is the
  connection identity (reconnects replace the old connection idempotently).
- ``input`` frames flow into the same bounded queue that the service owns, so
  backpressure is globally consistent (ADR-0006).  WebSocket is the only
  input channel.
- ``output_unit`` frames are sent by the hub when the Agent dispatches a unit;
  the module answers with a ``result`` frame which the worker accumulates
  (ADR-0002).
- ``status_query`` / ``status_result`` implement the optional status ability
  (A15/A19); the bridge turns queries into per-module status tools.

The hub layer is transport-specific (WebSocket); the frame model in
``waycast.wire`` is transport-independent.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import jsonschema
from fastapi import WebSocket, WebSocketDisconnect

from waycast.capabilities import CapabilityCatalog
from waycast.protocols import UnifiedInput, WaycastError
from waycast.state import OutputResult
from waycast.wire import Capability, WireFrame, make_frame, parse_frame

log = logging.getLogger(__name__)


class ModuleConnection:
    """One live module WebSocket plus its endpoint record."""

    def __init__(self, ws: WebSocket, endpoint: Any, cap: Capability) -> None:
        self.ws = ws
        self.endpoint = endpoint
        self.capability = cap
        self.closed = False


class Hub:
    """Accepts module connections, keeps the catalog, routes frames."""

    def __init__(
        self,
        catalog: CapabilityCatalog,
        *,
        token: str = "",
        enqueue_input: Callable[[UnifiedInput], Awaitable[None]] | None = None,
        on_result: Callable[[OutputResult], Any] | None = None,
    ) -> None:
        self.catalog = catalog
        self.token = token
        self._enqueue_input = enqueue_input
        self._on_result = on_result
        self._connections: dict[str, ModuleConnection] = {}
        self._status_futures: dict[str, asyncio.Future[dict[str, Any]]] = {}

    # -- connection lifecycle -------------------------------------------

    async def accept(self, ws: WebSocket) -> None:
        """Handle one module WebSocket connection from connect to close."""

        await ws.accept()
        conn: ModuleConnection | None = None
        try:
            # Token validation happens on the handshake query param (A8).
            self._check_token(ws)
            # First frame must be the capability advertisement (A13).
            raw = await ws.receive_text()
            frame = parse_frame(raw)
            if frame.type != "capability":
                raise WaycastError(f"first frame must be capability, got {frame.type}")
            cap = Capability.model_validate(frame.payload)
            name = cap.name

            # Reconnect: replace the previous connection under the same name.
            old = self._connections.get(name)
            if old is not None:
                await old.ws.close(code=4000, reason="replaced by new connection")
            endpoint = self.catalog.upsert(cap, connection=ws)
            conn = ModuleConnection(ws, endpoint, cap)
            self._connections[name] = conn
            log.info("module %s connected (kind=%s)", name, cap.kind)

            # Acknowledge so the module knows it is admitted.
            await ws.send_text(
                make_frame("capability", name, {"accepted": True}).model_dump_json()
            )

            await self._read_loop(conn)
        except WebSocketDisconnect:
            pass
        except WaycastError as exc:
            log.warning("rejecting module connection: %s", exc)
            with contextlib.suppress(Exception):
                await ws.close(code=4400, reason=str(exc))
        except Exception as exc:  # never crash the accept task
            log.exception("module connection error")
            with contextlib.suppress(Exception):
                await ws.close(code=4400, reason=f"error: {exc}")
        finally:
            # Drop only if this connection is still the current one: a
            # reconnect replaces the entry, so an old task's finally must not
            # remove the new connection under the same name.
            if conn is not None and self._connections.get(conn.capability.name) is conn:
                self._drop(conn.capability.name)

    def _check_token(self, ws: WebSocket) -> None:
        """Validate the shared connection token (A8) from the WS handshake."""

        if not self.token:
            return  # token auth disabled
        presented = ws.query_params.get("token", "")
        if presented != self.token:
            raise WaycastError("invalid connection token")

    def _drop(self, name: str) -> None:
        conn = self._connections.pop(name, None)
        if conn is None:
            return
        conn.closed = True
        self.catalog.remove(name)
        log.info("module %s disconnected", name)

    # -- reading frames ------------------------------------------------

    async def _read_loop(self, conn: ModuleConnection) -> None:
        while True:
            raw = await conn.ws.receive_text()
            frame = parse_frame(raw)
            if frame.module != conn.capability.name:
                raise WaycastError(
                    f"frame module {frame.module!r} does not match connection {conn.capability.name!r}"
                )
            await self._handle(conn, frame)

    async def _handle(self, conn: ModuleConnection, frame: WireFrame) -> None:
        if frame.type == "input":
            await self._handle_input(conn, frame)
        elif frame.type == "result":
            self._handle_result(conn, frame)
        elif frame.type == "status_result":
            self._handle_status_result(conn, frame)
        else:
            raise WaycastError(f"unexpected frame type from module: {frame.type}")

    async def _handle_input(self, conn: ModuleConnection, frame: WireFrame) -> None:
        if conn.capability.kind not in ("input", "both"):
            raise WaycastError(
                f"module {conn.capability.name!r} is not an input module"
            )
        payload = frame.payload
        inp = UnifiedInput(
            content=str(payload.get("content", "")),
            source=payload.get("source", conn.capability.name),
            metadata=dict(payload.get("metadata", {}) or {}),
        )
        log.debug(
            "input frame from %s -> queue (content=%r, metadata=%s)",
            conn.capability.name,
            inp.content[:120],
            inp.metadata,
        )
        if self._enqueue_input is not None:
            await self._enqueue_input(inp)

    def _handle_result(self, conn: ModuleConnection, frame: WireFrame) -> None:
        if conn.capability.kind not in ("output", "both"):
            raise WaycastError(
                f"module {conn.capability.name!r} is not an output module"
            )
        result = OutputResult.model_validate(frame.payload)
        log.debug(
            "result frame from %s: status=%s detail=%s",
            conn.capability.name,
            result.status,
            result.detail,
        )
        if self._on_result is not None:
            self._on_result(result)

    def _handle_status_result(self, conn: ModuleConnection, frame: WireFrame) -> None:
        req_id = frame.request_id
        fut = self._status_futures.pop(req_id, None) if req_id else None
        if fut is not None and not fut.done():
            fut.set_result(frame.payload)

    # -- hub -> module sends --------------------------------------------

    async def dispatch_unit(self, module: str, payload: dict[str, Any]) -> OutputResult:
        """Send one output unit to a connected module and return its result.

        Fire-and-forget dispatch (ADR-0002): the unit is sent as an
        ``output_unit`` frame and the immediate outcome is returned.  The
        module answers with a result frame which the service accumulates for
        the next invocation; what we return here only records dispatch errors
        (unknown/not-connected module, schema-invalid payload, send failure).
        This keeps the successful result from being double-counted: the result
        frame is the single authoritative success path (ADR-0002).
        """

        endpoint = self.catalog.resolve_output(module)
        if endpoint is None:
            return OutputResult(
                module=module,
                status="error",
                detail=f"no connected output module named {module!r}",
            )
        conn = self._connections.get(module)
        if conn is None or conn.closed:
            return OutputResult(
                module=module,
                status="error",
                detail=f"module {module!r} is not connected",
            )
        # Validate against the advertised JSON Schema before dispatch (A22).
        schema = self.catalog.output_schema(module)
        if schema is None:
            return OutputResult(
                module=module,
                status="error",
                detail=f"module {module!r} has no output schema",
            )
        try:
            jsonschema.validate(payload, schema)
        except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
            return OutputResult(
                module=module,
                status="error",
                detail=f"schema validation failed: {exc}",
            )
        try:
            await conn.ws.send_text(
                make_frame("output_unit", module, payload).model_dump_json()
            )
        except Exception as exc:  # noqa: BLE001 - 网络发送边界不穷举 uvicorn/starlette 各栈异常族，统一收敛为 error 结果上报
            log.warning("unit dispatch to %s failed: %s", module, exc)
            return OutputResult(
                module=module,
                status="error",
                detail=f"dispatch failed: {exc}",
            )
        log.debug(
            "unit dispatched to %s: %s", module, json.dumps(payload, ensure_ascii=False)
        )
        return OutputResult(module=module, status="ok", detail="dispatched")

    async def query_status(self, module: str) -> dict[str, Any] | None:
        """Send a status_query to a connected module and await status_result.

        The request_id is generated here and correlates the round-trip
        internally; the caller (the capability bridge's status tool) only
        names the module it wants to inspect.
        """

        conn = self._connections.get(module)
        if conn is None or conn.closed:
            return None
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._status_futures[request_id] = fut
        try:
            await conn.ws.send_text(
                make_frame(
                    "status_query", module, {}, request_id=request_id
                ).model_dump_json()
            )
            return await asyncio.wait_for(fut, timeout=10.0)
        except Exception:  # noqa: BLE001 - 尽力而为的状态查询：超时/断连/任何协议故障一律按不可达返回 None
            return None
        finally:
            self._status_futures.pop(request_id, None)

    async def close(self) -> None:
        for conn in list(self._connections.values()):
            with contextlib.suppress(Exception):  # 关闭尽力而为
                await conn.ws.close()
        self._connections.clear()
        for name in list(self.catalog.names()):
            self.catalog.remove(name)


__all__ = ["Hub", "ModuleConnection"]

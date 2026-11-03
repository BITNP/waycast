"""The Waycast service: FastAPI hub + a bounded, blocking, single-consumer queue.

The Agent is a hub (ADR-0008): modules connect over WebSocket to /ws/modules,
announce their capabilities, and exchange wire frames.  Every input - module
"input" frames - flows into the same bounded queue and the same single-consumer
worker, so backpressure is globally consistent (ADR-0006).  A single worker
consumes inputs one at a time, runs the Agent invocation, and dispatches output
units back to the owning module connections.  Module "result" frames accumulate
into the next invocation (ADR-0002).

WebSocket is the only input channel.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket

from waycast.agent import Agent
from waycast.capabilities import CapabilityCatalog
from waycast.hub import Hub
from waycast.protocols import UnifiedInput
from waycast.state import OutputResult

LOGGER = logging.getLogger(__name__)


class Service:
    """Assembles the hub app: one Agent + one input queue + module WebSockets."""

    def __init__(
        self,
        agent: Agent,
        catalog: CapabilityCatalog,
        *,
        queue_size: int = 100,
        hub_token: str = "",
    ) -> None:
        self.agent = agent
        self.catalog = catalog
        self.queue: asyncio.Queue[UnifiedInput] = asyncio.Queue(maxsize=queue_size)
        self._worker_task: asyncio.Task | None = None
        self._last_results: dict[str, Any] = {}

        self.hub = Hub(
            catalog,
            token=hub_token,
            enqueue_input=self._enqueue_input,
            on_result=self._on_result,
        )
        agent.set_adispatch(self.hub.dispatch_unit)
        agent.set_status_query(self.hub.query_status)

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self._worker_task = asyncio.create_task(self._run_worker())
            yield
            if self._worker_task:
                self._worker_task.cancel()
            await self.hub.close()

        self.app = FastAPI(title="Waycast", lifespan=lifespan)
        self._add_routes()

    async def _enqueue_input(self, inp: UnifiedInput) -> None:
        await self.queue.put(inp)  # blocking when full (backpressure)

    def _on_result(self, result: OutputResult) -> None:
        """A module answered a dispatched unit; feed it to the next invocation."""

        self.agent.remember_output_result(result)

    def _add_routes(self) -> None:
        app = self.app

        @app.get("/health")
        async def health() -> dict[str, Any]:
            return {"status": "ok", "queue_size": self.queue.qsize()}

        @app.get("/results")
        async def get_results() -> dict[str, Any]:
            return {
                "last_result": self._last_results.get("last_result"),
                "last_error": self._last_results.get("last_error"),
                "last_skipped": self._last_results.get("last_skipped"),
                "pending_output_results": [
                    r.model_dump() for r in self.agent.pending_output_results.results
                ],
                "connected_modules": self.catalog.names(),
                "queue_size": self.queue.qsize(),
            }

        @app.websocket("/ws/modules")
        async def ws_modules(websocket: WebSocket) -> None:
            await self.hub.accept(websocket)

    async def _run_worker(self) -> None:
        """Single consumer: one input at a time, then dispatch."""
        while True:
            inp = await self.queue.get()
            LOGGER.debug(
                "input dequeued (source=%s, backlog=%d): %r",
                inp.source,
                self.queue.qsize(),
                inp.content,
            )
            try:
                # No reachable output targets: the model could only emit an
                # empty (or doomed) units list, so skip the real call instead
                # of burning tokens for nothing.  The dropped input is
                # recorded so operators can see it in /results.
                if not self.catalog.output_names():
                    LOGGER.warning(
                        "input skipped: no output module connected; content=%r",
                        inp.content[:120],
                    )
                    self._last_results["last_skipped"] = {
                        "reason": "no output module connected",
                        "input": inp.model_dump(),
                    }
                    continue
                started_at = time.perf_counter()
                res = await self.agent.ainvoke(inp)
                self._last_results["last_result"] = res.model_dump()
                LOGGER.info(
                    "invocation finished in %.1fs: %d unit(s) dispatched",
                    time.perf_counter() - started_at,
                    len(res.units),
                )
            except Exception as exc:  # never kill the worker
                LOGGER.exception("agent invocation failed")
                self._last_results["last_error"] = str(exc)
            finally:
                self.queue.task_done()


__all__ = ["Service"]

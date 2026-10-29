"""The Waycast service: FastAPI + a bounded, blocking, single-consumer queue.

POST /input enqueues a unified input and returns 202 immediately.  A single
worker consumes inputs one at a time, runs the Agent invocation, and
dispatches output units.  When the queue is full, producers block: that
blocking is the backpressure contract (ADR-0006).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from waycast.agent import Agent
from waycast.protocols import ModuleRegistry, UnifiedInput


class InputEnvelope(BaseModel):
    """HTTP body for POST /input: unified input fields."""

    content: str
    source: str = "http"
    metadata: dict[str, Any] = {}


class Service:
    """Assembles the app with one Agent + one input queue."""

    def __init__(
        self,
        agent: Agent,
        registry: ModuleRegistry,
        *,
        queue_size: int = 100,
    ) -> None:
        self.agent = agent
        self.registry = registry
        self.queue: asyncio.Queue[UnifiedInput] = asyncio.Queue(maxsize=queue_size)
        self._worker_task: asyncio.Task | None = None
        self._last_results: dict[str, Any] = {}

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self._worker_task = asyncio.create_task(self._run_worker())
            yield
            if self._worker_task:
                self._worker_task.cancel()

        self.app = FastAPI(title="Waycast", lifespan=lifespan)
        self._add_routes()

    def _add_routes(self) -> None:
        app = self.app

        @app.get("/health")
        async def health() -> dict[str, Any]:
            return {"status": "ok", "queue_size": self.queue.qsize()}

        @app.post("/input")
        async def post_input(envelope: InputEnvelope) -> dict[str, Any]:
            """Enqueue an input; block when full (backpressure); return 200."""
            inp = UnifiedInput(
                content=envelope.content,
                source=envelope.source,
                metadata=envelope.metadata,
            )
            try:
                await self.queue.put(inp)  # blocking when full
            except asyncio.CancelledError:
                raise HTTPException(status_code=503, detail="service shutting down")
            return {"accepted": True, "queue_size": self.queue.qsize()}

        @app.get("/results")
        async def get_results() -> dict[str, Any]:
            return {
                "last_result": self._last_results.get("last_result"),
                "pending_output_results": [
                    r.model_dump() for r in self.agent.pending_output_results.results
                ],
                "queue_size": self.queue.qsize(),
            }

    async def _run_worker(self) -> None:
        """Single consumer: one input at a time, then dispatch."""
        while True:
            inp = await self.queue.get()
            try:
                res = await self.agent.ainvoke(inp)
                self._last_results["last_result"] = res.model_dump()
            except Exception as exc:  # never kill the worker
                self._last_results["last_error"] = str(exc)
            finally:
                self.queue.task_done()


__all__ = ["Service", "InputEnvelope"]

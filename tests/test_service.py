"""HTTP service behavior: the bounded, blocking, single-consumer input queue
with a worker that consumes one input at a time and dispatches units."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from waycast.agent import Agent
from waycast.modules import (
    HttpInputModule,
    MemoryLogOutputModule,
    NotifyOutputModule,
    _notifications,
)
from waycast.protocols import ModuleRegistry
from waycast.service import Service


def build(fake_chat) -> Service:
    reg = ModuleRegistry()
    reg.register_input(HttpInputModule())
    reg.register_output(NotifyOutputModule())
    reg.register_output(MemoryLogOutputModule())
    agent = Agent(registry=reg, model=fake_chat, tools=[])
    return Service(agent=agent, registry=reg, queue_size=5)


def test_post_input_runs_worker_and_dispatches(fake_chat):
    _notifications.clear()
    fake_chat.units = [
        {"module": "notify", "payload": {"message": "via http", "level": "info"}}
    ]
    svc = build(fake_chat)

    async def main():
        worker = asyncio.create_task(svc._run_worker())
        transport = httpx.ASGITransport(app=svc.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(
                "/input", json={"content": "hello", "source": "http"}
            )
            assert r.status_code == 200
            assert r.json()["accepted"] is True
            await asyncio.sleep(0.6)
            res = await c.get("/results")
        worker.cancel()
        return res.json()

    data = asyncio.run(main())
    assert _notifications == [{"message": "via http", "level": "info"}]
    assert data["last_result"]["units"][0]["module"] == "notify"
    assert data["last_result"]["results"][0]["status"] == "ok"
    assert data["pending_output_results"][0]["status"] == "ok"
    assert data["queue_size"] == 0


def test_backpressure_queue_is_bounded(fake_chat):
    # filling the queue beyond maxsize should block the producer until the
    # worker drains; we verify the queue size never exceeds maxsize.
    svc = build(fake_chat)

    async def main():
        worker = asyncio.create_task(svc._run_worker())
        # enqueue many inputs quickly; only 5 can fit before blocking
        for i in range(12):
            await svc.queue.put(
                __import__("waycast.protocols", fromlist=["UnifiedInput"]).UnifiedInput(
                    content=f"m{i}", source="http"
                )
            )
        assert svc.queue.qsize() <= 5
        worker.cancel()

    asyncio.run(main())

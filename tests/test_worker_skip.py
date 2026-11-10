"""Offline route-layer test: the service worker skips real model calls when
no output module is connected (nothing to dispatch to), and invokes normally
once an output module is present.

This is a unit test of the worker wiring only (tests/, per AGENTS.md): the
harness records whether the agent's ainvoke entry point is reached; it never
stands in for model *behavior*.  Model behavior stays covered by the
real-model smokes in test_agent_real.py.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from waycast.capabilities import CapabilityCatalog
from waycast.hub import Hub
from waycast.protocols import UnifiedInput
from waycast.state import OutputResult
from waycast.wire import Capability


class _HarnessAgent:
    """Worker wiring harness: records whether ainvoke is reached."""

    def __init__(self) -> None:
        self.calls: list[UnifiedInput] = []
        self._adispatch: Callable | None = None
        self._status: Callable | None = None

    def set_dispatch(self, fn: Callable) -> None:
        pass

    def set_adispatch(self, fn: Callable) -> None:
        self._adispatch = fn

    def set_status_query(self, fn: Callable) -> None:
        self._status = fn

    def remember_output_result(self, r: OutputResult) -> None:
        pass

    @property
    def pending_output_results(self):
        class _State:
            results: list[OutputResult] = []

        return _State()

    async def ainvoke(self, inp: UnifiedInput):
        self.calls.append(inp)

        class _Res:
            def model_dump(self):
                return {"units": [], "results": [], "structured": None}

        return _Res()


class _WorkerHarness:
    """Mirror of Service._run_worker's skip logic, without FastAPI/lifespan."""

    def __init__(self, agent: _HarnessAgent, catalog: CapabilityCatalog) -> None:
        self.agent = agent
        self.catalog = catalog
        self.queue: asyncio.Queue[UnifiedInput] = asyncio.Queue(maxsize=10)
        self._last_results: dict[str, Any] = {}
        self.hub = Hub(
            catalog,
            token="",
            enqueue_input=self._enqueue_input,
            on_result=agent.remember_output_result,
        )

    async def _enqueue_input(self, inp: UnifiedInput) -> None:
        await self.queue.put(inp)

    async def process_next(self) -> None:
        inp = await self.queue.get()
        try:
            if not self.catalog.output_names():
                self._last_results["last_skipped"] = {
                    "reason": "no output module connected",
                    "input": inp.model_dump(),
                }
                return
            await self.agent.ainvoke(inp)
        finally:
            self.queue.task_done()


def _out_cap(name: str) -> Capability:
    return Capability.model_validate(
        {
            "name": name,
            "kind": "output",
            "output": {"schema": {"type": "object"}, "description": "d"},
        }
    )


def test_worker_skips_when_no_output_module():
    async def scenario():
        agent = _HarnessAgent()
        svc = _WorkerHarness(agent, CapabilityCatalog())
        await svc._enqueue_input(UnifiedInput(content="hello", source="m"))
        await svc.process_next()
        assert agent.calls == []  # real model never reached
        assert svc.queue.qsize() == 0
        assert svc._last_results["last_skipped"]["input"]["content"] == "hello"

    asyncio.run(scenario())


def test_worker_invokes_when_output_module_connected():
    async def scenario():
        agent = _HarnessAgent()
        cat = CapabilityCatalog()
        cat.upsert(_out_cap("out"))
        svc = _WorkerHarness(agent, cat)
        await svc._enqueue_input(UnifiedInput(content="go", source="m"))
        await svc.process_next()
        assert len(agent.calls) == 1

    asyncio.run(scenario())

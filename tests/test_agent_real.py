"""Real-model Agent invocation tests (no mocks, per AGENTS.md).

These hit the model configured in .env (WAYCAST_BASE_URL / WAYCAST_API_KEY
/ WAYCAST_MODEL).  The credentials live in .env, which is gitignored, so
when they are missing the tests skip instead of failing CI-less clones.

They cover the Agent behaviors that a fake model cannot exercise honestly:
- structured output (units list, possibly empty)
- multi-round tool calling (the model must call the real get_time tool)
- the optional per-module status tool round-trip (A15/A19)
- output results feeding the next invocation (ADR-0002)

Each test runs inside one asyncio.run and closes the model's httpx2
async client (an injected per-test httpx2.AsyncClient) on that same
loop, so the loop exits cleanly and the per-test client never touches
langchain_openai's process-cached default client.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(os.getcwd()) / ".env")

import httpx2

from waycast.agent import Agent
from waycast.capabilities import CapabilityCatalog
from waycast.config import WaycastConfig, make_model
from waycast.protocols import UnifiedInput
from waycast.state import OutputResult
from waycast.tools import default_tools
from waycast.wire import Capability


def _cfg():
    cfg = WaycastConfig.from_env()
    if not cfg.base_url or not cfg.api_key:
        pytest.skip("WAYCAST_BASE_URL / WAYCAST_API_KEY not configured")
    return cfg


def _catalog():
    cat = CapabilityCatalog()
    cat.upsert(
        Capability.model_validate(
            {
                "name": "time_bell",
                "kind": "output",
                "output": {
                    "schema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                    "description": "push a short reminder text to the user (time_bell)",
                },
                "status": {"enabled": True, "description": "time_bell liveness"},
            }
        )
    )
    return cat


@pytest.mark.real_model
def test_real_model_tool_call_and_unit_dispatch():
    cfg = _cfg()
    cat = _catalog()
    dispatched: list[tuple[str, dict]] = []

    async def scenario():
        client = httpx2.AsyncClient()
        agent = Agent(
            cat, model=make_model(cfg, http_async_client=client), tools=default_tools()
        )
        try:

            async def adispatch(module: str, payload: dict):
                dispatched.append((module, payload))
                return OutputResult(module=module, status="ok", detail="dispatched")

            agent.set_adispatch(adispatch)
            res = await asyncio.wait_for(
                agent.ainvoke(
                    UnifiedInput(
                        content=(
                            "What time is it now in UTC? Call the available tool to "
                            "look it up, then output one time_bell unit whose text "
                            "contains the UTC time you found."
                        ),
                        source="cli",
                    )
                ),
                timeout=120,
            )
            assert len(res.units) >= 1
            assert res.units[0].module == "time_bell"
            assert "text" in res.units[0].payload
            assert (
                "UTC" in res.units[0].payload["text"]
                or "20" in res.units[0].payload["text"]
            )
            assert dispatched == [(u.module, u.payload) for u in res.units]
            assert all(r.status == "ok" for r in res.results)

            # empty-units path: the model must emit no units when told nothing to do
            res2 = await asyncio.wait_for(
                agent.ainvoke(
                    UnifiedInput(
                        content="There is nothing to do; output empty units.",
                        source="cli",
                    )
                ),
                timeout=120,
            )
            assert res2.units == []
            assert res2.results == []
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.real_model
def test_real_model_status_tool_roundtrip():
    cfg = _cfg()
    cat = _catalog()
    seen_status: list[str] = []

    async def scenario():
        client = httpx2.AsyncClient()
        agent = Agent(
            cat, model=make_model(cfg, http_async_client=client), tools=default_tools()
        )
        try:

            async def status_query(module: str):
                seen_status.append(module)
                return {"state": "up", "since": "boot"}

            agent.set_status_query(status_query)
            await asyncio.wait_for(
                agent.ainvoke(
                    UnifiedInput(
                        content=(
                            "First query the status of the time_bell module using "
                            "the status_time_bell tool, then call get_time for the "
                            "UTC time, then output one time_bell unit whose text "
                            "mentions the UTC time."
                        ),
                        source="cli",
                    )
                ),
                timeout=120,
            )
            assert "time_bell" in seen_status
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.real_model
def test_real_model_output_results_feed_next_invocation():
    cfg = _cfg()
    cat = _catalog()

    async def scenario():
        client = httpx2.AsyncClient()
        agent = Agent(
            cat, model=make_model(cfg, http_async_client=client), tools=default_tools()
        )
        try:

            async def adispatch(module: str, payload: dict):
                # Simulate an unreachable module: the Agent layer only
                # accumulates failed dispatches; the hub accumulates the
                # success path (ADR-0002).
                return OutputResult(
                    module=module, status="error", detail="simulated failure"
                )

            agent.set_adispatch(adispatch)

            r1 = await asyncio.wait_for(
                agent.ainvoke(
                    UnifiedInput(
                        content="Output one time_bell unit with text: first round.",
                        source="cli",
                    )
                ),
                timeout=120,
            )
            assert len(r1.units) == 1
            assert any(
                r.module == "time_bell" for r in agent.pending_output_results.results
            )
            assert r1.results and all(r2.status != "ok" for r2 in r1.results)

            await asyncio.wait_for(
                agent.ainvoke(
                    UnifiedInput(
                        content="Nothing else to do; output empty units.", source="cli"
                    )
                ),
                timeout=120,
            )
            # one-shot consumption (ADR-0002 / ADR-0013): invocation 2 drained
            # the failed delivery into its system prompt, so nothing is
            # pending afterwards
            assert agent.pending_output_results.results == []
            # and this invocation delivered an empty feed of its own
            r3 = await asyncio.wait_for(
                agent.ainvoke(
                    UnifiedInput(
                        content="Nothing else to do; output empty units.", source="cli"
                    )
                ),
                timeout=120,
            )
            assert r3.units == []
            assert agent.pending_output_results.results == []
        finally:
            await client.aclose()

    asyncio.run(scenario())

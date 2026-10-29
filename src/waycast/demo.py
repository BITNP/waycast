"""Bootstrap the demo: registry + modules + model + Agent + Service.

This is the concrete composition users can run to see the whole loop:
HTTP POST /input -> queue -> one invocation -> structured output units ->
output modules accept fire-and-forget -> results feed the next input.
"""
from __future__ import annotations

from waycast.agent import Agent
from waycast.config import WaycastConfig, make_model
from waycast.modules import (
    HttpInputModule,
    MemoryLogOutputModule,
    NotifyOutputModule,
)
from waycast.protocols import ModuleRegistry
from waycast.service import Service
from waycast.tools import default_tools


def build_registry() -> ModuleRegistry:
    reg = ModuleRegistry()
    reg.register_input(HttpInputModule())
    reg.register_output(NotifyOutputModule())
    reg.register_output(MemoryLogOutputModule())
    return reg


def build_agent(reg: ModuleRegistry, config: WaycastConfig, **kwargs) -> Agent:
    model = make_model(config)
    return Agent(
        registry=reg,
        model=model,
        tools=kwargs.pop("tools", default_tools()),
        thread_id=config.thread_id,
        **kwargs,
    )


def build_service(reg: ModuleRegistry, agent: Agent, config: WaycastConfig) -> Service:
    return Service(agent=agent, registry=reg, queue_size=config.queue_size)


__all__ = ["build_registry", "build_agent", "build_service"]

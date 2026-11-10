"""Capability catalog: the Agent's view of connected modules.

The Agent is a hub (ADR-0008): modules connect over WebSockets, authenticate,
and announce their capabilities.  The hub keeps a catalog of the currently
connected modules.  The catalog is what builds the module part of the system
prompt and routes output units; it is not an in-process registry of Python
objects.

A module connection may carry input and/or output capability over the same
multiplexed connection (A25).  Status query is optional (A19): a module that
does not advertise ``status.enabled`` gets no status tool.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from waycast.wire import Capability, OutputCapability


@dataclass
class ModuleEndpoint:
    """A connected module's capability advertisement, keyed by module name.

    The ``connection`` slot holds an opaque handle owned by the hub's WebSocket
    layer (a way for the capability bridge to deliver frames to this module's
    connection).  It is ``None`` while a module is only declared (e.g. in a
    static test fixture) and set once the module actually connects.
    """

    name: str
    kind: str
    input_description: str = ""
    output_schema: dict[str, Any] = field(default_factory=dict)
    output_description: str = ""
    status_description: str = ""
    status_enabled: bool = False
    connection: Any = None

    @classmethod
    def from_capability(cls, cap: Capability, connection: Any = None) -> "ModuleEndpoint":
        return cls(
            name=cap.name,
            kind=cap.kind,
            input_description=cap.input.description if cap.input else "",
            output_schema=dict(cap.output.json_schema) if cap.output else {},
            output_description=cap.output.description if cap.output else "",
            status_description=cap.status.description if cap.status else "",
            status_enabled=bool(cap.status and cap.status.enabled),
            connection=connection,
        )

    @property
    def is_input(self) -> bool:
        return self.kind in ("input", "both")

    @property
    def is_output(self) -> bool:
        return self.kind in ("output", "both")


class CapabilityCatalog:
    """The hub-side registry of connected module endpoints.

    Module name is the identity (ADR-0008): the same name replaces the previous
    connection, making reconnects idempotent.  Behaviors:

    - ``upsert`` on capability advertisement (join/reconnect).
    - ``remove`` on disconnect.
    - ``output_units`` validates a unit against the advertised JSON Schema and
      routes it to the owning connection.
    - ``describe_output_modules`` / ``describe_input_modules`` render the
      capability catalog for the system prompt.
    """

    def __init__(self) -> None:
        self._modules: dict[str, ModuleEndpoint] = {}

    def upsert(self, cap: Capability, connection: Any = None) -> ModuleEndpoint:
        endpoint = ModuleEndpoint.from_capability(cap, connection=connection)
        self._modules[cap.name] = endpoint
        return endpoint

    def remove(self, name: str) -> None:
        self._modules.pop(name, None)

    def get(self, name: str) -> ModuleEndpoint | None:
        return self._modules.get(name)

    def names(self) -> list[str]:
        return sorted(self._modules)

    def output_names(self) -> list[str]:
        return sorted(n for n, m in self._modules.items() if m.is_output)

    def input_names(self) -> list[str]:
        return sorted(n for n, m in self._modules.items() if m.is_input)

    def has_output(self, name: str) -> bool:
        endpoint = self._modules.get(name)
        return bool(endpoint and endpoint.is_output)

    def output_schema(self, name: str) -> dict[str, Any] | None:
        endpoint = self._modules.get(name)
        if not endpoint or not endpoint.is_output:
            return None
        return endpoint.output_schema

    def resolve_output(self, name: str) -> ModuleEndpoint | None:
        endpoint = self._modules.get(name)
        if endpoint and endpoint.is_output:
            return endpoint
        return None

    def status_tools(self) -> list[ModuleEndpoint]:
        """Endpoints that advertise an enabled status-query ability (A19).

        Sorted by module name (like the describe_* renderers): reconnecting a
        module moves it to the end of the internal dict, and tool registration
        order is serialized into the request prefix - a shuffled order would
        break KV prefix caching (ADR-0014).
        """

        return [
            self._modules[n] for n in sorted(self._modules) if self._modules[n].status_enabled
        ]

    def describe_output_modules(self) -> str:
        """Markdown-ish catalog of connected output modules + their JSON Schemas."""

        lines: list[str] = []
        for name in sorted(self._modules):
            endpoint = self._modules[name]
            if not endpoint.is_output:
                continue
            lines.append(f"- {name}: {endpoint.output_description}")
            lines.append(
                f"  schema: {json.dumps(endpoint.output_schema, ensure_ascii=False)}"
            )
        return "\n".join(lines)

    def describe_input_modules(self) -> str:
        """Markdown-ish catalog of connected input modules and what they deliver."""

        lines: list[str] = []
        for name in sorted(self._modules):
            endpoint = self._modules[name]
            if endpoint.is_input:
                lines.append(f"- {name}: {endpoint.input_description}")
        return "\n".join(lines)

    def describe_status_tools(self) -> str:
        """The per-module status tools exposed to the model (A15/A19)."""

        lines: list[str] = []
        for name in sorted(self._modules):
            endpoint = self._modules[name]
            if endpoint.status_enabled:
                lines.append(
                    f"- status_{name}: query {name} status. {endpoint.status_description}"
                )
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._modules)


__all__ = ["CapabilityCatalog", "ModuleEndpoint"]

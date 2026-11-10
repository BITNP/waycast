"""Unified payload protocols for Waycast inputs and outputs.

This module owns the payload models that cross the module boundary
(ADR-0008): ``UnifiedInput`` (one input event produced by an input module
and consumed by the Agent) and ``OutputUnit`` (one delivery target produced
by the Agent and consumed by an output module).  The network envelope that
carries them over a module connection (frames, capability advertisement) is
defined in ``waycast.wire``; this module stays transport-independent.

There is no in-process registry here any more: modules are network clients,
and the hub keeps a ``CapabilityCatalog`` of connected modules instead.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class UnifiedInput(BaseModel):
    """The single data structure every input module produces.

    ``content`` is what the Agent actually receives (natural text), while
    ``metadata`` carries module-specific structured facts (source, ids,
    timestamps, ...).  Both are JSON-serializable.
    """

    model_config = ConfigDict(extra="allow")

    content: str
    source: str = "unknown"
    metadata: dict[str, Any] = {}


class OutputUnit(BaseModel):
    """One element of an Agent output list.

    ``module`` names a connected output module; ``payload`` is a JSON object
    that must satisfy that module's declared schema (validated by the hub
    before dispatch).  The Agent output is a list of these units; an empty
    list means "do nothing".
    """

    module: str
    payload: dict[str, Any] = {}


class WaycastError(RuntimeError):
    """Base error raised by the Waycast hub, service, or wire layer."""


__all__ = ["UnifiedInput", "OutputUnit", "WaycastError"]

"""Unified protocols for Waycast inputs, output modules, and their schemas.

This module defines the contracts that pluggable input and output modules must
implement, plus the Pydantic schemas they declare.  The design rule: every
module registers with the Agent through a single registry protocol, and
everything that crosses the module boundary is a plain JSON-serializable dict
so that any concrete transport (HTTP, queue, callback) can carry it.
"""
from __future__ import annotations

from abc import abstractmethod
import json

from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from waycast.state import OutputResult

T = TypeVar("T", bound=BaseModel)
TOut = TypeVar("TOut", bound=BaseModel)

# ---------------------------------------------------------------------------
# Unified input envelope
# ---------------------------------------------------------------------------


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

# ---------------------------------------------------------------------------
# Output unit + output result
# ---------------------------------------------------------------------------


class OutputUnit(BaseModel):
    """One element of an Agent output list.

    ``module`` names a registered output module; ``payload`` is a JSON object
    that must satisfy that module's declared schema.  The Agent output is a
    list of these units; an empty list means "do nothing".
    """

    module: str
    payload: dict[str, Any] = {}


@runtime_checkable
class OutputModule(Protocol, Generic[TOut]):
    """Protocol that every output module must implement.

    A module declares the schema JSON it accepts (``output_schema``), a unique
    name, and a synchronous ``accept`` method returning the immediate result.
    Memory of accepted units is handled by the Agent (which persists the result
    as a message for the next invocation), so ``accept`` should not itself
    mutate shared memory.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique module name used as the targeting key in OutputUnit."""

    @property
    @abstractmethod
    def output_schema(self) -> type[TOut]:
        """Pydantic model defining the exact JSON this module accepts."""

    @abstractmethod
    def accept(self, payload: dict[str, Any]) -> "OutputResult":
        """Accept a validated payload fire-and-forget and return the immediate outcome."""

    @abstractmethod
    def describe(self) -> str:
        """What this module does (injected into the Agent prompt so the LLM
        can choose it meaningfully)."""


@runtime_checkable
class InputModule(Protocol, Generic[T]):
    """Protocol that every input module must implement.

    ``emit`` is called on each delivery; it must return a UnifiedInput that
    carries the module's content and source.  Input modules may be started with
    the service, but their contract with the Agent ends at emit.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique module name recorded as the input source."""

    @abstractmethod
    def emit(self, **kwargs: Any) -> UnifiedInput:
        """Turn external signal kwargs into a UnifiedInput for the Agent."""


class WaycastError(RuntimeError):
    """Base error raised by the Waycast registry or service."""


class ModuleRegistry:
    """Single registry where input and output modules register and are looked up.

    - Input modules register by name and are only used to produce UnifiedInput.
    - Output modules register by name and declare the schema they accept.
    """

    def __init__(self) -> None:
        self._inputs: dict[str, InputModule] = {}
        self._outputs: dict[str, OutputModule] = {}

    # -- input modules --

    def register_input(self, module: InputModule) -> None:
        if not isinstance(module, InputModule):
            raise WaycastError(f"{module!r} is not an InputModule")
        if module.name in self._inputs:
            raise WaycastError(f"input module {module.name!r} already registered")
        self._inputs[module.name] = module

    def input_names(self) -> list[str]:
        return sorted(self._inputs)

    def get_input(self, name: str) -> InputModule:
        if name not in self._inputs:
            raise WaycastError(f"unknown input module: {name!r}")
        return self._inputs[name]

    # -- output modules --

    def register_output(self, module: OutputModule) -> None:
        if not isinstance(module, OutputModule):
            raise WaycastError(f"{module!r} is not an OutputModule")
        if module.name in self._outputs:
            raise WaycastError(f"output module {module.name!r} already registered")
        self._outputs[module.name] = module

    def output_names(self) -> list[str]:
        return sorted(self._outputs)

    def get_output(self, name: str) -> OutputModule:
        if name not in self._outputs:
            raise WaycastError(f"unknown output module: {name!r}")
        return self._outputs[name]

    def output_schemas(self) -> dict[str, type[BaseModel]]:
        return {n: m.output_schema for n, m in self._outputs.items()}

    def describe_output_modules(self) -> str:
        """Markdown-ish catalog of output modules + their JSON schemas."""
        lines = []
        for name in sorted(self._outputs):
            mod = self._outputs[name]
            schema = mod.output_schema
            schema_json = getattr(schema, "model_json_schema", lambda: {})()
            lines.append(f"- {name}: {mod.describe()}")
            lines.append(f"  schema: {json.dumps(schema_json, ensure_ascii=False)}")
        return "\n".join(lines)

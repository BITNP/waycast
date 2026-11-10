"""Wire protocol: the JSON frame envelope exchanged between modules and the Agent.

The wire protocol is transport-independent: it defines the JSON message
format (the envelope + typed payloads), and any transport (WebSocket by
default, HTTP/SSE later) can carry it.  A single multiplexed, full-duplex
Module connection carries every frame type, distinguished by the ``type``
field: capability advertisement, input, output_unit, result, status_query,
status_result.  A module may act as input, output, or both over the same
connection (A25).

The frame models here are the single authoritative shape of what crosses a
Module connection (ADR-0008).  ``waycast.protocols`` owns the payload models
(UnifiedInput / OutputUnit / OutputResult); this module wraps them in the
envelope and validates capability advertisements.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROTOCOL_VERSION = 1

FrameType = Literal[
    "capability",
    "input",
    "output_unit",
    "result",
    "status_query",
    "status_result",
]


class WireFrame(BaseModel):
    """The unified JSON envelope for every message on a Module connection.

    ``type`` selects the payload shape; ``module`` is the unique module name
    (validated against the capability advertisement on the hub side).
    ``request_id`` correlates status_query / status_result round-trips.
    """

    model_config = ConfigDict(extra="forbid")

    protocol_version: int = PROTOCOL_VERSION
    type: FrameType
    module: str
    request_id: str | None = Field(
        default=None,
        description="Correlation id for status_query/status_result round-trips",
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_version(self) -> WireFrame:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"unsupported protocol_version {self.protocol_version}; "
                f"expected {PROTOCOL_VERSION}"
            )
        return self


class InputCapability(BaseModel):
    """What an input module declares about itself."""

    model_config = ConfigDict(extra="forbid")
    description: str = ""


class OutputCapability(BaseModel):
    """What an output module declares about itself: the JSON Schema it accepts
    plus a semantic description of what accepting a unit does.

    The JSON field is ``schema`` (the wire protocol key); the Python
    attribute is ``json_schema`` to avoid shadowing ``BaseModel.schema``.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    json_schema: dict[str, Any] = Field(
        alias="schema", description="JSON Schema the module accepts"
    )
    description: str = ""


class StatusCapability(BaseModel):
    """Optional: a module advertises a status-query channel whose semantics are
    defined by the module itself.  When absent (or ``enabled=False``), the hub
    creates no status tool for this module (A19)."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    description: str = ""


class Capability(BaseModel):
    """The first frame a module sends after connecting: its capability
    advertisement (A13).  A module may declare itself as input, output, or
    both over the same connection (A25).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["input", "output", "both"]
    input: InputCapability | None = None
    output: OutputCapability | None = None
    status: StatusCapability | None = None

    @model_validator(mode="after")
    def _kind_matches_payloads(self) -> Capability:
        if self.kind in ("input", "both") and self.input is None:
            raise ValueError("kind declares input but no input capability given")
        if self.kind in ("output", "both") and self.output is None:
            raise ValueError("kind declares output but no output capability given")
        if self.kind == "input" and self.output is not None:
            raise ValueError("kind=input must not carry an output capability")
        if self.kind == "output" and self.input is not None:
            raise ValueError("kind=output must not carry an input capability")
        return self


def make_frame(
    frame_type: FrameType,
    module: str,
    payload: dict[str, Any] | None = None,
    *,
    request_id: str | None = None,
) -> WireFrame:
    """Build a WireFrame with the default protocol version."""

    return WireFrame(
        protocol_version=PROTOCOL_VERSION,
        type=frame_type,
        module=module,
        request_id=request_id,
        payload=payload or {},
    )


def parse_frame(raw: str | bytes | dict[str, Any]) -> WireFrame:
    """Parse and validate an incoming wire message.

    Raises ``WaycastError`` on malformed JSON, an unsupported envelope, or a
    bad protocol version so the hub can reject the frame (or, on the very
    first frame, close the connection).
    """
    from waycast.protocols import WaycastError

    data: dict[str, Any]
    if isinstance(raw, dict):
        data = raw
    else:
        # 非 str/bytes 的杂类型会在这里被 json.loads 抛错并收敛为 WaycastError。
        try:
            import json

            parsed = json.loads(raw)
        except Exception as exc:
            raise WaycastError(f"malformed wire frame: {exc}") from exc
        if not isinstance(parsed, dict):
            raise WaycastError("wire frame must be a JSON object")
        # 值层面的校验交给 WireFrame（pydantic），这里只做形状收窄。
        data = cast("dict[str, Any]", parsed)
    try:
        return WireFrame.model_validate(data)
    except Exception as exc:
        raise WaycastError(f"invalid wire frame: {exc}") from exc


__all__ = [
    "PROTOCOL_VERSION",
    "Capability",
    "InputCapability",
    "OutputCapability",
    "StatusCapability",
    "WireFrame",
    "make_frame",
    "parse_frame",
]

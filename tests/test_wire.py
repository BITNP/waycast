"""Wire protocol: capability advertisement, frame envelope, schema."""

from __future__ import annotations

import pytest

from waycast.protocols import OutputUnit, UnifiedInput, WaycastError
from waycast.wire import (
    PROTOCOL_VERSION,
    Capability,
    InputCapability,
    OutputCapability,
    StatusCapability,
    WireFrame,
    make_frame,
    parse_frame,
)


def test_unified_input_defaults():
    inp = UnifiedInput(content="hi", source="m")
    assert inp.metadata == {}
    assert inp.source == "m"


def test_output_unit_defaults():
    unit = OutputUnit(module="x")
    assert unit.payload == {}


def test_make_frame_default_version_and_payload():
    f = make_frame("input", "m", {"content": "go"})
    assert f.protocol_version == PROTOCOL_VERSION
    assert f.type == "input"
    assert f.module == "m"
    assert f.payload == {"content": "go"}


def test_parse_roundtrip():
    f = make_frame("output_unit", "bell", {"text": "hi"}, request_id="r1")
    parsed = parse_frame(f.model_dump_json())
    assert parsed.type == "output_unit"
    assert parsed.module == "bell"
    assert parsed.request_id == "r1"
    assert parsed.payload == {"text": "hi"}


def test_parse_from_dict():
    parsed = parse_frame(
        {"protocol_version": 1, "type": "input", "module": "m", "payload": {}}
    )
    assert parsed.type == "input"


def test_parse_rejects_wrong_protocol_version():
    with pytest.raises(WaycastError):
        parse_frame(
            {"protocol_version": 999, "type": "input", "module": "m", "payload": {}}
        )


def test_parse_rejects_bad_json():
    with pytest.raises(WaycastError):
        parse_frame("not json {")


def test_parse_rejects_unknown_type():
    with pytest.raises(WaycastError):
        parse_frame(
            {"protocol_version": 1, "type": "teleport", "module": "m", "payload": {}}
        )


def test_capability_requires_kind_consistency():
    with pytest.raises(Exception):
        Capability.model_validate(
            {"name": "m", "kind": "input"}
        )  # kind=input needs input cap
    with pytest.raises(Exception):
        # kind=input must not carry output cap
        Capability.model_validate(
            {
                "name": "m",
                "kind": "input",
                "input": {"description": "d"},
                "output": {"schema": {}, "description": "d"},
            }
        )


def test_capability_both_and_optional_status():
    cap = Capability.model_validate(
        {
            "name": "m",
            "kind": "both",
            "input": {"description": "in"},
            "output": {"schema": {"type": "object"}, "description": "out"},
            "status": {"enabled": True, "description": "liveness"},
        }
    )
    assert cap.kind == "both"
    assert cap.status is not None and cap.status.enabled
    assert cap.output.json_schema == {"type": "object"}


def test_status_optional_defaults_disabled():
    cap = Capability.model_validate(
        {"name": "m", "kind": "output", "output": {"schema": {}, "description": ""}}
    )
    assert cap.status is None

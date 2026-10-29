"""Capability catalog: upsert/remove, input/output/status views, schema."""
from __future__ import annotations

import json

from waycast.capabilities import CapabilityCatalog
from waycast.wire import Capability


def _cap(name="notify", kind="output", schema=None, status=False):
    payload = {"name": name, "kind": kind}
    if kind in ("input", "both"):
        payload["input"] = {"description": f"{name} input"}
    if kind in ("output", "both"):
        payload["output"] = {
            "schema": schema or {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
            "description": f"send {name}",
        }
    if status:
        payload["status"] = {"enabled": True, "description": "liveness"}
    return Capability.model_validate(payload)


def test_upsert_and_names():
    cat = CapabilityCatalog()
    cat.upsert(_cap("notify"))
    cat.upsert(_cap("log"))
    assert cat.names() == ["log", "notify"]
    assert cat.output_names() == ["log", "notify"]
    assert cat.input_names() == []


def test_upsert_replaces_same_name():
    cat = CapabilityCatalog()
    cat.upsert(_cap("notify"))
    cat.upsert(_cap("notify", status=True))
    assert len(cat.names()) == 1
    assert cat.status_tools() == [cat.get("notify")]


def test_remove():
    cat = CapabilityCatalog()
    cat.upsert(_cap("notify"))
    cat.remove("notify")
    assert cat.names() == []


def test_has_output_and_schema():
    cat = CapabilityCatalog()
    cat.upsert(_cap("notify"))
    assert cat.has_output("notify")
    assert cat.output_schema("notify")["required"] == ["message"]
    assert cat.output_schema("missing") is None


def test_cache_input_schema_validation():
    cat = CapabilityCatalog()
    echo = _cap(
        "echo",
        kind="both",
        schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
        status=True,
    )
    cat.upsert(echo)
    ep = cat.resolve_output("echo")
    assert ep is not None and ep.is_input and ep.is_output
    assert ep.status_enabled


def test_describe_output_modules_renders_schema_json():
    cat = CapabilityCatalog()
    cat.upsert(_cap("notify"))
    text = cat.describe_output_modules()
    assert "notify" in text
    assert json.loads(text.split("schema: ", 1)[1])["required"] == ["message"]


def test_describe_status_tools_only_when_enabled():
    cat = CapabilityCatalog()
    cat.upsert(_cap("plain"))
    cat.upsert(_cap("stat", status=True))
    text = cat.describe_status_tools()
    assert "status_stat" in text
    assert "status_plain" not in text

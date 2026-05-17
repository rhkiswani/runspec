"""
Tests for _build_schema — the function that converts a runspec runnable
definition into an emitted tool schema (MCP / OpenAI / Anthropic).
"""

from __future__ import annotations

from runspec.cli import _build_schema


def _script(output=None, **kwargs):
    base = {"autonomy": "confirm", "args": {}}
    if output is not None:
        base["output"] = output
    base.update(kwargs)
    return base


# ── x-output field ────────────────────────────────────────────────────────────


def test_x_output_defaults_to_text():
    schema = _build_schema("deploy", _script(), "mcp")
    assert schema["x-output"] == "text"


def test_x_output_text_explicit():
    schema = _build_schema("deploy", _script(output="text"), "mcp")
    assert schema["x-output"] == "text"


def test_x_output_json():
    schema = _build_schema("process", _script(output="json"), "mcp")
    assert schema["x-output"] == "json"


def test_x_output_html():
    schema = _build_schema("report", _script(output="html"), "mcp")
    assert schema["x-output"] == "html"


def test_x_output_present_in_all_formats():
    for fmt in ("mcp", "openai", "anthropic"):
        schema = _build_schema("run", _script(output="json"), fmt)
        assert schema["x-output"] == "json", f"missing x-output in {fmt} format"


# ── other schema fields unaffected ────────────────────────────────────────────


def test_schema_fields_present():
    schema = _build_schema("deploy", _script(description="Deploy app", output="json"), "mcp")
    assert schema["name"] == "deploy"
    assert schema["description"] == "Deploy app"
    assert schema["x-autonomy"] == "confirm"
    assert schema["x-output"] == "json"
    assert "inputSchema" in schema


def test_x_autonomy_reason_present_when_set():
    script = _script(output="text", autonomy_reason="irreversible")
    script["autonomy_reason"] = "irreversible"
    schema = _build_schema("deploy", script, "mcp")
    assert schema.get("x-autonomy-reason") == "irreversible"

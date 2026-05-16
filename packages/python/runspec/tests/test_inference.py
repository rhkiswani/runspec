"""
Tests for inference.py — the inference rules are the heart of runspec.
Every rule in SPEC.md must have a corresponding test here.
"""

import pytest

from runspec.inference import effective_autonomy, infer_arg, infer_script


class TestTypeInference:
    def test_int_from_int_default(self):
        result = infer_arg({"name": "workers", "default": 4})
        assert result["type"] == "int"

    def test_float_from_float_default(self):
        result = infer_arg({"name": "ratio", "default": 0.75})
        assert result["type"] == "float"

    def test_str_from_str_default(self):
        result = infer_arg({"name": "format", "default": "json"})
        assert result["type"] == "str"

    def test_flag_from_false_default(self):
        result = infer_arg({"name": "verbose", "default": False})
        assert result["type"] == "flag"

    def test_flag_from_true_default(self):
        result = infer_arg({"name": "dry_run", "default": True})
        assert result["type"] == "flag"

    def test_bool_is_checked_before_int(self):
        # bool is a subclass of int in Python — must be caught first
        result = infer_arg({"name": "flag", "default": False})
        assert result["type"] == "flag"
        assert result["type"] != "int"

    def test_choice_from_options(self):
        result = infer_arg({"name": "format", "options": ["json", "csv"]})
        assert result["type"] == "choice"

    def test_explicit_type_not_overridden(self):
        result = infer_arg({"name": "count", "type": "float", "default": 1})
        assert result["type"] == "float"

    def test_path_type_explicit(self):
        result = infer_arg({"name": "input", "type": "path"})
        assert result["type"] == "path"


class TestRequiredInference:
    def test_required_when_no_default(self):
        result = infer_arg({"name": "input", "type": "str"})
        assert result["required"] is True

    def test_not_required_when_default_present(self):
        result = infer_arg({"name": "workers", "default": 4})
        assert result["required"] is False

    def test_path_required_when_no_default(self):
        result = infer_arg({"name": "input", "type": "path"})
        assert result["required"] is True

    def test_explicit_required_not_overridden(self):
        result = infer_arg({"name": "input", "type": "str", "required": False})
        assert result["required"] is False

    def test_flag_not_required(self):
        result = infer_arg({"name": "verbose", "default": False})
        assert result["required"] is False


class TestChoiceValidation:
    def test_choice_without_options_raises(self):
        with pytest.raises(ValueError, match="no 'options' list"):
            infer_arg({"name": "mode", "type": "choice"})

    def test_choice_with_options_ok(self):
        result = infer_arg({"name": "mode", "type": "choice", "options": ["a", "b"]})
        assert result["type"] == "choice"
        assert result["options"] == ["a", "b"]


class TestScriptInference:
    def test_autonomy_inherited_from_config(self):
        raw = {
            "name": "greet",
            "description": "Greet",
            "autonomy": None,
            "autonomy_reason": None,
            "args": {},
            "groups": {},
            "commands": {},
        }
        result = infer_script(raw, config_autonomy="confirm")
        assert result["autonomy"] == "confirm"

    def test_script_autonomy_overrides_config(self):
        raw = {
            "name": "fetch",
            "description": "Fetch data",
            "autonomy": "autonomous",
            "autonomy_reason": None,
            "args": {},
            "groups": {},
            "commands": {},
        }
        result = infer_script(raw, config_autonomy="confirm")
        assert result["autonomy"] == "autonomous"

    def test_args_inferred_within_script(self):
        raw = {
            "name": "compress",
            "description": "Compress",
            "autonomy": None,
            "autonomy_reason": None,
            "args": {
                "quality": {"name": "quality", "default": 85},
                "verbose": {"name": "verbose", "default": False},
            },
            "groups": {},
            "commands": {},
        }
        result = infer_script(raw, config_autonomy="confirm")
        assert result["args"]["quality"]["type"] == "int"
        assert result["args"]["verbose"]["type"] == "flag"


class TestAutonomyEscalation:
    def test_no_escalation_when_no_arg_autonomy(self):
        result = effective_autonomy(
            script_autonomy="confirm",
            provided_args={"workers": 4},
            arg_specs={"workers": {"autonomy": None}},
        )
        assert result == "confirm"

    def test_arg_escalates_to_manual(self):
        result = effective_autonomy(
            script_autonomy="confirm",
            provided_args={"api_key": "sk-abc"},
            arg_specs={"api_key": {"autonomy": "manual"}},
        )
        assert result == "manual"

    def test_most_restrictive_wins(self):
        result = effective_autonomy(
            script_autonomy="autonomous",
            provided_args={"api_key": "sk-abc", "workers": 4},
            arg_specs={
                "api_key": {"autonomy": "manual"},
                "workers": {"autonomy": "confirm"},
            },
        )
        assert result == "manual"

    def test_none_arg_does_not_escalate(self):
        # arg declared but not provided — should not escalate
        result = effective_autonomy(
            script_autonomy="autonomous",
            provided_args={"api_key": None},
            arg_specs={"api_key": {"autonomy": "manual"}},
        )
        assert result == "autonomous"

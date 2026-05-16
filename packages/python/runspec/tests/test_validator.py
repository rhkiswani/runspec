"""
Tests for validator.py — two-pass validation: args then groups.
"""

import pytest

from runspec.errors import RunSpecError
from runspec.validator import raise_if_errors, validate_args, validate_groups


class TestArgValidation:
    def test_required_missing_produces_error(self):
        specs = {"input": {"name": "input", "type": "path", "required": True}}
        errors = validate_args({"input": None}, specs)
        assert len(errors) == 1
        assert "--input" in errors[0]

    def test_required_present_no_error(self):
        specs = {"input": {"name": "input", "type": "path", "required": True}}
        errors = validate_args({"input": "/tmp/data"}, specs)
        assert errors == []

    def test_optional_missing_no_error(self):
        specs = {"verbose": {"name": "verbose", "type": "flag", "required": False}}
        errors = validate_args({"verbose": None}, specs)
        assert errors == []

    def test_deprecated_arg_emits_warning(self):
        specs = {
            "threads": {
                "name": "threads",
                "type": "int",
                "required": False,
                "deprecated": "use --workers instead",
            }
        }
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            validate_args({"threads": 4}, specs)
            assert len(w) == 1
            assert "deprecated" in str(w[0].message).lower()


class TestGroupValidation:
    def test_exclusive_violation(self):
        groups = {
            "output": {
                "name": "output",
                "args": ["format", "raw"],
                "exclusive": True,
                "inclusive": False,
                "at_least_one": False,
                "exactly_one": False,
                "condition": None,
                "requires": [],
            }
        }
        errors = validate_groups({"format": "json", "raw": True}, groups)
        assert len(errors) == 1
        assert "output" in errors[0]

    def test_exclusive_ok_with_one(self):
        groups = {
            "output": {
                "name": "output",
                "args": ["format", "raw"],
                "exclusive": True,
                "inclusive": False,
                "at_least_one": False,
                "exactly_one": False,
                "condition": None,
                "requires": [],
            }
        }
        errors = validate_groups({"format": "json", "raw": None}, groups)
        assert errors == []

    def test_inclusive_violation(self):
        groups = {
            "auth": {
                "name": "auth",
                "args": ["username", "password"],
                "exclusive": False,
                "inclusive": True,
                "at_least_one": False,
                "exactly_one": False,
                "condition": None,
                "requires": [],
            }
        }
        errors = validate_groups({"username": "alice", "password": None}, groups)
        assert len(errors) == 1
        assert "auth" in errors[0]

    def test_at_least_one_violation(self):
        groups = {
            "input": {
                "name": "input",
                "args": ["file", "dir", "glob"],
                "exclusive": False,
                "inclusive": False,
                "at_least_one": True,
                "exactly_one": False,
                "condition": None,
                "requires": [],
            }
        }
        errors = validate_groups({"file": None, "dir": None, "glob": None}, groups)
        assert len(errors) == 1

    def test_exactly_one_violation_none_provided(self):
        groups = {
            "mode": {
                "name": "mode",
                "args": ["fast", "balanced", "quality"],
                "exclusive": False,
                "inclusive": False,
                "at_least_one": False,
                "exactly_one": True,
                "condition": None,
                "requires": [],
            }
        }
        errors = validate_groups({"fast": None, "balanced": None, "quality": None}, groups)
        assert len(errors) == 1

    def test_exactly_one_violation_two_provided(self):
        groups = {
            "mode": {
                "name": "mode",
                "args": ["fast", "balanced", "quality"],
                "exclusive": False,
                "inclusive": False,
                "at_least_one": False,
                "exactly_one": True,
                "condition": None,
                "requires": [],
            }
        }
        errors = validate_groups({"fast": True, "balanced": True, "quality": None}, groups)
        assert len(errors) == 1

    def test_conditional_group(self):
        groups = {
            "upload": {
                "name": "upload",
                "args": ["bucket", "region"],
                "exclusive": False,
                "inclusive": False,
                "at_least_one": False,
                "exactly_one": False,
                "condition": "upload",
                "requires": ["bucket", "region"],
            }
        }
        # upload provided but bucket and region missing
        errors = validate_groups({"upload": True, "bucket": None, "region": None}, groups)
        assert len(errors) == 1


class TestRaiseIfErrors:
    def test_raises_on_errors(self):
        with pytest.raises(RunSpecError):
            raise_if_errors(["error one", "error two"])

    def test_no_raise_on_empty(self):
        raise_if_errors([])  # should not raise

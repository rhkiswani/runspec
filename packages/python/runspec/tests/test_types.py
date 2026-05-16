"""
Tests for types.py — type registry and built-in Python coercers.
"""

from pathlib import Path

import pytest

from runspec.types import coerce, list_types, register_type


class TestBuiltinCoercers:
    def test_str_coercion(self):
        assert coerce("hello", {"type": "str", "name": "x"}) == "hello"

    def test_int_coercion(self):
        assert coerce("42", {"type": "int", "name": "x"}) == 42

    def test_int_coercion_from_int(self):
        assert coerce(42, {"type": "int", "name": "x"}) == 42

    def test_float_coercion(self):
        result = coerce("3.14", {"type": "float", "name": "x"})
        assert abs(result - 3.14) < 0.001

    def test_bool_true_variants(self):
        for val in ("true", "True", "TRUE", "1", "yes", "on"):
            assert coerce(val, {"type": "bool", "name": "x"}) is True

    def test_bool_false_variants(self):
        for val in ("false", "False", "FALSE", "0", "no", "off"):
            assert coerce(val, {"type": "bool", "name": "x"}) is False

    def test_flag_true(self):
        assert coerce(True, {"type": "flag", "name": "x"}) is True

    def test_flag_false(self):
        assert coerce(False, {"type": "flag", "name": "x"}) is False

    def test_path_coercion(self):
        result = coerce("/tmp", {"type": "path", "name": "x"})
        assert isinstance(result, Path)

    def test_choice_valid(self):
        spec = {"type": "choice", "name": "fmt", "options": ["json", "csv"]}
        assert coerce("json", spec) == "json"

    def test_choice_invalid(self):
        spec = {"type": "choice", "name": "fmt", "options": ["json", "csv"]}
        with pytest.raises(ValueError):
            coerce("xml", spec)


class TestRangeValidation:
    def test_int_within_range(self):
        spec = {"type": "int", "name": "quality", "range": (1, 100)}
        assert coerce("85", spec) == 85

    def test_int_below_range(self):
        spec = {"type": "int", "name": "quality", "range": (1, 100)}
        with pytest.raises(ValueError):
            coerce("0", spec)

    def test_int_above_range(self):
        spec = {"type": "int", "name": "quality", "range": (1, 100)}
        with pytest.raises(ValueError):
            coerce("101", spec)

    def test_float_range(self):
        spec = {"type": "float", "name": "ratio", "range": (0.0, 1.0)}
        assert coerce("0.5", spec) == 0.5


class TestCustomTypes:
    def test_register_and_use_custom_type(self):
        register_type("upper-str", lambda v, arg: str(v).upper())
        result = coerce("hello", {"type": "upper-str", "name": "x"})
        assert result == "HELLO"

    def test_unknown_type_raises(self):
        with pytest.raises(TypeError, match="Unknown type"):
            coerce("value", {"type": "nonexistent-type-xyz", "name": "x"})

    def test_list_types_includes_builtins(self):
        types = list_types()
        for t in ("str", "int", "float", "bool", "flag", "path", "choice"):
            assert t in types

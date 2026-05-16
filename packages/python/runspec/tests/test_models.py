"""
Tests for the Arg transparent value access protocol.

Arg wraps a resolved value and should behave like that value in expressions —
no .value unwrapping required by callers.
"""

from runspec.models import Arg


def arg(value, *, type="str", name="x"):
    """Minimal Arg constructor for tests."""
    return Arg(value=value, name=name, type=type)


class TestStringProtocol:
    def test_str(self):
        assert str(arg("hello")) == "hello"

    def test_repr(self):
        assert repr(arg("hello")) == "'hello'"

    def test_fstring_plain(self):
        a = arg("world")
        assert f"Hello, {a}!" == "Hello, world!"

    def test_fstring_format_spec(self):
        a = arg(3.14159, type="float")
        assert f"{a:.2f}" == "3.14"

    def test_fstring_alignment(self):
        a = arg("hi", type="str")
        assert f"{a:>10}" == "        hi"

    def test_fstring_int_format(self):
        a = arg(255, type="int")
        assert f"{a:#010x}" == "0x000000ff"


class TestNumericProtocol:
    def test_int(self):
        assert int(arg(4.9, type="float")) == 4

    def test_float(self):
        assert float(arg(3, type="int")) == 3.0

    def test_index_in_range(self):
        a = arg(3, type="int")
        assert list(range(a)) == [0, 1, 2]

    def test_index_in_list_slice(self):
        a = arg(2, type="int")
        assert [10, 20, 30, 40][a] == 30

    def test_addition(self):
        assert arg(3, type="int") + 2 == 5

    def test_radd(self):
        assert 2 + arg(3, type="int") == 5

    def test_subtraction(self):
        assert arg(10, type="int") - 3 == 7

    def test_multiplication(self):
        assert arg(4, type="int") * 3 == 12

    def test_rmul(self):
        assert 3 * arg(4, type="int") == 12

    def test_truediv(self):
        assert arg(10, type="float") / 4 == 2.5

    def test_floordiv(self):
        assert arg(10, type="int") // 3 == 3

    def test_mod(self):
        assert arg(10, type="int") % 3 == 1


class TestComparisonProtocol:
    def test_eq_to_native(self):
        assert arg(5, type="int") == 5

    def test_eq_to_arg(self):
        assert arg(5, type="int") == arg(5, type="int")

    def test_lt(self):
        assert arg(3, type="int") < 5

    def test_le(self):
        assert arg(5, type="int") <= 5

    def test_gt(self):
        assert arg(7, type="int") > 5

    def test_ge(self):
        assert arg(5, type="int") >= 5

    def test_comparison_returns_bool(self):
        result = arg(3, type="int") < 5
        assert type(result) is bool

    def test_eq_returns_bool(self):
        result = arg(3, type="int") == 3
        assert type(result) is bool


class TestBoolProtocol:
    def test_truthy_flag(self):
        assert bool(arg(True, type="flag")) is True

    def test_falsy_flag(self):
        assert bool(arg(False, type="flag")) is False

    def test_if_statement(self):
        a = arg(True, type="flag")
        triggered = False
        if a:
            triggered = True
        assert triggered


class TestIterationProtocol:
    def test_iter_on_list_value(self):
        a = arg(["a", "b", "c"], type="str")
        assert list(a) == ["a", "b", "c"]

    def test_len_on_list_value(self):
        a = arg(["x", "y"], type="str")
        assert len(a) == 2

    def test_len_on_string(self):
        assert len(arg("hello")) == 5

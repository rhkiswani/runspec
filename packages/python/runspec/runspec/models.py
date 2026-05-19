"""
Core data models for runspec.

Arg     — a single argument with value + full metadata
Group   — a relationship constraint between arguments
RunSpec — the full parsed result for a script
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass
class Arg:
    """
    A single parsed argument. Carries its resolved value alongside
    its full spec metadata so the parsed result is self-describing.

    Transparent value access — Arg behaves as its native type in
    expressions. args.workers + 1, if args.dry_run, str(args.format)
    all work without unwrapping.
    """

    # Resolved value — coerced to native type by the language pack
    value: Any

    # Spec metadata
    name: str
    type: str
    required: bool = False
    default: Any = None
    description: str | None = None
    options: list[Any] | None = None
    range: tuple[Any, Any] | None = None
    multiple: bool = False
    delimiter: str | None = None
    short: str | None = None
    env: str | None = None
    deprecated: str | None = None
    autonomy: str | None = None
    ui: str | None = None
    meta: dict[str, Any] | None = None

    # Resolution metadata
    source: str = "default"  # "cli" | "env" | "config" | "default"

    # ── Transparent value access ──────────────────────────────────────────────

    def __repr__(self) -> str:
        return repr(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return int(self.value)

    def __index__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    def __format__(self, spec: str) -> str:
        return format(self.value, spec)

    def __bool__(self) -> bool:
        return bool(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Arg):
            return bool(self.value == other.value)
        return bool(self.value == other)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Arg):
            return bool(self.value < other.value)
        return bool(self.value < other)

    def __le__(self, other: object) -> bool:
        if isinstance(other, Arg):
            return bool(self.value <= other.value)
        return bool(self.value <= other)

    def __gt__(self, other: object) -> bool:
        if isinstance(other, Arg):
            return bool(self.value > other.value)
        return bool(self.value > other)

    def __ge__(self, other: object) -> bool:
        if isinstance(other, Arg):
            return bool(self.value >= other.value)
        return bool(self.value >= other)

    def __add__(self, other: object) -> Any:
        if isinstance(other, Arg):
            return self.value + other.value
        return self.value + other

    def __radd__(self, other: object) -> Any:
        return other + self.value

    def __sub__(self, other: object) -> Any:
        if isinstance(other, Arg):
            return self.value - other.value
        return self.value - other

    def __rsub__(self, other: object) -> Any:
        return other - self.value

    def __mul__(self, other: object) -> Any:
        if isinstance(other, Arg):
            return self.value * other.value
        return self.value * other

    def __rmul__(self, other: object) -> Any:
        return other * self.value

    def __truediv__(self, other: object) -> Any:
        if isinstance(other, Arg):
            return self.value / other.value
        return self.value / other

    def __floordiv__(self, other: object) -> Any:
        if isinstance(other, Arg):
            return self.value // other.value
        return self.value // other

    def __mod__(self, other: object) -> Any:
        if isinstance(other, Arg):
            return self.value % other.value
        return self.value % other

    def __fspath__(self) -> str:
        return cast(str, os.fspath(self.value))

    def __hash__(self) -> int:
        return hash(self.value)

    def __getitem__(self, key: Any) -> Any:
        return self.value[key]

    def __iter__(self) -> Any:
        """Allow iteration when value is a list (multiple=true args)."""
        return iter(self.value)

    def __len__(self) -> int:
        return len(self.value)

    def __getattr__(self, name: str) -> Any:
        """
        Delegate attribute access to the value for types like pathlib.Path.
        This allows args.input.is_dir(), args.input.glob("*.jpg") etc.
        """
        # Avoid infinite recursion on dataclass internals
        if name.startswith("_") or name in self.__dataclass_fields__:
            raise AttributeError(name)
        return getattr(self.value, name)


@dataclass
class Group:
    """
    A relationship constraint between arguments.
    Validated in a second pass after individual arg validation.
    """

    name: str
    args: list[str]

    # Group type — exactly one of these will be set
    exclusive: bool = False  # at most one arg from the group
    inclusive: bool = False  # if any, then all
    at_least_one: bool = False  # one or more must be provided
    exactly_one: bool = False  # strictly one must be provided

    # Conditional — if `condition` arg is provided, `args` become required
    condition: str | None = None  # the triggering arg name


@dataclass
class RunSpec:
    """
    The full parsed result for a script invocation.

    Acts as a namespace — args are attributes, accessed as args.quality,
    args.input_dir etc. Hyphens in arg names become underscores.

    Also carries full spec metadata so it can be used as a source of
    truth for emit, describe, scaffold, and other future operations.
    """

    # Script identity
    __script__: str
    __source__: Path
    __command__: str | None = None  # active subcommand if any
    __autonomy__: str = "confirm"  # effective autonomy for this invocation
    __output__: str = "text"  # declared output format: "text" | "json" | "html"
    __agent__: bool = False  # True when called via runspec serve (RUNSPEC_AGENT=1)
    __spec__: dict[str, Any] = field(default_factory=dict)
    __groups__: list[Group] = field(default_factory=list)

    # Args are stored internally and exposed as attributes
    _args: dict[str, Arg] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Arg:
        """Access args as attributes: args.quality, args.input_dir."""
        try:
            args: dict[str, Arg] = object.__getattribute__(self, "_args")
            return args[name]
        except KeyError as err:
            raise AttributeError(f"No argument '{name}' in spec for '{self.__script__}'. Available: {', '.join(self._args.keys())}") from err

    def __repr__(self) -> str:
        args_repr = ", ".join(f"{k}={v.value!r}" for k, v in self._args.items())
        return f"RunSpec(script={self.__script__!r}, {args_repr})"

    def _set_arg(self, name: str, arg: Arg) -> None:
        """Internal: store an arg. Normalises hyphens to underscores."""
        normalised = name.replace("-", "_")
        self._args[normalised] = arg

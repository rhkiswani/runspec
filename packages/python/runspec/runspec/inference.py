"""
inference.py — Applies the runspec inference rules to raw arg definitions.

Inference rules (applied in order, per SPEC.md):
  default = <integer>              → type = "int"
  default = <float>                → type = "float"
  default = <string>               → type = "str"
  default = true / false           → type = "flag"
  options = [...] present          → type = "choice"
  no default + no required=false   → required = True
  type = "path" with no default    → required = True
"""

from __future__ import annotations

from typing import Any

# Valid autonomy levels
AUTONOMY_LEVELS = ("autonomous", "confirm", "supervised", "manual")
AUTONOMY_RANK = {level: i for i, level in enumerate(AUTONOMY_LEVELS)}


def infer_arg(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Apply inference rules to a normalised raw arg dict.
    Returns a new dict with all inferred fields filled in.
    """
    result = dict(raw)
    default = result.get("default")
    options = result.get("options")

    # ── Type inference ────────────────────────────────────────────────────────
    if result.get("type") is None:
        if options is not None:
            result["type"] = "choice"
        elif isinstance(default, bool):
            # bool must be checked before int — bool is a subclass of int
            result["type"] = "flag"
        elif isinstance(default, int):
            result["type"] = "int"
        elif isinstance(default, float):
            result["type"] = "float"
        elif isinstance(default, str):
            result["type"] = "str"
        else:
            # No default and no type — will be caught by required inference
            result["type"] = "str"

    # ── Required inference ────────────────────────────────────────────────────
    if result.get("required") is None:
        # Explicitly no default = required
        if default is None and result.get("type") != "flag" or result["type"] == "path" and default is None:
            result["required"] = True
        else:
            result["required"] = False

    # ── Choice options must be present for choice type ─────────────────────
    if result["type"] == "choice" and not options:
        raise ValueError(f"Argument '{raw.get('name', '?')}' has type 'choice' but no 'options' list was provided.")

    return result


def infer_script(raw_script: dict[str, Any], config_autonomy: str) -> dict[str, Any]:
    """
    Apply inference to a full script definition.
    Fills in autonomy, infers all args, recurses into commands.
    """
    result = dict(raw_script)

    # Autonomy falls back to config default
    if result.get("autonomy") is None:
        result["autonomy"] = config_autonomy

    # Infer all args
    result["args"] = {name: infer_arg(arg) for name, arg in result.get("args", {}).items()}

    # Recurse into subcommands
    result["commands"] = {cmd_name: infer_script(cmd_data, config_autonomy) for cmd_name, cmd_data in result.get("commands", {}).items()}

    return result


def effective_autonomy(
    script_autonomy: str,
    provided_args: dict[str, Any],
    arg_specs: dict[str, Any],
) -> str:
    """
    Calculate the effective autonomy for an invocation.

    The most restrictive level among the script autonomy and all
    per-arg autonomy declarations for args that were actually provided.

    Escalation rule: manual > supervised > confirm > autonomous
    """
    effective = script_autonomy

    for arg_name, value in provided_args.items():
        if value is None:
            continue
        arg_spec = arg_specs.get(arg_name, {})
        arg_autonomy = arg_spec.get("autonomy")
        if arg_autonomy and is_more_restrictive(arg_autonomy, effective):
            effective = arg_autonomy

    return effective


def is_more_restrictive(candidate: str, current: str) -> bool:
    """Return True if candidate is more restrictive than current."""
    return AUTONOMY_RANK.get(candidate, 0) > AUTONOMY_RANK.get(current, 0)

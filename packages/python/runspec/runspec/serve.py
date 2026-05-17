"""
serve.py — MCP stdio server for runspec.

Implements the Model Context Protocol over stdin/stdout (zero dependencies).
Protocol: https://github.com/modelcontextprotocol/specification
Version:  2024-11-05
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SPEC = "https://github.com/modelcontextprotocol/specification"

# Standard JSON-RPC 2.0 error codes
_ERR_PARSE = -32700
_ERR_METHOD_NOT_FOUND = -32601
_ERR_INVALID_PARAMS = -32602


def serve() -> None:
    """
    Start the runspec MCP stdio server.
    Reads JSON-RPC requests from stdin, writes responses to stdout.
    Runs until stdin closes.
    """
    from pathlib import Path as _Path

    from runspec.cli import _build_schema
    from runspec.finder import find_config
    from runspec.inference import infer_script
    from runspec.loader import load_raw

    try:
        config_path, fmt = find_config(_Path.cwd())
    except FileNotFoundError as e:
        sys.stderr.write(f"runspec serve: {e}\n")
        sys.stderr.flush()
        sys.exit(1)

    raw = load_raw(config_path, fmt)
    config = raw["config"]

    tools: dict[str, dict[str, Any]] = {}
    arg_specs: dict[str, dict[str, Any]] = {}

    for name, runnable in raw["runnables"].items():
        inferred = infer_script(runnable, config["autonomy_default"])
        tools[name] = _build_schema(name, inferred, "mcp")
        arg_specs[name] = inferred.get("args", {})

    scripts_dir = Path(sysconfig.get_path("scripts"))
    server_name = _server_name(config)

    _mcp_loop(tools, arg_specs, scripts_dir, server_name)


# ── MCP loop ──────────────────────────────────────────────────────────────────


def _mcp_loop(
    tools: dict[str, dict[str, Any]],
    arg_specs: dict[str, dict[str, Any]],
    scripts_dir: Path,
    server_name: str,
) -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": _ERR_PARSE, "message": "Parse error"}})
            continue

        response = _dispatch(request, tools, arg_specs, scripts_dir, server_name)
        if response is not None:
            _write(response)


def _dispatch(
    request: dict[str, Any],
    tools: dict[str, dict[str, Any]],
    arg_specs: dict[str, dict[str, Any]],
    scripts_dir: Path,
    server_name: str,
) -> dict[str, Any] | None:
    method = request.get("method", "")
    req_id = request.get("id")

    # Notifications have no id — no response
    if req_id is None:
        return None

    if method == "initialize":
        return _handle_initialize(req_id, server_name)
    if method == "tools/list":
        return _handle_tools_list(req_id, tools)
    if method == "tools/call":
        return _handle_tools_call(req_id, request.get("params", {}), tools, arg_specs, scripts_dir)

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": _ERR_METHOD_NOT_FOUND, "message": f"Method not found: {method}"}}


# ── Handlers ──────────────────────────────────────────────────────────────────


def _handle_initialize(req_id: Any, server_name: str) -> dict[str, Any]:
    from runspec import __version__

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": server_name, "version": __version__},
        },
    }


def _handle_tools_list(req_id: Any, tools: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"tools": list(tools.values())},
    }


def _handle_tools_call(
    req_id: Any,
    params: dict[str, Any],
    tools: dict[str, dict[str, Any]],
    arg_specs: dict[str, dict[str, Any]],
    scripts_dir: Path,
) -> dict[str, Any]:
    name = params.get("name", "")
    arguments = params.get("arguments") or {}

    if name not in tools:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": _ERR_INVALID_PARAMS, "message": f"Unknown tool: {name}"},
        }

    cmd = _find_script(name, scripts_dir)
    if cmd is None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Script not found in {scripts_dir}: {name}"}],
                "isError": True,
            },
        }

    argv = _args_to_argv(arguments, arg_specs.get(name, {}))
    env = {**os.environ, "RUNSPEC_AGENT": "1"}

    result = subprocess.run([str(cmd), *argv], capture_output=True, text=True, env=env)

    if result.returncode == 0:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result.stdout}],
                "isError": False,
            },
        }

    parts = [f"exit_code: {result.returncode}"]
    if result.stdout:
        parts.append(f"stdout:\n{result.stdout.rstrip()}")
    if result.stderr:
        parts.append(f"stderr:\n{result.stderr.rstrip()}")

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": "\n".join(parts)}],
            "isError": True,
        },
    }


# ── Arg translation ───────────────────────────────────────────────────────────


def _args_to_argv(arguments: dict[str, Any], arg_specs: dict[str, Any]) -> list[str]:
    """Translate MCP tool call arguments dict to a CLI argv list."""
    argv: list[str] = []

    for arg_name, spec in arg_specs.items():
        # Accept both hyphen and underscore forms from the caller
        value = arguments.get(arg_name)
        if value is None:
            value = arguments.get(arg_name.replace("-", "_"))
        if value is None:
            continue

        flag = f"--{arg_name}"
        arg_type = spec.get("type", "str")

        if arg_type == "flag":
            if value:
                argv.append(flag)
        elif spec.get("multiple") and isinstance(value, list):
            for item in value:
                argv.extend([flag, str(item)])
        else:
            argv.extend([flag, str(value)])

    return argv


# ── Helpers ───────────────────────────────────────────────────────────────────


def _find_script(name: str, scripts_dir: Path) -> Path | None:
    """Return the path to the named script in the venv scripts directory."""
    candidate = scripts_dir / name
    if candidate.exists():
        return candidate
    candidate_exe = scripts_dir / (name + ".exe")
    if candidate_exe.exists():
        return candidate_exe
    return None


def _server_name(config: dict[str, Any]) -> str:
    """Agent name: explicit config name, or the venv directory name."""
    name = config.get("name")
    if name and isinstance(name, str):
        return name
    return Path(sys.prefix).name


def _write(response: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()

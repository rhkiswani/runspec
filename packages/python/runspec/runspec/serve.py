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
import threading
import time
import uuid
from pathlib import Path
from typing import Any

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SPEC = "https://github.com/modelcontextprotocol/specification"

# Standard JSON-RPC 2.0 error codes
_ERR_PARSE = -32700
_ERR_METHOD_NOT_FOUND = -32601
_ERR_INVALID_PARAMS = -32602


def serve(registry_url: str | None = None, name: str | None = None) -> None:
    """
    Start the runspec MCP stdio server.
    Reads JSON-RPC requests from stdin, writes responses to stdout.
    Runs until stdin closes.
    """
    import signal

    from runspec.cli import _build_schema
    from runspec.finder import find_config
    from runspec.inference import infer_script
    from runspec.loader import load_raw

    try:
        config_path, fmt = find_config(Path.cwd())
    except FileNotFoundError as e:
        sys.stderr.write(f"runspec serve: {e}\n")
        sys.stderr.flush()
        sys.exit(1)

    raw = load_raw(config_path, fmt)
    config = raw["config"]

    tools: dict[str, dict[str, Any]] = {}
    arg_specs: dict[str, dict[str, Any]] = {}

    for rname, runnable in raw["runnables"].items():
        inferred = infer_script(runnable, config["autonomy_default"])
        tools[rname] = _build_schema(rname, inferred, "mcp")
        arg_specs[rname] = inferred.get("args", {})

    scripts_dir = Path(sysconfig.get_path("scripts"))

    # Resolve effective name and registry URL (CLI flags override config)
    effective_name = name or _server_name(config)
    effective_registry = registry_url or config.get("registry")

    if effective_registry:
        agent_id = str(uuid.uuid4())
        start_time = time.time()
        tools_list = list(tools.values())
        heartbeat_interval = config.get("heartbeat", 30)
        heartbeat_data_fields: list[str] = config.get("heartbeat_data", [])

        try:
            _registry_register(effective_registry, agent_id, effective_name, config["version"])
        except Exception as e:
            sys.stderr.write(f"runspec serve: registry register failed: {e}\n")
            sys.stderr.flush()

        def _on_sigterm(signum: int, frame: Any) -> None:
            try:
                _registry_deregister(effective_registry, agent_id)
            except Exception:
                pass
            sys.exit(0)

        signal.signal(signal.SIGTERM, _on_sigterm)

        def _heartbeat_loop() -> None:
            while True:
                time.sleep(heartbeat_interval)
                try:
                    status = _registry_heartbeat(
                        effective_registry, agent_id, heartbeat_data_fields, start_time
                    )
                    if status == "refresh":
                        _registry_tools(effective_registry, agent_id, tools_list)
                except Exception as e:
                    sys.stderr.write(f"runspec serve: heartbeat error: {e}\n")
                    sys.stderr.flush()

        threading.Thread(target=_heartbeat_loop, daemon=True).start()

    _mcp_loop(tools, arg_specs, scripts_dir, effective_name)


# ── Registry client ────────────────────────────────────────────────────────────


def _registry_register(base_url: str, agent_id: str, name: str, version: str) -> None:
    _registry_post(base_url, "/register", {
        "agent_id": agent_id,
        "name": name,
        "version": version,
        "tools_seq": 1,
    })


def _registry_heartbeat(
    base_url: str,
    agent_id: str,
    heartbeat_data_fields: list[str],
    start_time: float,
) -> str:
    body: dict[str, Any] = {"agent_id": agent_id, "tools_seq": 1}
    if "system" in heartbeat_data_fields:
        body["system"] = {"pid": os.getpid(), "uptime": int(time.time() - start_time)}
    resp = _registry_post(base_url, "/heartbeat", body)
    return resp.get("status", "ack")


def _registry_tools(base_url: str, agent_id: str, tools_list: list[dict[str, Any]]) -> None:
    _registry_post(base_url, "/tools", {
        "agent_id": agent_id,
        "tools_seq": 1,
        "tools": tools_list,
    })


def _registry_deregister(base_url: str, agent_id: str) -> None:
    _registry_post(base_url, "/deregister", {"agent_id": agent_id})


def _registry_post(base_url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + path
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} from {url}: {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"Request to {url} failed: {e}") from e


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

"""
serve.py — MCP stdio server for runspec.

Implements the Model Context Protocol over stdin/stdout (zero dependencies).
Protocol: https://github.com/modelcontextprotocol/specification
Version:  2024-11-05
"""

from __future__ import annotations

import json
import os
import re
import socket
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


def serve(
    registry_url: str | None = None,
    name: str | None = None,
    registry_key: str | None = None,
    registry_cert: str | None = None,
    dev: bool = False,
) -> None:
    """
    Start the runspec MCP stdio server.
    Reads JSON-RPC requests from stdin, writes responses to stdout.
    Runs until stdin closes.
    """
    import signal

    from runspec.finder import find_config, find_configs_dev
    from runspec.inference import infer_script
    from runspec.loader import load_raw

    hostname = socket.gethostname()
    scripts_dir = Path(sysconfig.get_path("scripts"))

    tools: dict[str, dict[str, Any]] = {}
    arg_specs: dict[str, dict[str, Any]] = {}
    exec_specs: dict[str, dict[str, Any]] = {}

    if dev:
        config_paths = find_configs_dev(Path.cwd())
        if not config_paths:
            sys.stderr.write("runspec serve --dev: No runspec.toml files found (looked for them under the nearest .git root)\n")
            sys.stderr.flush()
            sys.exit(1)

        config = load_raw(config_paths[0])["config"]
        all_runnables: dict[str, Any] = {}
        for cp in config_paths:
            extra = load_raw(cp)
            for rname, rdata in extra["runnables"].items():
                if rname in all_runnables:
                    sys.stderr.write(f"runspec serve --dev: warning: '{rname}' defined in multiple TOML files, keeping first\n")
                    sys.stderr.flush()
                else:
                    all_runnables[rname] = rdata

        effective_registry: str | None = None  # registry disabled in --dev mode
    else:
        try:
            config_path = find_config(Path.cwd())
        except FileNotFoundError as e:
            sys.stderr.write(f"runspec serve: {e}\n")
            sys.stderr.flush()
            sys.exit(1)

        raw = load_raw(config_path)
        config = raw["config"]
        all_runnables = raw["runnables"]
        effective_registry = registry_url or config.get("registry")

    for rname, runnable in all_runnables.items():
        # Skip tools restricted to other hosts
        allowed_hosts = runnable.get("hosts")
        if allowed_hosts and hostname not in allowed_hosts:
            continue

        # Validate run_as patterns — exit with a clear error rather than silently misbehaving
        pattern_errors = _validate_run_as_patterns(runnable.get("run_as"))
        if pattern_errors:
            for err in pattern_errors:
                sys.stderr.write(f"runspec serve: {rname}.run_as: {err}\n")
            sys.stderr.flush()
            sys.exit(1)

        inferred = infer_script(runnable, config["autonomy_default"])
        base_cmd = _find_script(rname, scripts_dir)
        run_as = _resolve_run_as(runnable.get("run_as"), hostname)
        become_method = runnable.get("become_method", "sudo")
        become_flags = runnable.get("become_flags")

        for flat_name, schema, arg_spec, exec_spec in _expand_tools(rname, inferred, base_cmd, run_as, become_method, become_flags):
            tools[flat_name] = schema
            arg_specs[flat_name] = arg_spec
            exec_specs[flat_name] = exec_spec

    effective_name = name or _server_name(config)

    if effective_registry:
        agent_id = str(uuid.uuid4())
        start_time = time.time()
        tools_list = _build_registry_tools_list(tools, exec_specs)
        heartbeat_interval = config.get("heartbeat", 30)
        heartbeat_data_fields: list[str] = config.get("heartbeat_data", [])

        try:
            _registry_register(
                effective_registry,
                agent_id,
                effective_name,
                config["version"],
                hostname,
                registry_key,
                registry_cert,
            )
            _registry_tools(effective_registry, agent_id, tools_list, registry_key, registry_cert)
        except Exception as e:
            sys.stderr.write(f"runspec serve: registry register failed: {e}\n")
            sys.stderr.flush()

        def _on_sigterm(signum: int, frame: Any) -> None:
            import contextlib

            with contextlib.suppress(Exception):
                _registry_deregister(effective_registry, agent_id, registry_key, registry_cert)
            sys.exit(0)

        signal.signal(signal.SIGTERM, _on_sigterm)

        def _heartbeat_loop() -> None:
            while True:
                time.sleep(heartbeat_interval)
                try:
                    status = _registry_heartbeat(
                        effective_registry,
                        agent_id,
                        heartbeat_data_fields,
                        start_time,
                        registry_key,
                        registry_cert,
                    )
                    if status == "refresh":
                        _registry_tools(effective_registry, agent_id, tools_list, registry_key, registry_cert)
                except Exception as e:
                    sys.stderr.write(f"runspec serve: heartbeat error: {e}\n")
                    sys.stderr.flush()

        threading.Thread(target=_heartbeat_loop, daemon=True).start()

    _mcp_loop(tools, arg_specs, exec_specs, effective_name)


# ── Registry client ────────────────────────────────────────────────────────────


def _registry_register(
    base_url: str,
    agent_id: str,
    name: str,
    version: str,
    host: str,
    api_key: str | None = None,
    cert: str | None = None,
) -> None:
    _registry_request(
        base_url,
        "/instances",
        {
            "instance_id": agent_id,
            "name": name,
            "version": version,
            "host": host,
        },
        api_key=api_key,
        cert=cert,
    )


def _registry_heartbeat(
    base_url: str,
    agent_id: str,
    heartbeat_data_fields: list[str],
    start_time: float,
    api_key: str | None = None,
    cert: str | None = None,
) -> str:
    body: dict[str, Any] = {}
    if "system" in heartbeat_data_fields:
        body["system"] = {"pid": os.getpid(), "uptime": int(time.time() - start_time)}
    resp = _registry_request(base_url, f"/instances/{agent_id}/heartbeat", body, api_key=api_key, cert=cert)
    return str(resp.get("status", "ack"))


def _registry_tools(
    base_url: str,
    agent_id: str,
    tools_list: list[dict[str, Any]],
    api_key: str | None = None,
    cert: str | None = None,
) -> None:
    _registry_request(
        base_url,
        f"/instances/{agent_id}/tools",
        {
            "tools": tools_list,
        },
        api_key=api_key,
        cert=cert,
    )


def _registry_deregister(
    base_url: str,
    agent_id: str,
    api_key: str | None = None,
    cert: str | None = None,
) -> None:
    _registry_request(base_url, f"/instances/{agent_id}", {}, method="DELETE", api_key=api_key, cert=cert)


def _registry_request(
    base_url: str,
    path: str,
    body: dict[str, Any],
    *,
    method: str = "POST",
    api_key: str | None = None,
    cert: str | None = None,
) -> dict[str, Any]:
    import ssl
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + path
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    payload = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    ctx = ssl.create_default_context(cafile=cert) if cert else None
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} from {url}: {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"Request to {url} failed: {e}") from e


# ── Registry tool list builder ────────────────────────────────────────────────


def _build_registry_tools_list(
    tools: dict[str, dict[str, Any]],
    exec_specs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Augment MCP tool schemas with execution metadata for the registry."""
    result = []
    for name, schema in tools.items():
        entry = dict(schema)
        spec = exec_specs.get(name, {})
        cmd = spec.get("command")
        entry["x-command"] = cmd[-1] if cmd else name
        entry["x-run-as"] = spec.get("run_as", "")
        entry["x-become-method"] = spec.get("become_method", "sudo")
        if spec.get("become_flags"):
            entry["x-become-flags"] = spec["become_flags"]
        result.append(entry)
    return result


# ── MCP loop ──────────────────────────────────────────────────────────────────


def _mcp_loop(
    tools: dict[str, dict[str, Any]],
    arg_specs: dict[str, dict[str, Any]],
    exec_specs: dict[str, dict[str, Any]],
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

        response = _dispatch(request, tools, arg_specs, exec_specs, server_name)
        if response is not None:
            _write(response)


def _dispatch(
    request: dict[str, Any],
    tools: dict[str, dict[str, Any]],
    arg_specs: dict[str, dict[str, Any]],
    exec_specs: dict[str, dict[str, Any]],
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
        return _handle_tools_call(req_id, request.get("params", {}), tools, arg_specs, exec_specs)

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
    exec_specs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    name = params.get("name", "")
    arguments = params.get("arguments") or {}

    if name not in tools:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": _ERR_INVALID_PARAMS, "message": f"Unknown tool: {name}"},
        }

    cmd: list[str] | None = exec_specs.get(name, {}).get("command")
    if cmd is None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Script '{name}' not found. Install it in the venv (production) or place it alongside runspec.toml (--dev mode)."}],
                "isError": True,
            },
        }

    tool_arg_specs = arg_specs.get(name, {})
    argv = _args_to_argv(arguments, tool_arg_specs)

    from runspec.run import _args_to_runspec_env

    runspec_env = _args_to_runspec_env(arguments, tool_arg_specs)
    env = {**os.environ, "RUNSPEC_AGENT": "1", **runspec_env}

    result = subprocess.run([*cmd, *argv], capture_output=True, text=True, env=env)

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


# ── run_as helpers ────────────────────────────────────────────────────────────


def _resolve_run_as(run_as_spec: Any, hostname: str) -> str:
    """Resolve run_as to a plain string for the current host."""
    if run_as_spec is None:
        return ""

    # Simple string or $ENV_VAR reference
    if isinstance(run_as_spec, str):
        if run_as_spec.startswith("$"):
            return os.environ.get(run_as_spec[1:], "")
        return run_as_spec

    # Table form: hosts / patterns / default
    if isinstance(run_as_spec, dict):
        hosts = run_as_spec.get("hosts", {})
        if hostname in hosts:
            return str(hosts[hostname])

        for pattern, user in run_as_spec.get("patterns", {}).items():
            if re.fullmatch(pattern, hostname):
                return str(user)

        return str(run_as_spec.get("default", ""))

    return ""


def _validate_run_as_patterns(run_as_spec: Any) -> list[str]:
    """Return a list of error messages for any invalid regex patterns."""
    if not isinstance(run_as_spec, dict):
        return []

    errors: list[str] = []
    for pattern in run_as_spec.get("patterns", {}):
        try:
            re.compile(pattern)
        except re.error as e:
            errors.append(f"invalid pattern '{pattern}': {e}")
    return errors


# ── Helpers ───────────────────────────────────────────────────────────────────


def _expand_tools(
    name: str,
    inferred: dict[str, Any],
    base_cmd: list[str] | None,
    run_as: str | None,
    become_method: str,
    become_flags: str | None,
) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """Expand a runnable into flat MCP tool entries, recursing into subcommands.

    A runnable with no commands yields one entry (name, schema, arg_spec, exec_spec).
    A runnable with commands yields one entry per leaf subcommand, with underscore-joined
    names and the subcommand path prepended to base_cmd.
    e.g. portal_api.commands.orders_endpoint.commands.get_list →
         name="portal_api_orders_endpoint_get_list",
         base_cmd=["/path/to/portal_api", "orders_endpoint", "get_list"]
    """
    from runspec.cli import _build_schema

    commands = inferred.get("commands") or {}
    if commands:
        result: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for sub_name, sub_spec in commands.items():
            result.extend(
                _expand_tools(
                    f"{name}_{sub_name}",
                    sub_spec,
                    [*(base_cmd or []), sub_name],
                    run_as,
                    become_method,
                    become_flags,
                )
            )
        return result
    return [
        (
            name,
            _build_schema(name, inferred, "mcp"),
            inferred.get("args", {}),
            {
                "command": base_cmd,
                "run_as": run_as,
                "become_method": become_method,
                "become_flags": become_flags,
            },
        )
    ]


def _find_script(name: str, scripts_dir: Path) -> list[str] | None:
    """Return a command list for the named script, or None if not found.

    Looks only in the venv scripts dir — tools must be installed (pip install -e .).
    """
    for ext in ("", ".exe"):
        candidate = scripts_dir / (name + ext)
        if candidate.is_file():
            return [str(candidate)]
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

"""
run.py — Remote tool execution for runspec.

Remote mode : queries the registry for per-host metadata, SSHes via Paramiko.

Paramiko is optional: pip install runspec[run]
"""

from __future__ import annotations

import shlex
import sys
import threading
from typing import Any

# ── Public entry points ───────────────────────────────────────────────────────


def run_remote(
    tool_name: str,
    tool_args: list[str],
    host: str,
    registry_url: str,
    ssh_user: str | None = None,
    ssh_key: str | None = None,
    no_host_key_check: bool = False,
    api_key: str | None = None,
    cert: str | None = None,
) -> int:
    """Run a tool on a remote host via SSH, using registry metadata."""
    host_data = _fetch_registry_host(registry_url, tool_name, host, api_key, cert)
    command = host_data.get("x-command") or tool_name
    run_as = host_data.get("x-run-as") or None
    become_method = host_data.get("x-become-method") or "sudo"
    become_flags = host_data.get("x-become-flags") or None
    remote_cmd = _build_remote_command(command, tool_args, run_as, become_method, become_flags)
    return _ssh_exec(host, ssh_user, ssh_key, remote_cmd, no_host_key_check)



def list_registry_tools(registry_url: str, api_key: str | None = None, cert: str | None = None) -> list[dict[str, Any]]:
    """Return tools from the registry, with host list."""
    data = _http_get(f"{registry_url.rstrip('/')}/tools", api_key, cert)
    return [
        {
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "hosts": [h["host"] for h in t.get("hosts", [])],
        }
        for t in data
    ]


# ── Internal helpers ──────────────────────────────────────────────────────────



def _fetch_registry_host(
    base_url: str,
    tool_name: str,
    host: str,
    api_key: str | None,
    cert: str | None,
) -> dict[str, Any]:
    """Return the per-host execution entry for a tool from the registry."""
    data: dict[str, Any] = _http_get(f"{base_url.rstrip('/')}/tools/{tool_name}", api_key, cert)
    for host_entry in data.get("hosts", []):
        if host_entry.get("host") == host:
            return dict(host_entry)
    sys.stderr.write(f"✗  Host '{host}' not found for tool '{tool_name}' in registry\n")
    sys.exit(1)


def _http_get(url: str, api_key: str | None, cert: str | None) -> Any:
    """HTTP GET with optional API key header and CA certificate."""
    import json
    import ssl
    import urllib.request

    ctx: ssl.SSLContext | None = None
    if cert:
        ctx = ssl.create_default_context(cafile=cert)

    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-API-Key", api_key)

    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        sys.stderr.write(f"✗  Registry returned {e.code}: {body}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"✗  Could not reach registry at {url}: {e.reason}\n")
        sys.exit(1)


def _arg_name_to_env_key(name: str) -> str:
    """Convert an arg name to its RUNSPEC_* environment variable key.

    dry-run → RUNSPEC_DRY_RUN
    input_file → RUNSPEC_INPUT_FILE
    """
    return "RUNSPEC_" + name.upper().replace("-", "_")


def _args_to_runspec_env(arguments: dict[str, Any], arg_specs: dict[str, Any]) -> dict[str, str]:
    """Convert a resolved arguments dict to RUNSPEC_* environment variables.

    Accepts values from arguments; falls back to spec defaults. Bool/flag
    types serialise as "1" or "0". Multiple-value args serialise as
    newline-delimited strings. Everything else is str().
    """
    env_vars: dict[str, str] = {}
    for arg_name, spec in arg_specs.items():
        value = arguments.get(arg_name)
        if value is None:
            value = arguments.get(arg_name.replace("-", "_"))
        if value is None:
            value = spec.get("default")
        if value is None:
            continue

        env_key = _arg_name_to_env_key(arg_name)
        arg_type = spec.get("type", "str")

        if arg_type in ("bool", "flag"):
            env_vars[env_key] = "1" if value else "0"
        elif spec.get("multiple") and isinstance(value, list):
            env_vars[env_key] = "\n".join(str(v) for v in value)
        else:
            env_vars[env_key] = str(value)

    return env_vars



def _parse_argv_to_dict(argv: list[str], arg_specs: dict[str, Any]) -> dict[str, Any]:
    """Parse a --flag-name [value] list into a dict, using arg_specs to detect flag types."""
    result: dict[str, Any] = {}
    i = 0
    while i < len(argv):
        token = argv[i]
        if not token.startswith("--"):
            i += 1
            continue
        arg_name = token[2:]
        spec = arg_specs.get(arg_name) or arg_specs.get(arg_name.replace("-", "_")) or {}
        arg_type = spec.get("type", "str")

        if arg_type == "flag":
            result[arg_name] = True
            i += 1
        elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            if spec.get("multiple"):
                result.setdefault(arg_name, []).append(argv[i + 1])
            else:
                result[arg_name] = argv[i + 1]
            i += 2
        else:
            i += 1
    return result


def _build_remote_command(
    command: str,
    args: list[str],
    run_as: str | None,
    become_method: str,
    become_flags: str | None,
) -> str:
    """Build the full remote command string with privilege escalation."""
    quoted_cmd = shlex.quote(command)
    quoted_args = " ".join(shlex.quote(a) for a in args)
    payload = f"{quoted_cmd} {quoted_args}".strip()

    if not run_as:
        return payload

    flags_part = f" {become_flags}" if become_flags else ""
    if become_method == "su":
        return f"su{flags_part} -c {shlex.quote(payload)} {shlex.quote(run_as)}"
    # sudo, pbrun, dzdo all take -u <user>
    return f"{become_method}{flags_part} -u {shlex.quote(run_as)} {payload}"


def _ssh_exec(
    host: str,
    user: str | None,
    key_file: str | None,
    command: str,
    no_host_key_check: bool,
) -> int:
    """SSH to host, run command, stream stdout/stderr. Returns exit code."""
    try:
        import paramiko  # type: ignore[import-untyped]
    except ImportError:
        sys.stderr.write("✗  Paramiko is required for remote execution.\n")
        sys.stderr.write("   Install it with: pip install 'runspec[run]'\n")
        sys.exit(1)

    client = paramiko.SSHClient()
    if no_host_key_check:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

    connect_kwargs: dict[str, Any] = {}
    if user:
        connect_kwargs["username"] = user
    if key_file:
        connect_kwargs["key_filename"] = key_file

    try:
        client.connect(host, **connect_kwargs)
    except Exception as e:
        sys.stderr.write(f"✗  SSH connection to {host} failed: {e}\n")
        sys.exit(1)

    try:
        _, stdout, stderr = client.exec_command(command)
        channel = stdout.channel

        def _pipe(src: Any, dst: Any) -> None:
            for chunk in src:
                dst.write(chunk)
                dst.flush()

        t1 = threading.Thread(target=_pipe, args=(stdout, sys.stdout.buffer))
        t2 = threading.Thread(target=_pipe, args=(stderr, sys.stderr.buffer))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        return int(channel.recv_exit_status())
    finally:
        client.close()

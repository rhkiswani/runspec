"""
jump.py — SSH+MCP client for runspec jump.

Connects to a configured jump host via SSH subprocess, starts 'runspec serve'
on the remote, and communicates via JSON-RPC stdio (MCP 2024-11-05).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


def ssh_cmd(host_cfg: dict[str, Any]) -> list[str]:
    """Build the SSH command list to start runspec serve on the remote.

    Argv order matters — OpenSSH uses first-value-wins for command-line
    options, so the structure is:

        ssh -o BatchMode=yes        ← always; locked because stdin is JSON-RPC
            [-F /dev/null]          ← when use-ssh-config = false
            [-p PORT] [-i KEY]      ← explicit fields next (highest precedence)
            [-o OPT]...             ← ssh-options pass-through (lowest precedence)
            user@host bin serve
    """
    cmd = ["ssh", "-o", "BatchMode=yes"]

    if not host_cfg.get("use_ssh_config", True):
        cmd += ["-F", "/dev/null"]

    if host_cfg.get("port") and host_cfg["port"] != 22:
        cmd += ["-p", str(host_cfg["port"])]
    if host_cfg.get("ssh_key"):
        cmd += ["-i", host_cfg["ssh_key"]]

    for opt in host_cfg.get("ssh_options") or []:
        cmd += ["-o", str(opt)]

    host = host_cfg["host"]
    target = f"{host_cfg['user']}@{host}" if host_cfg.get("user") else host
    cmd.append(target)

    bin_path = host_cfg.get("bin") or os.environ.get("RUNSPEC_JUMP_BIN") or "runspec"
    cmd.append(bin_path)
    cmd.append("serve")
    return cmd


def _open_session(host_cfg: dict[str, Any]) -> subprocess.Popen[bytes]:
    """Open an SSH+MCP session. Exits on connection failure."""
    cmd = ssh_cmd(host_cfg)
    try:
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
        )
    except FileNotFoundError:
        sys.stderr.write("✗  ssh not found — install OpenSSH\n")
        sys.exit(1)


def _send(proc: subprocess.Popen[bytes], msg: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()


def _recv(proc: subprocess.Popen[bytes]) -> dict[str, Any]:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        _report_remote_failure(proc)
    return json.loads(line.decode())  # type: ignore[no-any-return]


def _report_remote_failure(proc: subprocess.Popen[bytes]) -> None:
    """The remote produced no MCP response — figure out why and report cleanly."""
    try:
        exit_code = proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        exit_code = None  # still alive but stdout closed — unusual

    if exit_code == 255:
        # OpenSSH conventional exit code for connection / authentication failure
        sys.stderr.write("✗  SSH connection failed (see error above for details).\n")
    elif exit_code is not None and exit_code != 0:
        sys.stderr.write(
            f"✗  Remote command failed (exit {exit_code}) before the MCP handshake completed.\n"
            "   Common cause: `runspec` is not on the remote shell's PATH.\n"
            '   Fix: set `bin = "/full/path/to/runspec"` in [config.jump-hosts.<alias>],\n'
            "   or export RUNSPEC_JUMP_BIN in your local shell.\n"
            "   (SSH commands run in a non-login shell and don't source ~/.bashrc / ~/.profile.)\n"
        )
    else:
        sys.stderr.write("✗  Remote MCP server closed stdout unexpectedly\n")
    sys.exit(1)


def _close(proc: subprocess.Popen[bytes]) -> None:
    if proc.stdin:
        proc.stdin.close()
    proc.wait()


def _initialize(proc: subprocess.Popen[bytes]) -> None:
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "runspec-jump", "version": "1.0"},
            },
        },
    )
    _recv(proc)
    # Notification: no id, no response expected
    _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})


def list_tools(host_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """List tools available on a jump host via SSH+MCP."""
    proc = _open_session(host_cfg)
    try:
        _initialize(proc)
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        resp = _recv(proc)
        return resp.get("result", {}).get("tools", [])  # type: ignore[no-any-return]
    finally:
        _close(proc)


def call_tool(host_cfg: dict[str, Any], tool_name: str, tool_argv: list[str]) -> None:
    """Call a tool on a jump host via SSH+MCP, streaming text output to stdout."""
    proc = _open_session(host_cfg)
    try:
        _initialize(proc)
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_resp = _recv(proc)
        tools = tools_resp.get("result", {}).get("tools", [])
        schema = next((t for t in tools if t["name"] == tool_name), None)
        if schema is None:
            sys.stderr.write(f"✗  Tool '{tool_name}' not found on remote\n")
            sys.exit(1)

        arguments = parse_tool_argv(tool_argv, schema)
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
        call_resp = _recv(proc)
        if "error" in call_resp:
            sys.stderr.write(f"✗  {call_resp['error'].get('message', 'Remote error')}\n")
            sys.exit(1)
        for block in call_resp.get("result", {}).get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                sys.stdout.write(text)
                if not text.endswith("\n"):
                    sys.stdout.write("\n")
    finally:
        _close(proc)


def parse_tool_argv(argv: list[str], schema: dict[str, Any]) -> dict[str, Any]:
    """Parse --flag [value] argv into a call arguments dict using the tool's JSON Schema.

    serve.py maps runspec 'flag' and 'bool' types to JSON Schema 'boolean'.
    """
    props = schema.get("inputSchema", {}).get("properties", {})
    result: dict[str, Any] = {}
    i = 0
    while i < len(argv):
        token = argv[i]
        if not token.startswith("--"):
            i += 1
            continue
        arg_name = token[2:]
        prop = props.get(arg_name, {})
        if prop.get("type") == "boolean":
            result[arg_name] = True
            i += 1
        elif i + 1 < len(argv):
            result[arg_name] = argv[i + 1]
            i += 2
        else:
            sys.stderr.write(f"✗  --{arg_name} requires a value\n")
            sys.exit(1)
    return result

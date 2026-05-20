"""
jump.py — SSH+MCP client for runspec jump.

Connects to a configured jump host via SSH subprocess, starts 'runspec serve'
on the remote, and communicates via JSON-RPC stdio (MCP 2024-11-05).
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def ssh_cmd(host_cfg: dict[str, Any]) -> list[str]:
    """Build the SSH command list to start runspec serve on the remote."""
    cmd = ["ssh", "-o", "BatchMode=yes"]
    if host_cfg.get("port") and host_cfg["port"] != 22:
        cmd += ["-p", str(host_cfg["port"])]
    if host_cfg.get("ssh_key"):
        cmd += ["-i", host_cfg["ssh_key"]]
    host = host_cfg["host"]
    target = f"{host_cfg['user']}@{host}" if host_cfg.get("user") else host
    cmd.append(target)
    cmd.append(host_cfg.get("bin", "runspec"))
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
        sys.stderr.write("✗  Remote MCP server closed unexpectedly\n")
        sys.exit(1)
    return json.loads(line.decode())  # type: ignore[no-any-return]


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

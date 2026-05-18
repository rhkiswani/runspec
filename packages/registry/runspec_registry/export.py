"""
export.py — Generate connection database files for SSH clients.

Supported formats:
  SuperPuTTY  — XML sessions file (.xml)
  MobaXterm   — sessions file (.mxtsessions)
"""

from __future__ import annotations

import html
from typing import Any


def _xml_tag(tag: str, content: str, indent: int = 4) -> str:
    pad = " " * indent
    return f"{pad}<{tag}>{html.escape(content)}</{tag}>"


def generate_superputty(hosts: list[dict[str, Any]], default_user: str = "") -> str:
    """
    Generate a SuperPuTTY sessions XML file from a list of host records.

    Each record must have at least 'host' and 'name' keys.
    Returns the XML string.
    """
    ns = "http://schemas.datacontract.org/2004/07/SuperPuTTY"
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<ArrayOfSessionData xmlns="{ns}" xmlns:i="http://www.w3.org/2001/XMLSchema-instance">',
    ]

    for entry in hosts:
        host = entry.get("host", "")
        name = entry.get("name", host)
        lines.append("  <SessionData>")
        lines.append(_xml_tag("Host", host))
        lines.append(_xml_tag("Port", "22"))
        lines.append(_xml_tag("Proto", "SSH"))
        lines.append(_xml_tag("PuttySession", "Default Settings"))
        lines.append(_xml_tag("SessionId", f"runspec/{name}/{host}"))
        lines.append(_xml_tag("SessionName", f"{name} ({host})"))
        lines.append(_xml_tag("Username", default_user))
        lines.append("  </SessionData>")

    lines.append("</ArrayOfSessionData>")
    return "\n".join(lines)


def generate_mobaxterm(hosts: list[dict[str, Any]], default_user: str = "") -> str:
    """
    Generate a MobaXterm .mxtsessions file from a list of host records.

    The format is a simple INI-like text file that MobaXterm can import.
    Returns the file content as a string.
    """
    lines = ["[Bookmarks]", "SubRep=runspec", "ImgNum=42", ""]

    for entry in hosts:
        host = entry.get("host", "")
        name = entry.get("name", host)
        user = default_user or ""
        # MobaXterm SSH session format: name =#109#0#host#port#user#...
        lines.append(f"{name} ({host}) =#109#0#{host}#22#{user}##-1#0#0#0#1080##0#0#0#-1#0#0#0#0")

    return "\n".join(lines) + "\n"

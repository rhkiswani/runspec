"""
Tests for SuperPuTTY and MobaXterm export functions.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from runspec_registry.export import generate_mobaxterm, generate_superputty

HOSTS = [
    {"host": "logserver-01", "name": "log-agent"},
    {"host": "dbserver-02", "name": "db-agent"},
]


# ── SuperPuTTY ────────────────────────────────────────────────────────────────


def test_superputty_is_valid_xml() -> None:
    xml = generate_superputty(HOSTS)
    root = ET.fromstring(xml)
    assert root is not None


def test_superputty_contains_all_hosts() -> None:
    xml = generate_superputty(HOSTS)
    root = ET.fromstring(xml)
    ns = "http://schemas.datacontract.org/2004/07/SuperPuTTY"
    sessions = root.findall(f"{{{ns}}}SessionData")
    assert len(sessions) == 2


def test_superputty_host_values() -> None:
    xml = generate_superputty(HOSTS)
    root = ET.fromstring(xml)
    ns = "http://schemas.datacontract.org/2004/07/SuperPuTTY"
    sessions = root.findall(f"{{{ns}}}SessionData")
    hosts_in_xml = [s.findtext(f"{{{ns}}}Host") for s in sessions]
    assert "logserver-01" in hosts_in_xml
    assert "dbserver-02" in hosts_in_xml


def test_superputty_sets_username() -> None:
    xml = generate_superputty(HOSTS, default_user="jason")
    root = ET.fromstring(xml)
    ns = "http://schemas.datacontract.org/2004/07/SuperPuTTY"
    sessions = root.findall(f"{{{ns}}}SessionData")
    for s in sessions:
        assert s.findtext(f"{{{ns}}}Username") == "jason"


def test_superputty_empty_hosts() -> None:
    xml = generate_superputty([])
    root = ET.fromstring(xml)
    ns = "http://schemas.datacontract.org/2004/07/SuperPuTTY"
    assert root.findall(f"{{{ns}}}SessionData") == []


# ── MobaXterm ─────────────────────────────────────────────────────────────────


def test_mobaxterm_contains_bookmarks_header() -> None:
    content = generate_mobaxterm(HOSTS)
    assert "[Bookmarks]" in content


def test_mobaxterm_contains_all_hosts() -> None:
    content = generate_mobaxterm(HOSTS)
    assert "logserver-01" in content
    assert "dbserver-02" in content


def test_mobaxterm_sets_username() -> None:
    content = generate_mobaxterm(HOSTS, default_user="oracle")
    assert "#oracle#" in content


def test_mobaxterm_empty_hosts() -> None:
    content = generate_mobaxterm([])
    assert "[Bookmarks]" in content


def test_mobaxterm_ends_with_newline() -> None:
    content = generate_mobaxterm(HOSTS)
    assert content.endswith("\n")

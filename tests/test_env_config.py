"""Tests for the .env-backed UDP target resolution (persistence/env.py).

The UDP/JSON output reads its destination from `OPENFOV_UDP_TARGET`, which
may be set directly in the environment or loaded from a `.env` file. Real
environment variables always win over `.env` file contents.
"""

from __future__ import annotations

from openfov.persistence.env import (
    DEFAULT_UDP_TARGET,
    load_dotenv,
    parse_udp_target,
    udp_target,
)


def test_parse_full_udp_url() -> None:
    assert parse_udp_target("udp://127.0.0.1:4242") == ("127.0.0.1", 4242)


def test_parse_bare_host_port() -> None:
    """A bare host:port (no scheme) is accepted too."""
    assert parse_udp_target("192.168.1.50:9000") == ("192.168.1.50", 9000)


def test_udp_target_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENFOV_UDP_TARGET", "udp://10.0.0.1:5005")
    assert udp_target() == ("10.0.0.1", 5005)


def test_udp_target_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("OPENFOV_UDP_TARGET", raising=False)
    monkeypatch.delenv("OPENFOV_DOTENV", raising=False)
    assert udp_target() == DEFAULT_UDP_TARGET


def test_load_dotenv_populates_environ(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\nOPENFOV_UDP_TARGET=udp://203.0.113.7:7777\n\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENFOV_UDP_TARGET", raising=False)
    load_dotenv(env_file)
    assert udp_target() == ("203.0.113.7", 7777)


def test_real_env_wins_over_dotenv(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENFOV_UDP_TARGET=udp://1.1.1.1:1111\n", encoding="utf-8")
    monkeypatch.setenv("OPENFOV_UDP_TARGET", "udp://2.2.2.2:2222")
    load_dotenv(env_file)
    # The real environment value must not be clobbered by the file.
    assert udp_target() == ("2.2.2.2", 2222)

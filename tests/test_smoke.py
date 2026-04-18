"""Smoke tests for the step-A scaffold.

Real tests land with the step-B implementation.
"""
from click.testing import CliRunner

from paircode import __version__
from paircode.cli import main


def test_version_flag_prints_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_flag_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for subcmd in ("status", "install-claude", "install-codex", "handshake", "focus", "stage"):
        assert subcmd in result.output


def test_bare_invocation_prints_scaffold_notice():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "step-A scaffold" in result.output

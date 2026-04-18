"""paircode CLI entry point.

Scaffold only — real command implementations land in step B.
Current scope: --help, --version, and a placeholder for every subcommand
we know we'll need. Subcommands print "not yet implemented" so the CLI
contract is visible even before implementation lands.
"""
from __future__ import annotations

import click

from paircode import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="paircode")
@click.pass_context
def main(ctx: click.Context) -> None:
    """paircode — adversarial journey framework for LLM peer review.

    Run with no subcommand to bootstrap .paircode/ in the current directory
    (once implemented). Run with a subcommand to act on an existing .paircode/.
    """
    if ctx.invoked_subcommand is None:
        click.echo(
            "paircode v{} — step-A scaffold only. Run --help to see planned "
            "subcommands.".format(__version__)
        )


@main.command()
def status() -> None:
    """Summarize the current .paircode/ state: active focus, roster, iteration count."""
    click.echo("status: not yet implemented (step B)")


@main.command("install-claude")
def install_claude() -> None:
    """Install paircode as a Claude Code slash command in this project or globally."""
    click.echo("install-claude: not yet implemented (step B)")


@main.command("install-codex")
def install_codex() -> None:
    """Register paircode with Codex CLI for peer invocation."""
    click.echo("install-codex: not yet implemented (step B)")


@main.command()
def handshake() -> None:
    """Detect installed LLM CLIs, ping each, propose a peer roster."""
    click.echo("handshake: not yet implemented (step B)")


@main.command()
@click.argument("focus_name", required=False)
def focus(focus_name: str | None) -> None:
    """Open a new focus inside .paircode/ (or list existing focuses)."""
    click.echo(f"focus {focus_name or ''}: not yet implemented (step B)")


@main.command()
@click.argument("stage", type=click.Choice(["research", "plan", "execute"]))
def stage(stage: str) -> None:
    """Run one round of peer review at the given stage of the active focus."""
    click.echo(f"stage {stage}: not yet implemented (step B)")


if __name__ == "__main__":
    main()

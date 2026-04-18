"""paircode CLI entry point.

Subcommands:
  install     — register /paircode in all detected LLM CLIs (Claude, Codex, Gemini)
  uninstall   — remove paircode entries from those CLIs (idempotent)
  handshake   — list detected CLIs, no install
  status      — summarize current .paircode/ state (step B)
  init        — bootstrap .paircode/ in cwd (step B)
  focus       — open/list focuses (step B)
  stage       — run one peer-review round at a stage (step B)
  drive       — high-level workflow driver: topic → research → plan → execute (step B)
"""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from paircode import __version__
from paircode.detect import detect_all
from paircode.installer import install_all, uninstall_all
from paircode.state import (
    find_paircode,
    init_paircode,
    open_focus,
    read_peers,
)


console = Console()


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="paircode")
@click.pass_context
def main(ctx: click.Context) -> None:
    """paircode — adversarial journey framework for LLM peer review.

    Run `paircode install` to register /paircode in your LLM CLIs.
    Run `paircode drive "<topic>"` to kick off a research → plan → execute loop.
    Run `paircode --help` for the full command list.
    """
    if ctx.invoked_subcommand is None:
        console.print(f"[bold]paircode[/bold] v{__version__}")
        console.print("Run [cyan]paircode --help[/cyan] to see available commands.")
        console.print(
            "First-time setup: [cyan]paircode install[/cyan] "
            "(registers /paircode in Claude, Codex, Gemini)."
        )


@main.command()
def install() -> None:
    """Install /paircode slash command into every detected LLM CLI (global scope)."""
    console.print("[bold]Installing paircode into detected LLM CLIs...[/bold]\n")
    results = install_all()
    table = Table(show_header=True, header_style="bold")
    table.add_column("CLI")
    table.add_column("Action")
    table.add_column("Details")
    for r in results:
        color = {"installed": "green", "skipped": "yellow", "failed": "red"}.get(r.action, "white")
        table.add_row(r.cli_name, f"[{color}]{r.action}[/{color}]", r.message)
    console.print(table)
    installed = sum(1 for r in results if r.action == "installed")
    skipped = sum(1 for r in results if r.action == "skipped")
    failed = sum(1 for r in results if r.action == "failed")
    console.print(
        f"\n[bold]Summary:[/bold] {installed} installed, {skipped} skipped, {failed} failed."
    )
    if installed > 0:
        console.print(
            "\nTry it: open Claude Code in any project and run [cyan]/paircode[/cyan]."
        )


@main.command()
def uninstall() -> None:
    """Remove /paircode from every LLM CLI config dir (idempotent)."""
    console.print("[bold]Uninstalling paircode from LLM CLIs...[/bold]\n")
    results = uninstall_all()
    for r in results:
        console.print(f"  [dim]{r.cli_name}:[/dim] {r.message}")


@main.command()
def handshake() -> None:
    """List detected LLM CLIs without installing anything."""
    detected = detect_all()
    table = Table(show_header=True, header_style="bold")
    table.add_column("CLI")
    table.add_column("Installed")
    table.add_column("Binary")
    table.add_column("Config dir")
    for name, info in detected.items():
        status = "[green]yes[/green]" if info.installed else "[red]no[/red]"
        binary = str(info.binary_path) if info.binary_path else "[dim]—[/dim]"
        table.add_row(name, status, binary, str(info.config_dir))
    console.print(table)


@main.command()
def status() -> None:
    """Summarize the current .paircode/ state (walks up from cwd)."""
    state = find_paircode()
    if state is None:
        console.print(
            "[yellow]No .paircode/ found in cwd or any parent. "
            "Run [cyan]paircode init[/cyan] to bootstrap.[/yellow]"
        )
        return
    console.print(f"[bold].paircode/[/bold] at [cyan]{state.root}[/cyan]")
    console.print(f"  project root: {state.project_root}")
    console.print(f"  focuses:      {state.focus_count}")
    if state.active_focus:
        console.print(f"  active focus: [green]{state.active_focus.name}[/green]")
    peers = read_peers(state)
    console.print(f"  peers:        {len(peers)} configured")
    if peers:
        ptable = Table(show_header=True, header_style="bold")
        ptable.add_column("id")
        ptable.add_column("cli")
        ptable.add_column("mode")
        ptable.add_column("priority")
        for p in peers:
            ptable.add_row(
                str(p.get("id", "?")),
                str(p.get("cli", "?")),
                str(p.get("mode", "?")),
                str(p.get("priority", "?")),
            )
        console.print(ptable)
    if state.focus_dirs:
        ftable = Table(show_header=True, header_style="bold")
        ftable.add_column("#")
        ftable.add_column("focus")
        for i, d in enumerate(state.focus_dirs, 1):
            ftable.add_row(str(i), d.name)
        console.print(ftable)


@main.command()
@click.option("--force", is_flag=True, help="Overwrite an existing .paircode/ dir")
def init(force: bool) -> None:
    """Bootstrap .paircode/ in the current directory."""
    try:
        state = init_paircode(force=force)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(
        f"[green]✓[/green] Initialized [cyan]{state.root}[/cyan]\n"
        f"  wrote {state.journey_path.name}\n"
        f"  wrote {state.peers_path.name}\n"
        "\nNext: [cyan]paircode handshake[/cyan] to detect LLM CLIs and propose a peer roster,"
        "\nor [cyan]paircode focus <name>[/cyan] to open your first focus."
    )


@main.command()
@click.argument("name", required=False)
@click.option("--prompt", "-p", default=None, help="One-line focus prompt (freeform)")
def focus(name: str | None, prompt: str | None) -> None:
    """Open a new focus, or list existing focuses if no name given."""
    state = find_paircode()
    if state is None:
        console.print(
            "[red]No .paircode/ found.[/red] Run [cyan]paircode init[/cyan] first."
        )
        return
    if not name:
        if not state.focus_dirs:
            console.print("[yellow]No focuses yet.[/yellow]")
            return
        for d in state.focus_dirs:
            marker = "→" if d == state.active_focus else " "
            console.print(f"  {marker} {d.name}")
        return
    try:
        focus_dir = open_focus(state, name, prompt=prompt)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(f"[green]✓[/green] Opened focus [cyan]{focus_dir.name}[/cyan]")
    console.print(f"  Edit: [dim]{focus_dir}/FOCUS.md[/dim]")


@main.command()
@click.argument("stage_name", type=click.Choice(["research", "plan", "execute"]))
def stage(stage_name: str) -> None:
    """Run one peer-review round at a stage (not yet implemented — step B)."""
    console.print(f"[yellow]stage {stage_name}: not yet implemented (step B)[/yellow]")


@main.command()
@click.argument("topic")
def drive(topic: str) -> None:
    """High-level loop: open a focus on <topic>, run research → plan → execute."""
    console.print(f"[yellow]drive {topic!r}: not yet implemented (step B/M3)[/yellow]")


if __name__ == "__main__":
    main()

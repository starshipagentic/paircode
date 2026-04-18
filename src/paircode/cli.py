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

import re

import click
from rich.console import Console
from rich.table import Table

from paircode import __version__
from paircode.detect import detect_all
from paircode.drive import drive_full, drive_research, run_stage
from paircode.handshake import propose_roster, proposed_as_yaml_dicts
from paircode.installer import install_all, uninstall_all
from paircode.journey import note_focus_opened
from paircode.seal import discover_latest_versions, seal_stage
from paircode.state import (
    find_paircode,
    init_paircode,
    open_focus,
    read_peers,
    write_peers,
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
@click.option("--write", is_flag=True, help="Write proposed roster to .paircode/peers.yaml")
def handshake(write: bool) -> None:
    """List detected LLM CLIs and propose a peer roster.

    Without --write, just shows what was detected and what roster would be proposed.
    With --write, saves the proposed roster to .paircode/peers.yaml (requires init first).
    """
    detected = detect_all()
    dtable = Table(title="Detected CLIs", show_header=True, header_style="bold")
    dtable.add_column("CLI")
    dtable.add_column("Installed")
    dtable.add_column("Binary")
    for name, info in detected.items():
        status = "[green]yes[/green]" if info.installed else "[red]no[/red]"
        binary = str(info.binary_path) if info.binary_path else "[dim]—[/dim]"
        dtable.add_row(name, status, binary)
    console.print(dtable)

    proposed = propose_roster()
    if not proposed:
        console.print(
            "\n[yellow]No peers detected (only alpha is available). Install "
            "codex/gemini/ollama to add peer voices.[/yellow]"
        )
        return

    ptable = Table(title="Proposed peer roster", show_header=True, header_style="bold")
    ptable.add_column("id")
    ptable.add_column("cli")
    ptable.add_column("mode")
    ptable.add_column("priority")
    ptable.add_column("notes")
    for p in proposed:
        ptable.add_row(p.id, p.cli, p.mode, p.priority, p.notes)
    console.print(ptable)

    if write:
        state = find_paircode()
        if state is None:
            console.print(
                "[red]No .paircode/ found.[/red] Run [cyan]paircode init[/cyan] first, then rerun."
            )
            return
        write_peers(state, proposed_as_yaml_dicts(proposed))
        console.print(
            f"\n[green]✓[/green] Wrote roster to [cyan]{state.peers_path}[/cyan]"
        )
    else:
        console.print(
            "\n[dim]Run `paircode handshake --write` to save this roster to "
            ".paircode/peers.yaml[/dim]"
        )


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
        ftable.add_column("research")
        ftable.add_column("plan")
        ftable.add_column("execute")
        for i, d in enumerate(state.focus_dirs, 1):
            per_stage_cols = []
            for stage in ("research", "plan", "execute"):
                stage_dir = d / stage
                if not stage_dir.exists():
                    per_stage_cols.append("[dim]—[/dim]")
                    continue
                latest = discover_latest_versions(stage_dir)
                if not latest:
                    per_stage_cols.append("[dim]empty[/dim]")
                    continue
                final_count = sum(
                    1 for pid in latest if (stage_dir / f"{pid}-FINAL.md").exists()
                )
                v_max = max(
                    int(re.search(r"v(\d+)", p.name).group(1))  # type: ignore[union-attr]
                    for p in latest.values()
                )
                sealed_note = f" ([green]{final_count} sealed[/green])" if final_count else ""
                per_stage_cols.append(f"v{v_max}{sealed_note}")
            ftable.add_row(str(i), d.name, *per_stage_cols)
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
    note_focus_opened(state, focus_dir.name)
    console.print(f"[green]✓[/green] Opened focus [cyan]{focus_dir.name}[/cyan]")
    console.print(f"  Edit: [dim]{focus_dir}/FOCUS.md[/dim]")


@main.command()
@click.argument("stage_name", type=click.Choice(["research", "plan", "execute"]))
def seal(stage_name: str) -> None:
    """Seal the given stage on the active focus: copy each peer's latest version to {peer}-FINAL.md."""
    state = find_paircode()
    if state is None or state.active_focus is None:
        console.print(
            "[red]No active focus.[/red] Run [cyan]paircode focus <name>[/cyan] first."
        )
        return
    stage_dir = state.active_focus / stage_name
    if not stage_dir.exists():
        console.print(f"[red]Stage dir not found: {stage_dir}[/red]")
        return
    sealed = seal_stage(stage_dir)
    if not sealed:
        console.print(
            f"[yellow]No versioned files found in {stage_dir} — nothing to seal.[/yellow]"
        )
        return
    for s in sealed:
        console.print(
            f"  [green]✓[/green] {s.peer_id}: {s.source.name} → [cyan]{s.final.name}[/cyan]"
        )


@main.command()
@click.argument("stage_name", type=click.Choice(["research", "plan", "execute"]))
@click.option("--rounds", default=1, show_default=True, help="Rounds to run (round 1 = cold v1; 2+ = review+revise)")
@click.option("--alpha-cli", default="claude", show_default=True)
@click.option("--alpha-model", default=None)
@click.option("--timeout", default=600, show_default=True)
def stage(stage_name: str, rounds: int, alpha_cli: str, alpha_model: str | None, timeout: int) -> None:
    """Run a peer-review stage on the active focus for N rounds."""
    from paircode.state import find_paircode

    state = find_paircode()
    if state is None or state.active_focus is None:
        console.print("[red]No active focus.[/red] Run [cyan]paircode focus <name>[/cyan] first.")
        return
    focus_dir = state.active_focus
    focus_md = focus_dir / "FOCUS.md"
    topic = focus_md.read_text(encoding="utf-8") if focus_md.exists() else focus_dir.name

    console.print(
        f"[bold]stage[/bold] {stage_name} × {rounds} rounds on [cyan]{focus_dir.name}[/cyan]"
    )
    results = run_stage(
        topic=topic,
        focus_dir=focus_dir,
        stage=stage_name,  # type: ignore[arg-type]
        rounds=rounds,
        alpha_cli=alpha_cli,
        alpha_model=alpha_model,
        timeout_s=timeout,
        state=state,
    )
    _render_stage_results(stage_name, results)


def _render_stage_results(stage_name: str, results) -> None:
    for sr in results:
        console.print(f"\n[bold]round {sr.version}[/bold] ({stage_name})")
        table = Table(show_header=True, header_style="bold")
        table.add_column("kind")
        table.add_column("peer")
        table.add_column("cli")
        table.add_column("ok")
        table.add_column("duration")
        if sr.peer_results:
            for r in sr.peer_results:
                status = "[green]✓[/green]" if r.ok else "[red]✗[/red]"
                table.add_row("cold", r.peer_id, r.cli, status, f"{r.duration_s:.1f}s")
        if sr.review_results:
            for r in sr.review_results:
                status = "[green]✓[/green]" if r.ok else "[red]✗[/red]"
                table.add_row("review", r.peer_id, r.cli, status, f"{r.duration_s:.1f}s")
        if sr.alpha_revision:
            r = sr.alpha_revision
            status = "[green]✓[/green]" if r.ok else "[red]✗[/red]"
            table.add_row("revise", r.peer_id, r.cli, status, f"{r.duration_s:.1f}s")
        console.print(table)


@main.command()
@click.argument("topic")
@click.option(
    "--alpha-cli",
    default="claude",
    show_default=True,
    help="Which LLM CLI acts as alpha (the primary developer)",
)
@click.option("--alpha-model", default=None, help="Model string for alpha (CLI default if omitted)")
@click.option("--timeout", default=600, show_default=True, help="Per-peer timeout in seconds")
@click.option(
    "--research-rounds",
    default=2,
    show_default=True,
    help="Rounds in research stage (1 = cold only, 2+ = with reviews)",
)
@click.option("--plan-rounds", default=2, show_default=True)
@click.option("--execute-rounds", default=1, show_default=True)
@click.option(
    "--research-only",
    is_flag=True,
    help="Stop after research stage (for quick iteration / cost control)",
)
def drive(
    topic: str,
    alpha_cli: str,
    alpha_model: str | None,
    timeout: int,
    research_rounds: int,
    plan_rounds: int,
    execute_rounds: int,
    research_only: bool,
) -> None:
    """Full loop: open focus, run research → plan → execute with peer review."""
    console.print(f"[bold]paircode drive[/bold] topic=[cyan]{topic}[/cyan]")
    console.print(
        f"  alpha = {alpha_cli} ({alpha_model or 'default model'}), timeout = {timeout}s"
    )
    if research_only:
        console.print(
            f"  [dim]research-only mode, rounds = {research_rounds}[/dim]"
        )
        stage_results = drive_research(
            topic=topic,
            alpha_cli=alpha_cli,
            alpha_model=alpha_model,
            timeout_s=timeout,
            rounds=research_rounds,
        )
        _render_stage_results("research", stage_results)
        console.print(
            f"\n[bold]Research stage complete.[/bold] "
            f"Files at [cyan].paircode/{stage_results[0].focus_dir.name}/research/[/cyan]"
        )
        return

    console.print(
        f"  [dim]research={research_rounds}r, plan={plan_rounds}r, "
        f"execute={execute_rounds}r (this can take a while)[/dim]"
    )
    all_results = drive_full(
        topic=topic,
        alpha_cli=alpha_cli,
        alpha_model=alpha_model,
        timeout_s=timeout,
        research_rounds=research_rounds,
        plan_rounds=plan_rounds,
        execute_rounds=execute_rounds,
    )
    for stage_name, stage_results in all_results.items():
        _render_stage_results(stage_name, stage_results)
    first_focus = next(iter(all_results.values()))[0].focus_dir
    console.print(
        f"\n[bold green]Drive complete.[/bold green] Focus: [cyan]{first_focus.name}[/cyan]"
    )


if __name__ == "__main__":
    main()

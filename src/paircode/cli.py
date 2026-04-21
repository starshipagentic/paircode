"""paircode CLI — thin helpers the team-lead slash command calls.

Arch B (v0.11+): orchestration lives in the slash command installed inside
each LLM CLI. This binary exposes only the mechanical helpers the team lead
needs: scaffold, focus creation, roster listing, peer invocation, plus the
one-time `install` / `uninstall` lifecycle.

Subcommands:
  install          — register /paircode in every detected LLM CLI
  uninstall        — remove /paircode from LLM CLIs (idempotent)
  ensure-scaffold  — idempotent init + handshake, silent on success
  focus new <slug> — create a new focus dir, print its path
  focus active     — print the active focus path
  roster           — print peer ids, one per line
  invoke <id> <p>  — run one peer CLI, write output file-trace to --out
  (bare)           — print current state (what `status` used to do)
"""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from paircode import __version__
from paircode.handshake import propose_roster, proposed_as_yaml_dicts
from paircode.installer import install_all, uninstall_all
from paircode.runner import run_peer
from paircode.state import (
    ensure_peer_dirs,
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
    """paircode — adversarial multi-LLM peer review.

    Orchestration runs inside the /paircode slash command of whichever LLM CLI
    you invoked it from. This binary is the helper layer the team lead calls.

    First-time setup: `paircode install` registers /paircode in Claude, Codex, Gemini.
    """
    if ctx.invoked_subcommand is None:
        _show_state()


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------

@main.command()
def install() -> None:
    """Install /paircode slash command into every detected LLM CLI."""
    console.print("[bold]Installing paircode into detected LLM CLIs...[/bold]\n")
    results = install_all()
    table = Table(show_header=True, header_style="bold")
    table.add_column("CLI")
    table.add_column("Action")
    table.add_column("Details")
    for r in results:
        color = {"installed": "green", "skipped": "yellow",
                 "failed": "red", "already": "cyan"}.get(r.action, "white")
        table.add_row(r.cli_name, f"[{color}]{r.action}[/{color}]", r.message)
    console.print(table)
    installed = sum(1 for r in results if r.action == "installed")
    skipped = sum(1 for r in results if r.action == "skipped")
    failed = sum(1 for r in results if r.action == "failed")
    already = sum(1 for r in results if r.action == "already")
    console.print(
        f"\n[bold]Summary:[/bold] {installed} installed, {already} already, "
        f"{skipped} skipped, {failed} failed."
    )


@main.command()
def uninstall() -> None:
    """Remove /paircode from every LLM CLI config dir (idempotent)."""
    console.print("[bold]Uninstalling paircode from LLM CLIs...[/bold]\n")
    results = uninstall_all()
    for r in results:
        console.print(f"  [dim]{r.cli_name}:[/dim] {r.message}")


# ---------------------------------------------------------------------------
# Scaffold — idempotent init + handshake
# ---------------------------------------------------------------------------

@main.command(name="ensure-scaffold")
def ensure_scaffold() -> None:
    """Idempotent: init .paircode/ if missing, run handshake if peers empty.

    Silent on success. Prints one line per action taken (init, handshake).
    The team-lead slash command calls this before every focus.
    """
    state = find_paircode()
    did_init = False
    if state is None:
        state = init_paircode()
        did_init = True

    peers = read_peers(state)
    proposed_count = 0
    if not peers:
        proposed = propose_roster()
        if proposed:
            write_peers(state, proposed_as_yaml_dicts(proposed))
            peers = proposed_as_yaml_dicts(proposed)
            proposed_count = len(proposed)

    # Always reconcile sandbox dirs with the roster-of-record (peers.yaml).
    # Idempotent via mkdir(exist_ok=True); recreates any missing peer sandbox.
    # Without this, roster peers added after first init (or dropped by a rename)
    # never get their sandbox dir back.
    ensure_peer_dirs(state, peers)

    if did_init:
        click.echo(f"init {state.root}")
    if proposed_count:
        click.echo(f"handshake wrote {proposed_count} peers to {state.peers_path}")


# ---------------------------------------------------------------------------
# Focus — new / active
# ---------------------------------------------------------------------------

@main.group()
def focus() -> None:
    """Focus commands (new, active)."""


@focus.command("new")
@click.argument("slug")
@click.option("--prompt", default=None, help="One-line focus prompt to embed in FOCUS.md")
def focus_new(slug: str, prompt: str | None) -> None:
    """Create a new focus dir, print its path to stdout."""
    state = find_paircode()
    if state is None:
        state = init_paircode()
    try:
        focus_dir = open_focus(state, slug, prompt=prompt)
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(focus_dir))


@focus.command("active")
def focus_active() -> None:
    """Print the most recent focus path, or exit 1 if none exists."""
    state = find_paircode()
    if state is None or state.active_focus is None:
        raise click.ClickException(
            "No focus found. Run `paircode focus new <slug>` first."
        )
    click.echo(str(state.active_focus))


# ---------------------------------------------------------------------------
# Roster — print peer ids
# ---------------------------------------------------------------------------

@main.command()
@click.option("--alpha", "alpha_cli", default=None,
              help="CLI acting as alpha (excluded from peers unless last resort).")
@click.option("--peer", "peer_filter", default=None,
              help="Narrow to a single peer id. Silently falls back if missing.")
@click.option("--peers", "peers_filter", default=None,
              help="Comma-separated peer ids. Silently falls back if none match.")
def roster(alpha_cli: str | None, peer_filter: str | None, peers_filter: str | None) -> None:
    """Print peer ids, one per line — best-effort, never errors.

    Resolution order:
      1. Apply --peer/--peers filter to the peers.yaml roster.
      2. If --alpha is given, drop peers whose cli matches (except as last resort).
      3. If the result is empty, fall back to "all peers except alpha".
      4. If still empty, re-run handshake detection in case new CLIs landed.
      5. If still empty and an alpha-cli peer exists, emit that as last resort.
      6. If still empty, emit nothing — team lead must handle.
    """
    state = find_paircode()
    if state is None:
        return

    all_peers = [p for p in read_peers(state) if p.get("id")]

    # Step 1 — apply filter
    if peers_filter:
        wanted = [s.strip() for s in peers_filter.split(",") if s.strip()]
        filtered = [p for p in all_peers if p.get("id") in wanted]
    elif peer_filter:
        filtered = [p for p in all_peers if p.get("id") == peer_filter]
    else:
        filtered = list(all_peers)

    # Step 2 — alpha exclusion
    def _exclude_alpha(peers: list[dict]) -> list[dict]:
        if not alpha_cli:
            return peers
        return [p for p in peers if p.get("cli") != alpha_cli]

    result = _exclude_alpha(filtered)

    # Step 3 — fallback to "all peers except alpha" if filter missed
    if not result and (peer_filter or peers_filter):
        result = _exclude_alpha(all_peers)

    # Step 4 — refresh detection (maybe user installed something since last handshake)
    if not result:
        proposed = propose_roster()
        if proposed:
            fresh_dicts = proposed_as_yaml_dicts(proposed)
            known_ids = {p.get("id") for p in all_peers}
            added = [p for p in fresh_dicts if p.get("id") not in known_ids]
            if added:
                write_peers(state, all_peers + added)
                ensure_peer_dirs(state, proposed)
                all_peers = all_peers + added
                result = _exclude_alpha(all_peers)

    # Step 5 — last resort: include alpha-cli peer if that's all we have
    if not result:
        result = list(all_peers)

    for p in result:
        pid = p.get("id")
        if pid:
            click.echo(pid)


# ---------------------------------------------------------------------------
# Invoke — fire one peer
# ---------------------------------------------------------------------------

@main.command()
@click.argument("stage")
def converge(stage: str) -> None:
    """Converge a stage — copy each participant's latest `vN.md` to `{id}-FINAL.md`.

    Runs on the active focus. Mechanical file-copy only; the slash command
    writes `consensus.md` afterward from the FINAL files.
    """
    from paircode.converge import seal_stage

    state = find_paircode()
    if state is None or state.active_focus is None:
        raise click.ClickException(
            "No active focus. Run `paircode focus new <slug>` first."
        )
    stage_dir = state.active_focus / stage
    if not stage_dir.exists():
        raise click.ClickException(f"Stage dir not found: {stage_dir}")
    sealed = seal_stage(stage_dir)
    if not sealed:
        raise click.ClickException(
            f"No versioned files found in {stage_dir} — nothing to converge."
        )
    for s in sealed:
        click.echo(f"{s.peer_id} → {s.final.name}")


@main.command()
@click.argument("peer_id")
@click.argument("prompt")
@click.option("--out", "out_path", required=True, type=click.Path(),
              help="Where to write the peer's file-trace markdown")
@click.option("--timeout", default=600, show_default=True,
              help="Per-peer timeout in seconds")
@click.option("--fast/--no-fast", default=False,
              help="Apply cliworker speed flags (faster, fewer tools)")
def invoke(peer_id: str, prompt: str, out_path: str, timeout: int, fast: bool) -> None:
    """Run one peer LLM against PROMPT; write file-trace markdown to --out.

    PEER_ID must match an `id` in .paircode/peers.yaml.
    Exits 0 on peer success, non-zero on failure. Always writes a file-trace
    (even on failure) so every invocation leaves evidence on disk.
    """
    state = find_paircode()
    if state is None:
        raise click.ClickException(
            "No .paircode/ found. Run `paircode ensure-scaffold` first."
        )
    peers = read_peers(state)
    peer = next((p for p in peers if p.get("id") == peer_id), None)
    if peer is None:
        known = [p.get("id") for p in peers]
        raise click.ClickException(
            f"Unknown peer id: {peer_id!r}. Known: {known}"
        )

    result = run_peer(
        peer_id=peer_id,
        cli=str(peer.get("cli")),
        prompt=prompt,
        output_path=Path(out_path),
        model=peer.get("model"),
        timeout_s=timeout,
        fast=fast,
    )
    status = "ok" if result.ok else "FAIL"
    click.echo(f"{peer_id} {status} {result.duration_s:.1f}s", err=True)
    if not result.ok:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# peerlab — per-peer independent parallel labs with their own .git
# ---------------------------------------------------------------------------

@main.group()
def peerlab() -> None:
    """Per-peer parallel labs under .peerlab/<peer-id>/ with own .git each."""


@peerlab.command("ensure")
def peerlab_ensure() -> None:
    """Scaffold .peerlab/<peer-id>/ per peer; seed from project root on first
    creation; git init per lab; add .peerlab/ to outer .gitignore. Idempotent."""
    from paircode.peerlab import ensure_peer_labs

    state = find_paircode()
    if state is None:
        state = init_paircode()
    results = ensure_peer_labs(state)
    for r in results:
        if r.status == "created":
            click.echo(f"created {r.lab_path}")
        elif r.status == "missing-id":
            click.echo(f"skipped peer with no id", err=True)
        # "already-exists" → silent, per auto-install ethos


@peerlab.command("invoke")
@click.argument("peer_id")
@click.argument("prompt")
@click.option("--out", "out_path", default=None, type=click.Path(),
              help="Optional file-trace output (markdown). If omitted, peer stdout goes to stdout.")
@click.option("--timeout", default=600, show_default=True,
              help="Per-peer timeout in seconds")
@click.option("--fast/--no-fast", default=False,
              help="Apply cliworker speed flags")
def peerlab_invoke(peer_id: str, prompt: str, out_path: str | None, timeout: int, fast: bool) -> None:
    """Fire a peer CLI with cwd set to its lab. Peer works in-place."""
    from paircode.peerlab import peer_lab_path

    state = find_paircode()
    if state is None:
        raise click.ClickException(
            "No .paircode/ found. Run `paircode ensure-scaffold` + `paircode peerlab ensure` first."
        )
    peers = read_peers(state)
    peer = next((p for p in peers if p.get("id") == peer_id), None)
    if peer is None:
        known = [p.get("id") for p in peers]
        raise click.ClickException(f"Unknown peer id: {peer_id!r}. Known: {known}")
    lab = peer_lab_path(state, peer_id)
    if not lab.exists():
        raise click.ClickException(
            f"Lab dir missing: {lab}. Run `paircode peerlab ensure` first."
        )

    # Preamble so the peer knows it's in a lab with its own git
    framed_prompt = (
        f"You are the {peer_id} peer working in your own lab at {lab}.\n"
        f"Your cwd is already this lab. You have your own `.git/` here — commit\n"
        f"your work (stage + commit) before finishing so the team lead can read\n"
        f"the diff. Don't worry about alpha's repo; your lab is fully independent.\n"
        f"\n"
        f"Work:\n"
        f"{prompt}"
    )

    from cliworker import get_spec, run as cliworker_run

    spec = get_spec(str(peer.get("cli")), model=peer.get("model")) if peer.get("model") else get_spec(str(peer.get("cli")))
    results = cliworker_run(
        framed_prompt, spec,
        fast=True if fast else None,
        timeout_s=timeout,
        cwd=str(lab),
    )
    cli_result = results[-1] if results else None
    if cli_result is None:
        raise click.ClickException(f"no result from cliworker for {peer.get('cli')}")

    status = "ok" if cli_result.ok else "FAIL"
    click.echo(f"{peer_id} {status} {cli_result.duration_s:.1f}s", err=True)

    body = cli_result.stdout if cli_result.ok else (
        f"# Peer run FAILED\n\n```\n{cli_result.stderr}\n```\n\n{cli_result.stdout}"
    )

    if out_path:
        header = (
            f"<!-- peer_id: {peer_id} -->\n"
            f"<!-- cli: {peer.get('cli')} -->\n"
            f"<!-- lab: {lab} -->\n"
            f"<!-- duration_s: {cli_result.duration_s:.1f} -->\n"
            f"<!-- ok: {cli_result.ok} -->\n"
        )
        timeout_kind = getattr(cli_result, "timeout_kind", None)
        if timeout_kind:
            header += f"<!-- timeout_kind: {timeout_kind} -->\n"
        header += "\n"
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(header + body, encoding="utf-8")
    else:
        click.echo(body)

    if not cli_result.ok:
        raise SystemExit(1)


@peerlab.command("list")
def peerlab_list() -> None:
    """Show peer labs with creation status + HEAD commit (if any)."""
    from paircode.peerlab import peer_lab_path

    state = find_paircode()
    if state is None:
        click.echo("No .paircode/ found. Nothing to list.")
        return
    peers = read_peers(state)
    if not peers:
        click.echo("No peers in roster.")
        return
    ptable = Table(show_header=True, header_style="bold")
    ptable.add_column("peer")
    ptable.add_column("lab path")
    ptable.add_column("git HEAD")
    import subprocess as _sub
    for p in peers:
        pid = p.get("id")
        if not pid:
            continue
        lab = peer_lab_path(state, pid)
        if not lab.exists():
            ptable.add_row(pid, str(lab), "[dim](not created)[/dim]")
            continue
        if not (lab / ".git").exists():
            ptable.add_row(pid, str(lab), "[yellow](no git)[/yellow]")
            continue
        r = _sub.run(
            ["git", "-C", str(lab), "log", "-1", "--oneline"],
            capture_output=True, text=True, check=False,
        )
        head = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "[dim](no commits)[/dim]"
        ptable.add_row(pid, str(lab), head)
    console.print(ptable)


# ---------------------------------------------------------------------------
# Bare paircode — show state
# ---------------------------------------------------------------------------

def _show_state() -> None:
    """Bare `paircode` prints current .paircode/ state. Former `status` output."""
    state = find_paircode()
    console.print(f"[bold]paircode[/bold] v{__version__}")
    if state is None:
        console.print(
            "\n[yellow]No .paircode/ found in cwd or any parent.[/yellow]\n"
            "Run [cyan]paircode install[/cyan] to register /paircode in your LLM CLIs,\n"
            "then run [cyan]/paircode \"your prompt\"[/cyan] inside Claude / Codex / Gemini\n"
            "to kick off a peer-review cycle."
        )
        return
    console.print(f"\n[bold].paircode/[/bold] at [cyan]{state.root}[/cyan]")
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
        ptable.add_column("priority")
        for p in peers:
            ptable.add_row(
                str(p.get("id", "?")),
                str(p.get("cli", "?")),
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


if __name__ == "__main__":
    main()

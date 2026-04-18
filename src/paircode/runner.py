"""Invoke peer LLM CLIs via cliworker, capture output to .md files.

Thin wrapper over `cliworker.run()`. Gives paircode:
  * CLAUDE_FAST flags when fast=True (claude -p goes from 18s → 4s)
  * Gemini MCP strip-and-restore during calls
  * Skip-cache for broken engines (1h TTL)
  * Subscription-mode-first by default (no API credits unless paid_ok=True)
  * One place to fix CLI quirks instead of re-implementing them here

Adds one paircode-specific thing cliworker doesn't: writing each peer's
response to a .md file with a file-trace header (peer_id / cli / model /
duration / ok). That's the orchestration log paircode needs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cliworker import CLIResult, get_spec, run


DEFAULT_TIMEOUT_SECONDS = 600  # 10 min per peer call — generous for cold research


@dataclass(frozen=True)
class PeerRunResult:
    """paircode's peer-run result — wraps cliworker's CLIResult with a peer_id."""
    peer_id: str
    cli: str
    ok: bool
    stdout: str
    stderr: str
    duration_s: float
    command: list[str]

    @classmethod
    def from_cli_result(cls, peer_id: str, r: CLIResult) -> "PeerRunResult":
        return cls(
            peer_id=peer_id,
            cli=r.spec.cli,
            ok=r.ok,
            stdout=r.stdout,
            stderr=r.stderr,
            duration_s=r.duration_s,
            command=list(r.argv),
        )


def run_peer(
    peer_id: str,
    cli: str,
    prompt: str,
    output_path: Path,
    model: Optional[str] = None,
    timeout_s: int = DEFAULT_TIMEOUT_SECONDS,
    fast: bool = False,
    paid_ok: bool | list[str] | None = None,
) -> PeerRunResult:
    """Run one peer LLM against `prompt`, write its stdout to `output_path`.

    Delegates to `cliworker.run()` for the actual subprocess call. Adds the
    paircode-specific file-trace header. Output file is written regardless
    of success — every invocation leaves a trace on disk.

    Args:
        peer_id: paircode-level identifier (e.g. "peer-a-codex"). Not known to cliworker.
        cli: one of "claude", "codex", "gemini", "ollama".
        prompt: the instruction to send.
        output_path: where to write the file-trace .md.
        model: optional model override (e.g. "sonnet", "gemma3:4b").
        timeout_s: per-call timeout.
        fast: True = apply cliworker's speed flags (CLAUDE_FAST, gemini MCP strip).
              False (default) = full mode — all MCPs/tools loaded, matches how
              the user's normal `claude -p` session behaves.
        paid_ok: None (default) = free/subscription only, never burn API credits.
                 True = allow paid API fallback for this CLI.
                 list[str] = allow paid only for those CLI names (typically just `cli`).
    """
    # Build spec with optional model override
    spec = get_spec(cli, model=model) if model else get_spec(cli)

    # cliworker's run() needs None (not False) to "respect spec default" for fast.
    results = run(
        prompt, spec,
        fast=True if fast else None,
        paid_ok=paid_ok,
        timeout_s=timeout_s,
    )

    # cliworker.run() returns empty list only if no CLIs passed AND no default chain.
    # We passed an explicit spec, so this should always have at least one result.
    if results:
        cli_result = results[-1]
    else:
        # Defensive fallback — construct a failure result
        cli_result = CLIResult(
            spec=spec, ok=False, stdout="",
            stderr=f"no result from cliworker for {cli}",
            duration_s=0.0, returncode=None, argv=[], skipped_reason=None,
        )

    # Write the paircode file-trace
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- peer_id: {peer_id} -->\n"
        f"<!-- cli: {cli} -->\n"
        f"<!-- model: {model or '(default)'} -->\n"
        f"<!-- duration_s: {cli_result.duration_s:.1f} -->\n"
        f"<!-- ok: {cli_result.ok} -->\n\n"
    )
    if cli_result.ok:
        body = cli_result.stdout
    else:
        body = (
            f"# Peer run FAILED\n\n"
            f"```\n{cli_result.stderr}\n```\n\n"
            f"{cli_result.stdout}"
        )
    output_path.write_text(header + body, encoding="utf-8")

    return PeerRunResult.from_cli_result(peer_id, cli_result)

"""Invoke peer LLM CLIs as subprocesses, capture output to .md files.

This is the "spawn an LLM, write its answer to disk" primitive. Each CLI
has different flags for non-interactive / prompt-mode; we normalize them
here so upstream code just says "ask <peer> this prompt, save to <path>".
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_TIMEOUT_SECONDS = 600  # 10 min per peer call — generous for cold research


@dataclass(frozen=True)
class PeerRunResult:
    peer_id: str
    cli: str
    ok: bool
    stdout: str
    stderr: str
    duration_s: float
    command: list[str]


def _cli_command(cli: str, prompt: str, model: Optional[str]) -> list[str]:
    """Return the subprocess argv to invoke `cli` non-interactively with `prompt`."""
    if cli == "claude":
        # Claude Code: -p is non-interactive (print) mode
        cmd = ["claude", "-p", prompt]
        if model:
            cmd.extend(["--model", model])
        return cmd
    if cli == "codex":
        # Codex CLI: `codex exec` is non-interactive; --dangerously-bypass needed to
        # write files / skip approvals when running headless.
        cmd = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", prompt]
        if model:
            cmd.extend(["--model", model])
        return cmd
    if cli == "gemini":
        cmd = ["gemini", "-p", prompt]
        if model:
            cmd.extend(["--model", model])
        return cmd
    if cli == "ollama":
        # Ollama needs a model name
        return ["ollama", "run", model or "llama3.1", prompt]
    # Unknown CLI — best-effort: pass prompt as last arg
    return [cli, prompt]


def run_peer(
    peer_id: str,
    cli: str,
    prompt: str,
    output_path: Path,
    model: Optional[str] = None,
    timeout_s: int = DEFAULT_TIMEOUT_SECONDS,
) -> PeerRunResult:
    """Run one peer LLM against `prompt`, write its stdout to `output_path`.

    Returns a PeerRunResult capturing success/failure + full stdout + stderr.
    The output file is written regardless of success (empty or error-captured
    text) so that every invocation leaves a file-trace on disk.
    """
    import time

    cmd = _cli_command(cli, prompt, model)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        duration = time.monotonic() - start
        ok = proc.returncode == 0
        stdout, stderr = proc.stdout, proc.stderr
    except FileNotFoundError:
        duration = time.monotonic() - start
        ok = False
        stdout = ""
        stderr = f"{cli} binary not found on PATH"
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        ok = False
        stdout = ""
        stderr = f"{cli} timed out after {timeout_s}s"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- peer_id: {peer_id} -->\n"
        f"<!-- cli: {cli} -->\n"
        f"<!-- model: {model or '(default)'} -->\n"
        f"<!-- duration_s: {duration:.1f} -->\n"
        f"<!-- ok: {ok} -->\n\n"
    )
    body = stdout if ok else f"# Peer run FAILED\n\n```\n{stderr}\n```\n\n{stdout}"
    output_path.write_text(header + body, encoding="utf-8")
    return PeerRunResult(
        peer_id=peer_id,
        cli=cli,
        ok=ok,
        stdout=stdout,
        stderr=stderr,
        duration_s=duration,
        command=cmd,
    )

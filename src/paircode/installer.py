"""Install paircode's slash command into detected LLM CLIs.

Strategy per CLI:
  - Claude Code: writes ~/.claude/commands/paircode.md as a real slash command.
    When the user types `/paircode` in any Claude Code session, this file
    tells Claude to invoke the paircode CLI via bash.
  - Codex: no file written. Codex doesn't have a user-facing slash-command
    system. Users invoke `paircode` from their shell or `codex exec paircode ...`.
    Previous versions wrote `~/.codex/rules/paircode.rules` — that file is
    Starlark-formatted and our markdown content broke codex's rule loader.
    `uninstall` still cleans up that legacy path.
  - Gemini: no file written. Same reasoning — gemini's custom-command story
    is `gemini skills install` with a git-repo source, not a markdown drop.
    That's a v0.9+ stretch goal. For now, gemini users invoke paircode from
    the shell.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from paircode.detect import detect_all, CliInfo


@dataclass(frozen=True)
class InstallResult:
    cli_name: str
    action: str  # "installed", "skipped", "failed", "noop"
    path: Path | None
    message: str


def _read_template(name: str) -> str:
    return resources.files("paircode.templates").joinpath(name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-CLI installers
# ---------------------------------------------------------------------------

def install_claude(info: CliInfo) -> InstallResult:
    """Write ~/.claude/commands/paircode.md — a real Claude Code slash command."""
    if not info.installed:
        return InstallResult(
            cli_name="claude",
            action="skipped",
            path=None,
            message=f"claude CLI not on PATH. {info.install_hint}",
        )
    commands_dir = info.config_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    target = commands_dir / "paircode.md"
    template = _read_template("claude_slash_command.md")
    target.write_text(template, encoding="utf-8")
    return InstallResult(
        cli_name="claude",
        action="installed",
        path=target,
        message=f"Wrote /paircode slash command to {target}. Use it from any Claude Code session.",
    )


def install_codex(info: CliInfo) -> InstallResult:
    """Codex has no user-facing slash-command system. No-op, print guidance."""
    if not info.installed:
        return InstallResult(
            cli_name="codex",
            action="skipped",
            path=None,
            message=f"codex CLI not on PATH. {info.install_hint}",
        )
    return InstallResult(
        cli_name="codex",
        action="noop",
        path=None,
        message=(
            "codex has no slash-command system — nothing to install. "
            "Invoke paircode from your shell (`paircode status`) or via "
            "`codex exec 'paircode status'` from inside a codex session."
        ),
    )


def install_gemini(info: CliInfo) -> InstallResult:
    """Gemini's custom-command story uses `gemini skills install` with a git
    repo. That's not an easy installer drop — deferred to v0.9+. No-op."""
    if not info.installed:
        return InstallResult(
            cli_name="gemini",
            action="skipped",
            path=None,
            message=f"gemini CLI not on PATH. {info.install_hint}",
        )
    return InstallResult(
        cli_name="gemini",
        action="noop",
        path=None,
        message=(
            "gemini uses `gemini skills install` for custom commands — "
            "proper skill-registration lands in v0.9+. For now, invoke "
            "paircode from your shell or via `gemini -p 'run paircode status'`."
        ),
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def install_all() -> list[InstallResult]:
    """Run every CLI's installer. Also cleans up legacy broken files first."""
    _clean_legacy_broken_files()
    detected = detect_all()
    installers = {
        "claude": install_claude,
        "codex": install_codex,
        "gemini": install_gemini,
    }
    results: list[InstallResult] = []
    for name, info in detected.items():
        installer = installers.get(name)
        if not installer:
            continue
        try:
            results.append(installer(info))
        except Exception as exc:  # pragma: no cover — defensive
            results.append(
                InstallResult(
                    cli_name=name, action="failed", path=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def _clean_legacy_broken_files() -> None:
    """Remove files that previous versions of paircode installed and which we
    now know to be broken or misplaced. Silent; best-effort."""
    for legacy_path in (
        # v0.1–v0.7 wrote markdown to codex's Starlark rules dir, which broke
        # codex's rule loader. Always clean this up on any install.
        Path.home() / ".codex" / "rules" / "paircode.rules",
        # v0.1–v0.7 also dropped a reference file at ~/.gemini/paircode.md.
        # Harmless but no longer created; remove to keep the dir clean.
        Path.home() / ".gemini" / "paircode.md",
    ):
        try:
            if legacy_path.exists():
                legacy_path.unlink()
        except OSError:
            pass


def uninstall_all() -> list[InstallResult]:
    """Remove paircode entries from every CLI config dir (idempotent).
    Also cleans up legacy broken paths from prior paircode versions."""
    results: list[InstallResult] = []
    paths: list[tuple[Path, str]] = [
        (Path.home() / ".claude" / "commands" / "paircode.md", "claude"),
        # Legacy paths — older paircode put these here, we still clean them up
        (Path.home() / ".codex" / "rules" / "paircode.rules", "codex"),
        (Path.home() / ".gemini" / "paircode.md", "gemini"),
    ]
    for path, cli_name in paths:
        if path.exists():
            try:
                path.unlink()
                results.append(InstallResult(
                    cli_name=cli_name, action="installed",  # "removed"
                    path=path, message=f"Removed {path}",
                ))
            except OSError as exc:
                results.append(InstallResult(
                    cli_name=cli_name, action="failed",
                    path=path, message=f"Failed to remove {path}: {exc}",
                ))
        else:
            results.append(InstallResult(
                cli_name=cli_name, action="skipped",
                path=path, message=f"Nothing to remove at {path}",
            ))
    return results

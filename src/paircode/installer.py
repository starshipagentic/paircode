"""Install paircode's slash command into detected LLM CLIs.

Strategy per CLI (all file-drop; see v1.0 roadmap for native register migration):
  - Claude Code: ~/.claude/commands/paircode.md (Markdown + YAML frontmatter).
                 First-class documented path.
  - Codex CLI:   ~/.codex/prompts/paircode.md (Markdown + YAML frontmatter).
                 Path marked "deprecated" by OpenAI (they're steering toward
                 marketplaces), but still loads and remains the only file-drop
                 path for user-typed slash commands in codex.
  - Gemini CLI:  ~/.gemini/commands/paircode.toml (TOML with description + prompt).
                 First-class, first-party format. Not Markdown.

Also cleans up legacy broken files from paircode 0.1–0.7 which wrote
~/.codex/rules/paircode.rules (that file is Starlark-parsed and our markdown
broke codex's rule loader).
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
            cli_name="claude", action="skipped", path=None,
            message=f"claude CLI not on PATH. {info.install_hint}",
        )
    commands_dir = info.config_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    target = commands_dir / "paircode.md"
    target.write_text(_read_template("claude_slash_command.md"), encoding="utf-8")
    return InstallResult(
        cli_name="claude", action="installed", path=target,
        message=f"Wrote /paircode slash command to {target}.",
    )


def install_codex(info: CliInfo) -> InstallResult:
    """Write ~/.codex/prompts/paircode.md — codex's custom-prompt slash command path.

    Codex flags this path as "deprecated" in favor of marketplace plugins, but
    it's still the only file-drop path for user-typed slash commands. When
    codex removes this (they haven't yet), paircode will migrate to
    `codex marketplace add` with a satellite repo.
    """
    if not info.installed:
        return InstallResult(
            cli_name="codex", action="skipped", path=None,
            message=f"codex CLI not on PATH. {info.install_hint}",
        )
    prompts_dir = info.config_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    target = prompts_dir / "paircode.md"
    target.write_text(_read_template("codex_slash_command.md"), encoding="utf-8")
    return InstallResult(
        cli_name="codex", action="installed", path=target,
        message=f"Wrote /paircode slash command to {target}. Inside codex interactive, /paircode will appear.",
    )


def install_gemini(info: CliInfo) -> InstallResult:
    """Write ~/.gemini/commands/paircode.toml — gemini's first-class custom command path.

    Gemini uses TOML (not Markdown) with `description` and `prompt` fields.
    After install, run `/commands reload` inside gemini or restart the session.
    """
    if not info.installed:
        return InstallResult(
            cli_name="gemini", action="skipped", path=None,
            message=f"gemini CLI not on PATH. {info.install_hint}",
        )
    commands_dir = info.config_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    target = commands_dir / "paircode.toml"
    target.write_text(_read_template("gemini_slash_command.toml"), encoding="utf-8")
    return InstallResult(
        cli_name="gemini", action="installed", path=target,
        message=(
            f"Wrote /paircode slash command to {target}. "
            "Run `/commands reload` inside gemini (or restart) to pick it up."
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
            results.append(InstallResult(
                cli_name=name, action="failed", path=None,
                message=f"{type(exc).__name__}: {exc}",
            ))
    return results


def _clean_legacy_broken_files() -> None:
    """Remove files prior paircode versions installed and which we now know
    to be broken or misplaced. Silent best-effort."""
    # v0.1–v0.7 wrote markdown to codex's Starlark rules dir, which broke
    # codex's rule loader on every session startup.
    legacy = Path.home() / ".codex" / "rules" / "paircode.rules"
    try:
        if legacy.exists():
            legacy.unlink()
    except OSError:
        pass

    # v0.1–v0.7 also dropped a reference file at ~/.gemini/paircode.md.
    # v0.9+ writes the real slash command at ~/.gemini/commands/paircode.toml
    # instead; clean up the old reference.
    legacy_gemini = Path.home() / ".gemini" / "paircode.md"
    try:
        if legacy_gemini.exists():
            legacy_gemini.unlink()
    except OSError:
        pass


def uninstall_all() -> list[InstallResult]:
    """Remove paircode entries from every CLI config dir (idempotent).
    Also cleans up legacy broken paths from prior paircode versions."""
    results: list[InstallResult] = []
    paths: list[tuple[Path, str]] = [
        # Current v0.9+ paths
        (Path.home() / ".claude" / "commands" / "paircode.md", "claude"),
        (Path.home() / ".codex" / "prompts" / "paircode.md", "codex"),
        (Path.home() / ".gemini" / "commands" / "paircode.toml", "gemini"),
        # Legacy paths from older paircode versions
        (Path.home() / ".codex" / "rules" / "paircode.rules", "codex-legacy"),
        (Path.home() / ".gemini" / "paircode.md", "gemini-legacy"),
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

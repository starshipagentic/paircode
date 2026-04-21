"""Install paircode's slash command into detected LLM CLIs.

Strategy per CLI:
  - Claude Code: file-drop ~/.claude/commands/paircode.md
                 Claude's native plugin-install requires publishing a marketplace;
                 overkill for one command. File-drop is first-class + documented.
  - Codex CLI:   native register via `codex marketplace add starshipagentic/paircode-codex`
                 (git-clones the satellite repo into ~/.codex/.tmp/marketplaces/).
                 Satellite contains .agents/plugins/marketplace.json + plugin manifest +
                 commands/paircode.md. Replaces the v0.9 file-drop at ~/.codex/prompts/.
  - Gemini CLI:  native register via `gemini extensions install https://github.com/starshipagentic/paircode-gemini --consent`
                 Git-clones the satellite repo into ~/.gemini/extensions/paircode/.
                 Satellite contains gemini-extension.json + commands/paircode.toml.
                 Replaces the v0.9 file-drop at ~/.gemini/commands/.

Native-register subprocess calls go through `cliworker.invoke()` — no LLM semantics,
stdin=DEVNULL for fail-fast on unexpected prompts, capture stderr for fallback
messaging.

Also cleans up legacy files from pre-v0.10 paircode versions on every install.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from cliworker import invoke

from paircode.detect import detect_all, CliInfo


# Satellite repo coordinates — update here when repos move.
CODEX_MARKETPLACE = "starshipagentic/paircode-codex"
GEMINI_EXTENSION_URL = "https://github.com/starshipagentic/paircode-gemini"

# Per-CLI timeouts for the native install commands (git clones + setup).
NATIVE_INSTALL_TIMEOUT_S = 90


@dataclass(frozen=True)
class InstallResult:
    cli_name: str
    action: str  # "installed", "skipped", "failed", "noop", "already"
    path: Path | None
    message: str


def _read_template(relative_path: str) -> str:
    """Read a file under `paircode/templates/` by relative path.

    Host templates live at `<host>/commands/...`, host-agnostic scaffold
    templates at the root (`FOCUS.md`, `JOURNEY.md`, `peers.yaml`).
    """
    return resources.files("paircode.templates").joinpath(relative_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-CLI installers
# ---------------------------------------------------------------------------

def install_claude(info: CliInfo) -> InstallResult:
    """Write ~/.claude/commands/paircode.md — file-drop (native for Claude Code).

    The template uses Claude's stock Agent tool (subagent_type=general-purpose,
    run_in_background=true) to fan out peer reviewers — no custom sub-agent
    definition file required.
    """
    if not info.installed:
        return InstallResult(
            cli_name="claude", action="skipped", path=None,
            message=f"claude CLI not on PATH. {info.install_hint}",
        )
    commands_dir = info.config_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    target = commands_dir / "paircode.md"
    target.write_text(
        _read_template("claude/commands/paircode.md"),
        encoding="utf-8",
    )
    return InstallResult(
        cli_name="claude", action="installed", path=target,
        message=f"Wrote /paircode slash command to {target}.",
    )


def _codex_already_installed() -> bool:
    """Idempotency check: is the paircode marketplace already registered?"""
    config = Path.home() / ".codex" / "config.toml"
    if not config.exists():
        return False
    try:
        text = config.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "[marketplaces.paircode]" in text or "paircode-codex" in text


def install_codex(info: CliInfo) -> InstallResult:
    """Native register via `codex marketplace add starshipagentic/paircode-codex`."""
    if not info.installed:
        return InstallResult(
            cli_name="codex", action="skipped", path=None,
            message=f"codex CLI not on PATH. {info.install_hint}",
        )

    if _codex_already_installed():
        return InstallResult(
            cli_name="codex", action="already", path=None,
            message="paircode already registered with codex. Skip.",
        )

    result = invoke(
        "codex", "marketplace", "add", CODEX_MARKETPLACE,
        timeout_s=NATIVE_INSTALL_TIMEOUT_S,
    )
    if result.ok:
        return InstallResult(
            cli_name="codex", action="installed", path=None,
            message=f"Ran: codex marketplace add {CODEX_MARKETPLACE}",
        )
    return InstallResult(
        cli_name="codex", action="failed", path=None,
        message=(
            f"codex marketplace add failed. Run yourself:\n"
            f"  codex marketplace add {CODEX_MARKETPLACE}\n"
            f"stderr: {result.stderr.strip()[:200]}"
        ),
    )


def _gemini_already_installed() -> bool:
    """Idempotency check: is the paircode extension already installed?"""
    result = invoke("gemini", "extensions", "list", timeout_s=15)
    if not result.ok:
        return False
    return "paircode-gemini" in result.stdout or "paircode (" in result.stdout


def install_gemini(info: CliInfo) -> InstallResult:
    """Native register via `gemini extensions install <url> --consent`."""
    if not info.installed:
        return InstallResult(
            cli_name="gemini", action="skipped", path=None,
            message=f"gemini CLI not on PATH. {info.install_hint}",
        )

    if _gemini_already_installed():
        return InstallResult(
            cli_name="gemini", action="already", path=None,
            message="paircode already installed as gemini extension. Skip.",
        )

    result = invoke(
        "gemini", "extensions", "install", GEMINI_EXTENSION_URL, "--consent",
        timeout_s=NATIVE_INSTALL_TIMEOUT_S,
    )
    if result.ok:
        return InstallResult(
            cli_name="gemini", action="installed", path=None,
            message=(
                f"Ran: gemini extensions install {GEMINI_EXTENSION_URL} --consent. "
                "Inside gemini, run `/commands reload` (or restart) to pick up /paircode."
            ),
        )
    return InstallResult(
        cli_name="gemini", action="failed", path=None,
        message=(
            f"gemini extensions install failed. Run yourself:\n"
            f"  gemini extensions install {GEMINI_EXTENSION_URL} --consent\n"
            f"stderr: {result.stderr.strip()[:200]}"
        ),
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def install_all() -> list[InstallResult]:
    """Run every CLI's installer. Also cleans up legacy paths first."""
    _clean_legacy_paths()
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


def _clean_legacy_paths() -> None:
    """Remove files that prior paircode versions installed and which we now
    know to be broken, misplaced, or replaced by native-register flows."""
    legacy_files = (
        # v0.1–v0.7: wrote markdown to codex's Starlark rules dir → broke codex.
        Path.home() / ".codex" / "rules" / "paircode.rules",
        # v0.8: wrote a reference file at ~/.gemini/paircode.md (harmless but obsolete).
        Path.home() / ".gemini" / "paircode.md",
        # v0.9: wrote file-drop slash commands at these paths. v0.10+ uses native register.
        Path.home() / ".codex" / "prompts" / "paircode.md",
        Path.home() / ".gemini" / "commands" / "paircode.toml",
    )
    for path in legacy_files:
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass


def uninstall_all() -> list[InstallResult]:
    """Remove paircode from every CLI. Uses native uninstall where available,
    file-drop removal where not."""
    results: list[InstallResult] = []

    # Claude — file-drop. Remove slash command AND the paircode-peer sub-agent.
    claude_home = Path.home() / ".claude"
    claude_paths = [
        claude_home / "commands" / "paircode.md",
        claude_home / "agents" / "paircode-peer.md",
    ]
    removed = []
    failed = []
    for p in claude_paths:
        if not p.exists():
            continue
        try:
            p.unlink()
            removed.append(str(p))
        except OSError as exc:
            failed.append(f"{p}: {exc}")
    if failed:
        results.append(InstallResult(
            cli_name="claude", action="failed", path=None,
            message=f"Failed to remove: {'; '.join(failed)}",
        ))
    elif removed:
        results.append(InstallResult(
            cli_name="claude", action="installed", path=None,
            message=f"Removed: {', '.join(removed)}",
        ))
    else:
        results.append(InstallResult(
            cli_name="claude", action="skipped", path=None,
            message="Nothing to remove under ~/.claude/.",
        ))

    # Codex — no native remove command. Strip the marketplace stanza from config.toml
    # and rm -rf the cache dir. Fragile but the only option until codex adds a CLI.
    config = Path.home() / ".codex" / "config.toml"
    cache_dir = Path.home() / ".codex" / ".tmp" / "marketplaces" / "paircode"
    removed_codex = False
    if config.exists():
        try:
            text = config.read_text(encoding="utf-8")
            # Strip the [marketplaces.paircode] section and its key/value lines.
            new_text = _strip_toml_section(text, "marketplaces.paircode")
            new_text = _strip_toml_section(new_text, 'plugins."paircode@paircode"')
            if new_text != text:
                config.write_text(new_text, encoding="utf-8")
                removed_codex = True
        except OSError as exc:
            results.append(InstallResult(
                cli_name="codex", action="failed", path=config,
                message=f"Failed to edit {config}: {exc}",
            ))
    if cache_dir.exists():
        import shutil as _sh
        try:
            _sh.rmtree(cache_dir)
            removed_codex = True
        except OSError:
            pass
    if removed_codex:
        results.append(InstallResult(
            cli_name="codex", action="installed", path=None,
            message="Removed paircode marketplace from ~/.codex/config.toml + cache.",
        ))
    else:
        results.append(InstallResult(
            cli_name="codex", action="skipped", path=None,
            message="No paircode marketplace registered with codex.",
        ))

    # Gemini — native uninstall command exists.
    result = invoke("gemini", "extensions", "uninstall", "paircode", timeout_s=30)
    if result.ok:
        results.append(InstallResult(
            cli_name="gemini", action="installed", path=None,
            message="Ran: gemini extensions uninstall paircode",
        ))
    else:
        # May fail if not installed; treat as skipped when stderr mentions that
        if "not installed" in result.stderr.lower() or "no extension" in result.stderr.lower():
            results.append(InstallResult(
                cli_name="gemini", action="skipped", path=None,
                message="paircode gemini extension not installed; nothing to remove.",
            ))
        else:
            results.append(InstallResult(
                cli_name="gemini", action="failed", path=None,
                message=(
                    f"gemini extensions uninstall failed. Run yourself:\n"
                    f"  gemini extensions uninstall paircode\n"
                    f"stderr: {result.stderr.strip()[:200]}"
                ),
            ))

    # Legacy cleanup (same as install_all)
    _clean_legacy_paths()

    return results


def _strip_toml_section(text: str, section_name: str) -> str:
    """Remove `[section_name]` and its following key/value lines from a TOML string.

    Returns the modified text. A section ends at the next `[...]` header or EOF.
    No-op if the section isn't present.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skipping = False
    target = f"[{section_name}]"
    for line in lines:
        stripped = line.strip()
        if stripped == target:
            skipping = True
            continue
        if skipping and stripped.startswith("[") and stripped.endswith("]"):
            skipping = False  # new section started
        if not skipping:
            out.append(line)
    return "".join(out)

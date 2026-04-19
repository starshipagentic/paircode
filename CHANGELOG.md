# Changelog

## 0.10.0 — native-register slash commands via satellite repos + cliworker.invoke()

Migrated from file-drop (v0.9) to the industry-standard native-register flow
for Codex and Gemini. Claude Code stays file-drop (no plugin install needed
for a single command).

### Install flow

    pipx install paircode
    paircode install

Now runs:
    * claude  — file-drop ~/.claude/commands/paircode.md          (unchanged)
    * codex   — codex marketplace add starshipagentic/paircode-codex
    * gemini  — gemini extensions install https://github.com/starshipagentic/paircode-gemini --consent

Both subprocess calls go through `cliworker.invoke()` (the new v0.8 primitive).
stdin=DEVNULL so any unexpected prompt fails fast instead of hanging.

### Two satellite repos

New companion repositories at starshipagentic/:
    * paircode-codex    — single-plugin marketplace for Codex CLI
    * paircode-gemini   — extension manifest + TOML command for Gemini CLI

Both contain ONLY the slash-command manifest — no Python. They mirror
`src/paircode/templates/{codex,gemini}_slash_command.{md,toml}` and are
auto-synced by `scripts/release.py` on every paircode release.

### Release pipeline

New `scripts/release.py`:

    ./scripts/release.py 0.10.0      # or: patch / minor / major

Bumps paircode version, runs tests, commits + tags + beams paircode to PyPI
+ GitHub, then for each satellite: copies the latest template, bumps the
manifest version, commits + tags + beams, and `gh release create` (critical
for Gemini's release-lookup — without a GitHub release, Gemini's install
command falls back to an interactive "install via git clone?" prompt).

One command keeps pypi, the main repo, and both satellites version-locked.

### Idempotency

`paircode install` is now idempotent:
    * codex  — greps ~/.codex/config.toml for `[marketplaces.paircode]`; skip if present
    * gemini — `gemini extensions list` grep for `paircode`; skip if present
    * claude — file-drop always overwrites (harmless idempotency)

### Fallback on failure

If either native-register call fails, `paircode install` prints the exact
command for the user to run manually (with the captured stderr) and sets
action="failed" — never silently succeeds with a non-working state.

### Legacy cleanup still runs

Every `paircode install` removes paths that older versions left:
    ~/.codex/rules/paircode.rules       (v0.1–0.7 — broke codex's rule loader)
    ~/.gemini/paircode.md               (v0.8 — obsolete reference file)
    ~/.codex/prompts/paircode.md        (v0.9 — replaced by marketplace)
    ~/.gemini/commands/paircode.toml    (v0.9 — replaced by extension)

Users upgrading from ANY prior version get silent heal.

### New dep

    cliworker>=0.8.1   (for the `invoke()` primitive)

### Tests

52 green. 4 new in test_cli_smoke.py + 1 updated in test_smoke.py:
    * test_installer_codex_calls_marketplace_add_via_invoke
    * test_installer_gemini_calls_extensions_install_via_invoke
    * test_installer_codex_idempotent_when_already_registered
    * test_installer_fails_gracefully_with_actionable_message
    * test_install_writes_claude_and_invokes_native_register (rewrite)

Also verified end-to-end on a live machine: both real `codex marketplace add`
and real `gemini extensions install` calls succeeded against the freshly-
published satellite repos. `/paircode` appears in each tool's slash menu.

## 0.9.0 — real `/paircode` slash command in Codex and Gemini (file-drop)

Research in April 2026 showed both Codex CLI (0.121.0+) and Gemini CLI
(0.35.3+) now support user-level slash commands via file-drop. paircode
v0.8.0 missed this and left codex/gemini as no-ops. v0.9.0 fixes that.

### What `paircode install` writes now

| CLI | Path | Format |
|---|---|---|
| Claude Code | `~/.claude/commands/paircode.md` | Markdown + YAML frontmatter (unchanged) |
| Codex CLI | `~/.codex/prompts/paircode.md` | Markdown + YAML frontmatter (new) |
| Gemini CLI | `~/.gemini/commands/paircode.toml` | **TOML** with `description` + `prompt` (new) |

All three return `action="installed"` in `paircode install` output. All three
show `/paircode` in the user's slash-command menu when they open the tool.

### New templates

- `src/paircode/templates/codex_slash_command.md` — codex-flavored frontmatter
  with `argument-hint` field.
- `src/paircode/templates/gemini_slash_command.toml` — TOML with `{{args}}`
  placeholder substitution (Gemini's native syntax).

### One caveat

Codex flags `~/.codex/prompts/` as "deprecated" (they're steering toward
marketplace plugins). Still the only file-drop path for user-typed slash
commands today, and OpenAI hasn't removed it. If that changes, paircode
migrates to `codex marketplace add` with a satellite `starshipagentic/paircode-codex`
repo — flagged for v1.0.

### Tests

50 green. Key new coverage:
- `test_install_writes_to_tmp_claude` updated: asserts all three CLIs write
  correct files at correct paths.
- `test_installer_writes_codex_prompt_never_broken_rules_file` — regression
  against the v0.7 codex bug AND asserts the new correct prompts path.
- `test_installer_writes_gemini_toml_command` — asserts TOML format, not
  markdown, with `description` + `prompt` + triple-quoted blocks.

### Legacy cleanup still runs

`install_all()` continues to silently remove `~/.codex/rules/paircode.rules`
(left by 0.1–0.7) and `~/.gemini/paircode.md` (left by 0.8). Users upgrading
from any prior version get silent heal.

## 0.8.0 — delegate CLI invocation to cliworker, fix codex installer

Major refactor: `paircode.runner` now delegates subprocess invocation to
[`cliworker`](https://pypi.org/project/cliworker/). One place to own the
CLI-calling quirks, for paircode + navcom + anything else.

### What paircode inherits for free

- **CLAUDE_FAST flags** when `run_peer(..., fast=True)` — 18s cold start → ~4s
- **Gemini MCP strip-and-restore** automatic during gemini invocations
- **Subscription-first** by default (API keys stripped unless `paid_ok=True`)
- **Skip-cache** for broken engines (1h TTL, same for all orchestrators)
- **Friendly ollama error** when the model isn't pulled (points at the exact
  `ollama pull gemma3:4b` command)

### Breaking fix — codex installer

Previous versions wrote `~/.codex/rules/paircode.rules` as markdown. Codex
parses `rules/*.rules` files as Starlark and our markdown broke its rule
loader. From v0.8.0:

- `paircode install` no longer writes to `~/.codex/rules/`.
- `install_codex` is a no-op — codex has no slash-command system, and users
  invoke `paircode` from their shell directly.
- `install_all()` also *cleans up* any legacy broken `~/.codex/rules/paircode.rules`
  file left over from older versions. Affected users get silent cleanup on
  next install.
- Gemini installer also became a no-op (skill registration deferred to v0.9+).
- Only `claude` gets a real file written: `~/.claude/commands/paircode.md`.

### New dependency

- `cliworker>=0.7.1` in `pyproject.toml`.

### Tests

49 green (22 new). New coverage in `tests/test_cli_smoke.py`:
- Parametrized help-lint across every subcommand
- `test_runner_imports_cliworker` (regression guard against reverting the delegation)
- `test_run_peer_wraps_cliworker_result` — runner returns proper PeerRunResult
- `test_run_peer_with_failure_still_writes_trace` — file-trace on failure path
- `test_run_peer_fast_kwarg_passes_through` — fast=True reaches cliworker
- `test_installer_returns_noop_for_codex_not_installed_file` — no broken file
- `test_install_cleans_legacy_codex_rules_file` — upgrade-path cleanup
- `test_init_creates_paircode_dir`, `test_status_finds_paircode_dir` — dispatch smoke

## 0.5.0 — M5: seal + JOURNEY + stage-progress status
- `paircode seal {research|plan|execute}` copies each peer's latest versioned output to `{peer}-FINAL.md`.
- `paircode focus <name>` now updates `JOURNEY.md` (sets active focus, appends history row).
- `paircode status` per-focus stage table with version count + sealed indicator.

## 0.4.0 — M4: full loop (research → plan → execute with peer reviews)
- `paircode stage {research|plan|execute} --rounds N` drives one stage for N rounds on the active focus.
- Round 1 = cold v1 for alpha + every peer in parallel.
- Rounds 2+ = each peer reviews alpha's v_N, alpha reads all reviews and writes v_{N+1}.
- `paircode drive "<topic>"` runs the full research → plan → execute loop; `--research-only` or per-stage `--research-rounds` / `--plan-rounds` / `--execute-rounds` flags for cost control.

## 0.3.0 — M3: handshake + drive (research stage)
- `paircode handshake` detects installed CLIs, proposes a peer roster.
- `paircode handshake --write` saves roster to `.paircode/peers.yaml`.
- `paircode drive "<topic>"` real subprocess invocation of `claude -p`, `codex exec`, `gemini -p`, `ollama run`.
- Per-peer timeouts, file-trace header on every output (peer_id/cli/model/duration/ok).

## 0.2.0 — M2: state + init + status
- `.paircode/` scaffold (JOURNEY.md, peers.yaml, peers/ dir, numbered focus dirs).
- `paircode init`, `paircode status`, `paircode focus <name>`.
- `state.find_paircode()` walks up the tree to find `.paircode/` from anywhere.

## 0.1.0 — M1: install across Claude/Codex/Gemini
- `paircode install` registers `/paircode` in every detected LLM CLI:
  - Claude Code: `~/.claude/commands/paircode.md`
  - Codex: `~/.codex/rules/paircode.rules`
  - Gemini: `~/.gemini/paircode.md`
- `paircode uninstall` cleans up.

## 0.0.1 — scaffold
- Package layout, pypi metadata, click CLI skeleton, initial diary.

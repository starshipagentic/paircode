# Diary 003 — Arch-B pivot: cold-use failure exposed Python-driven orchestrator as a regression

**Stardate:** 2026-04-20
**From:** v0.10.1 — Python-driven orchestrator (drive.py with ThreadPoolExecutor spawning fresh `claude -p` / `gemini -p` / `codex exec` subprocesses in parallel)
**Toward:** Arch B — interactive Claude session IS the team lead; Python shrinks to filesystem scaffolding + template rendering

**This diary is a preservation record, not a migration log.** No code has changed on `main` beyond this file. A companion branch `path-python-controls-stages` pins the current Python-driven state so we can return if Arch B underdelivers.

---

## What triggered this pivot

The maintainer ran `/paircode` cold in Claude Code after weeks away, trying to get a second opinion on an unrelated engineering question. He typed:

```
/paircode use gemini for reserach only to 'i mean go look at their actual releases...'
```

Four concrete failures in one invocation:

1. **Slash command pass-through failed.** `~/.claude/commands/paircode.md` instructs the LLM to pass args literally to the CLI. `paircode use gemini for research only to '...'` → `Error: No such command 'use'`. The slash command's own literal-pass-through instruction is the failing case.
2. **Fallback picked the wrong flag.** The previous session fell back to `paircode drive "<topic>" --alpha-cli gemini --research-only`. Wrong: `--alpha-cli` swaps the driver — it replaces Claude with Gemini as alpha. The maintainer wanted Claude (this session) to keep driving and Gemini to be added as a peer. Inverted alpha/peer.
3. **No primitive for "just get an opinion".** The architecture has `research → plan → execute`. "What does Gemini think of X" isn't any of those — it's review-of-existing. No native primitive. The previous session hacked it with `--research-only`, which is semantically wrong.
4. **Flag soup.** `--alpha-cli`, `--alpha-model`, `--timeout`, `--research-rounds`, `--plan-rounds`, `--execute-rounds`, `--research-only`. User has to pre-classify their task into flag combinations before typing the quoted prompt.

The redesign brief written mid-session (see conversation transcript 2026-04-20) names these as Gap 1–4.

## What the maintainer wants

Single verb CLI:

```
paircode "<whatever you want>"                      # ~95% of invocations
paircode "<whatever>" --peer gemini                 # filter roster to one peer
paircode "<whatever>" --peers gemini,codex          # subset
```

The LLM reads the quoted prompt and picks the right stages itself. Stages (research / plan / execute / ask-or-review) become invisible templates the LLMs consult, not CLI verbs the user types.

Plus the philosophy, stated verbatim in the session: *"my philosophy is auto fucking install bro!"* — setup work like `init`, `handshake` happens silently inside the main verb. Saved as a feedback memory under `/Users/t/.claude/projects/-Users-t-dev-paircode/memory/feedback_auto_install.md`.

## The architectural fork — Arch A vs Arch B

The real discovery of this session is that today's `drive.py` architecture is **the opposite of what worked in the maintainer's original mlmodel repo.** Comparing the two:

|  | Arch A — current paircode | Arch B — mlmodel pattern |
|---|---|---|
| Alpha identity | Fresh `claude -p` subprocess spawned by Python | Interactive Claude session where `/paircode` was typed |
| Alpha's context | None (headless, no memory, no session) | Full (session + user memory + project state) |
| Orchestrator | Python `ThreadPoolExecutor` in drive.py | The interactive Claude session itself, via its Bash + Agent tools |
| Claude peers | Fresh `claude -p` subprocess | In-process Agent tool subagents (background) |
| Codex/Gemini peers | `cliworker.run()` → shell subprocess | Bash subprocess |
| Runs after user closes Claude? | Yes (headless loop) | No (dies with session) |
| Python code surface | Large — drive.py, gates.py, ThreadPoolExecutor | Small — scaffold + template render |

**Evidence for Arch B being what the maintainer originally built:**

- `/Users/t/clients/syra/mlmodel/.claude/commands/peerkickoff.md` — team lead is the interactive Claude, spawns two Agent-tool subagents in parallel with `run_in_background=true`, then synthesizes.
- `/Users/t/clients/syra/mlmodel/.claude/commands/audit-me.md` — interactive Claude spawns one subagent that shells out to codex CLI for peer review.
- `/Users/t/clients/syra/mlmodel/.claude/commands/audit-codex.md` — interactive Claude does PART 1 (review) itself with full context, then spawns a subagent to fire codex for self-heal.
- **Zero Python orchestrator binary in mlmodel.** Slash command markdown + Bash + Agent tool handles everything.

The maintainer confirmed this was his "worked fucking great" baseline. Today's paircode drive.py is a regression introduced during vibe-coding that built a Python thread pool which spawns the very `claude -p` subprocess that strips alpha of its session context.

## Decisions made in this session

**CLI surface (user-facing):**
- `paircode "<prompt>"` — the one verb.
- `paircode` bare — prints current state (eats what `status` used to do).
- `paircode install` / `paircode uninstall` — stay. One-time setup that writes to `~/.claude`, `~/.codex`, `~/.gemini`. Maintainer explicitly said this is fine because users self-selected into it by installing paircode.
- **Dies as user verbs:** `init`, `handshake`, `status`, `focus`, `stage`, `seal`, `drive`.

**Auto-silent preconditions inside the main verb:**
- If `.paircode/` missing → `init_paircode()` runs silently.
- If `peers.yaml` empty / stale → handshake runs silently.
- Focus creation is procedural (`open_focus()` in state.py), always-new-per-invocation by default, escape hatch `--continue` to reuse the most recent unsealed focus when the previous team lead flaked.

**Semantic decisions vs mechanical decisions:**
- LLMs decide: is this a new topic? is this round converged? which focus to continue? who gets which stage?
- Python decides: where files go on disk, how directories are scaffolded, template rendering, roster persistence.

**Sealing + consensus (the maintainer's design):**
- Team lead (interactive Claude) runs multiple rounds from the one `/paircode` invocation.
- When the team lead has heard enough, it tells each peer to write their `{peer}-FINAL.md`.
- Team lead then writes its own `alpha-FINAL.md`.
- Team lead reads all FINALs and writes a **new artifact: `consensus.md`** — the very last thing before closing out the focus.
- **Current prompts in drive.py do NOT describe any of this.** The maintainer had believed sealing logic was already in the prompts; verification showed it is not. This is a real prompt authoring task, not a memory of existing work.

**Capability syntax rejected:**
- Brief proposed `--peer gemini:opine` / `--peer codex:work` for inline capability override.
- Maintainer explicitly dislikes this. Capability stays in `.paircode/peers.yaml` only; edit the file if you want to change it. No per-invocation override flag.

## Open tensions we are grappling with

1. **Headless execution.** Arch A can run for an hour unattended after the user closes Claude. Arch B dies with the session. mlmodel worked fine without headless, but this is a genuine capability loss. Does it matter for the paircode use cases? Unresolved. Preservation branch exists partly because of this.
2. **Claude-reviewing-Claude support.** mlmodel used Agent tool subagents for claude-on-claude peer review. paircode's current thesis is cross-vendor adversarial (different engines surface different blind spots). Do we keep Claude-on-Claude as an option or cut it for simplicity? Leaning toward cut, not decided.
3. **Consensus.md prompt authoring.** The final-round team-lead prompt needs to instruct: seal each peer, write your own FINAL, read all FINALs, write `consensus.md`, report. Not drafted yet.
4. **Codex + Gemini as team lead.** Slash commands are installed via satellites for all three CLIs. If `/paircode` is invoked inside Codex or Gemini (not Claude), can those hosts run the Arch B orchestration? Codex has subagent primitives; Gemini's are different. Cross-host parity for Arch B is an open question. Without parity, paircode is effectively Claude-first with Codex/Gemini as peers only.
5. **`cliworker` dependency.** If the slash command does all subprocess work via its host CLI's Bash tool, `cliworker.run()` leaves the runtime path. cliworker still matters for `paircode install` (marketplace add, extensions install via `invoke()`). The LLM-call speed-flag logic currently in cliworker.run becomes dead code from paircode's perspective.
6. **Testability.** Today's drive.py has unit tests (`tests/test_drive.py`). Arch B moves orchestration into slash command markdown, which is untestable by pytest. Smoke tests would have to shell out through a real LLM CLI — slow, flaky, costly. Mitigation: keep the procedural Python helpers (`init_paircode`, `open_focus`, template render, seal_stage) testable in isolation, and accept that the orchestration loop itself becomes an integration-test concern.

## Why we're preserving now

Arch B is a bet. It matches the maintainer's philosophy, it matches the pattern that worked in mlmodel, it dissolves Gap 1–4 cleanly. But it trades away:

- Headless execution
- A testable orchestration loop
- Cross-host parity guarantees (Codex/Gemini may not support the team-lead pattern as cleanly)

If any of those turn out to matter more than they look like they do today, we come back to this branch. The Python-driven orchestrator at v0.10.1 is a working, shipped system with 52 green tests. Killing it without preservation would be a mistake.

## Preservation details

- Branch `path-python-controls-stages` cut from `main` immediately after this diary commits.
- `main` continues toward the Arch B rewrite.
- The `drive` command, `run_stage`, `run_stage_cold`, `run_review_round`, `run_alpha_revision`, and the ThreadPoolExecutor orchestration in `drive.py` are expected to be deleted from `main` during the rewrite. They remain intact on the preservation branch.
- `state.py` (procedural scaffolding) stays on `main` unchanged — Arch B still uses it.
- `runner.py` / `cliworker` integration: fate undecided. See tension #5.

## Key files as of this diary

| Concern | File | Fate in Arch B |
|---|---|---|
| `/paircode` slash command (Claude) | `src/paircode/templates/claude_slash_command.md` | **Rewritten** — becomes the orchestrator |
| `/paircode` slash command (Codex) | `src/paircode/templates/codex_slash_command.md` | Rewritten; parity with Claude version tbd |
| `/paircode` slash command (Gemini) | `src/paircode/templates/gemini_slash_command.toml` | Rewritten; parity tbd |
| Python CLI | `src/paircode/cli.py` | Reduced to `paircode "<prompt>"`, `install`, `uninstall`, bare-state |
| Drive loop | `src/paircode/drive.py` | **Deleted** on main, preserved on branch |
| State scaffolding | `src/paircode/state.py` | Kept |
| Runner | `src/paircode/runner.py` | Undecided |
| Seal | `src/paircode/seal.py` | Kept as a helper the slash command can call silently |

*End of diary 003. Next session: draft the rewritten slash command template + the trimmed Python CLI.*

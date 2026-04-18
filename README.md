# paircode

**Multi-LLM peer review for your code, with file-traces on disk.** One primary LLM (alpha) + any number of peer LLMs (Codex, Gemini, Ollama, …) running independent research, plans, and code, with structured cross-review rounds stored entirely as Markdown on disk.

> Born from 31 iterations of dual-LLM silent-agreement hunting on a real ML project. See `diary/001-step-a-architecture.md` for the full design rationale.

## Install

```bash
pipx install paircode       # or: pip install --user paircode
paircode install            # registers /paircode in every detected LLM CLI
```

After install, `/paircode` is available in all three:

| CLI | File installed |
|---|---|
| Claude Code | `~/.claude/commands/paircode.md` |
| Codex CLI | `~/.codex/prompts/paircode.md` |
| Gemini CLI | `~/.gemini/commands/paircode.toml` |

Open any of them and type `/paircode`. In Gemini, you may need `/commands reload` the first time.

As of v0.8.0, paircode delegates all CLI invocation to [`cliworker`](https://pypi.org/project/cliworker/) — one place to own
the speed flags, MCP strip tricks, skip-cache, and subscription-first fallback
logic. paircode adds the peer-review orchestration on top (file-traces, stages,
gates, journey).

## Use it — three entry points

### 1. From Claude Code (or any supported LLM) as a slash command

Inside a Claude Code session:

```
/paircode drive "build a KISS PHQ-9 depression risk engine"
```

Claude relays that to the CLI. paircode opens a focus, runs research → plan → execute with peer-reviewed rounds, writes everything to `.paircode/` as Markdown.

### 2. From the shell directly

```bash
paircode init                                   # bootstrap .paircode/ in cwd
paircode handshake --write                      # detect CLIs + write peer roster
paircode drive "refactor the auth middleware"   # full loop
paircode status                                 # see where you are
```

### 3. Piece by piece

```bash
paircode focus "try GitHub Actions migration"
paircode stage research --rounds 2              # cold v1 + one review/revise round
paircode seal research                          # mark research FINAL
paircode stage plan --rounds 3
paircode seal plan
paircode stage execute
paircode seal execute
```

## What ends up on disk

```
your-project/
  .paircode/
    JOURNEY.md                    # fleet log (auto-updated)
    peers.yaml                    # who's on the team
    peers/
      peer-a-codex/               # peer's profile (and code if full-fork mode)
    focus-01-<slug>/
      FOCUS.md                    # this focus's goal, roster override, gate config
      research/
        alpha-v1.md ... alpha-vN.md
        peer-a-codex-v1.md ...
        reviews/round-01-peer-a-codex-critiques-alpha.md
        alpha-FINAL.md            # sealed exit artifact
        peer-a-codex-FINAL.md
      plan/
        (same shape)
      execute/
        (same shape)
    focus-02-<slug>/
      ...
```

Every LLM's every thought lands as a Markdown file. That's how heterogeneous LLM tools communicate reliably across vendors, sessions, and days.

## Three peer modes

| Mode | What the peer does | When to use |
|---|---|---|
| **full-fork** | Writes its own cold codebase + markdown artifacts | Silent-agreement hunting, safety-critical code |
| **pair-code** | Contributes directly to alpha's codebase via patches + reviews | Feature work, regular dev |
| **opinion-only** | Reads alpha's work, writes reviews, never touches code | Budget peers, quick sanity checks |

Configured per peer in `.paircode/peers.yaml`.

## Model compatibility

| CLI | Slash command | Subprocess driver | Status |
|---|---|---|---|
| Claude Code (`claude`) | ✓ `/paircode` via `~/.claude/commands/paircode.md` | ✓ `claude -p <prompt>` | stable |
| Codex (`codex`) | ✓ context rule via `~/.codex/rules/paircode.rules` | ✓ `codex exec <prompt>` | stable |
| Gemini CLI (`gemini`) | ✓ reference file at `~/.gemini/paircode.md` | ✓ `gemini -p <prompt>` | stable |
| Ollama (`ollama`) | — (local models, no slash-cmd primitive) | ✓ `ollama run <model> <prompt>` | stable |
| Aider / others | — | best-effort, PRs welcome | planned |

## Commands

```
paircode --help           full command list
paircode install          register /paircode in all detected LLM CLIs
paircode uninstall        remove /paircode from LLM CLIs (idempotent)
paircode handshake        detect CLIs, propose peer roster
paircode handshake --write save roster to .paircode/peers.yaml
paircode init             bootstrap .paircode/ in cwd
paircode status           summarize current state
paircode focus <name>     open a new focus
paircode focus            list existing focuses
paircode stage <name>     run one stage N rounds on active focus
paircode seal <stage>     seal stage — copy each peer's latest vN to {peer}-FINAL.md
paircode drive <topic>    full loop: research → plan → execute
```

## Why this exists

See [`diary/001-step-a-architecture.md`](diary/001-step-a-architecture.md) for the full backstory. The short version: running two LLMs adversarially surfaces silent-agreement bug classes that neither engine alone can catch, because cross-engine agreement is not the same as correctness when both share the same blind spot.

## License

MIT. See [LICENSE](LICENSE).

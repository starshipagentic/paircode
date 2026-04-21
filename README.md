# paircode

**Multi-LLM peer review for your code, with file-traces on disk.** One primary LLM (alpha, usually Claude Code) + any number of peer LLMs (Codex, Gemini, Ollama, …) running research / plan / execute / ask cycles with structured cross-review rounds stored entirely as Markdown on disk.

> Born from 31 iterations of dual-LLM silent-agreement hunting on a real ML project. See `diary/001-step-a-architecture.md` for the origin story and `diary/003-arch-b-pivot-grappling.md` for the current (v0.11) team-lead architecture.

## Install

```bash
pipx install paircode       # or: pip install --user paircode
paircode install            # registers /paircode in every detected LLM CLI
```

`paircode install` deploys `/paircode` into each LLM CLI it finds on your PATH:

| CLI | How it's installed | What you get |
|---|---|---|
| Claude Code | file-drop `~/.claude/commands/paircode.md` | `/paircode` slash command |
| Codex CLI | `codex marketplace add starshipagentic/paircode-codex` | `/paircode` slash command |
| Gemini CLI | `gemini extensions install github.com/starshipagentic/paircode-gemini --consent` | `/paircode` slash command |

In Gemini you may need `/commands reload` the first time. In Codex the marketplace fetches on first use.

paircode delegates LLM subprocess invocation to [`cliworker`](https://pypi.org/project/cliworker/) — that's where speed flags, MCP strip tricks, skip-cache, and subscription-first fallback live. paircode adds the peer-review orchestration on top (file-traces, stages, rosters, convergence).

## Use it

Inside any LLM CLI that has `/paircode` installed, just type:

```
/paircode "build a KISS PHQ-9 depression risk engine"
```

or

```
/paircode "review my auth middleware approach at src/auth/"
/paircode "plan the refactor" --peers codex,gemini
/paircode "get a second opinion on this PR" --peer gemini
```

The slash command's team-lead prompt (the LLM you're inside) reads your prompt, picks a stage (`research | plan | execute | ask`), fires peers, collects their markdown, iterates through review rounds until convergence, and writes `consensus.md` at the end. Everything lands under `.paircode/` in your current project.

## What ends up on disk

```
your-project/
  .paircode/
    JOURNEY.md                    # fleet log
    peers.yaml                    # roster: who's on the team
    peers/
      peer-a-codex/               # codex's persistent sandbox (code goes here)
      peer-b-gemini/               # gemini's persistent sandbox
    focus-01-<slug>/
      FOCUS.md                    # this focus's prompt + metadata
      research/
        alpha-v1.md ... alpha-vN.md
        peer-a-codex-v1.md ...
        reviews/round-01-peer-a-codex-critiques-alpha.md
        alpha-FINAL.md
        peer-a-codex-FINAL.md
        consensus.md              # team-lead synthesis (last thing written)
      plan/         (same shape)
      execute/      (same shape)
      ask/          (same shape)
    focus-02-<slug>/
      ...
```

**Code vs. reports.** Files inside `focus-*/` are markdown *reports* (opinions, plans, critiques, summaries of work). Actual code lives elsewhere:

- **Peers** code in their sandboxed workspaces at `.paircode/peers/<peer-id>/` — persistent across focuses.
- **Alpha** codes directly in the project root (the real repo) — alpha *is* the project.

## Stages

Stage is picked by the team-lead LLM based on the prompt:

| Stage | When | Typical prompt |
|---|---|---|
| `research` | Explore new ground | "build X", "find the right Y", "how should we approach Z" |
| `plan` | Concrete implementation plan from prior research | "plan the refactor based on focus-02" |
| `execute` | Do the work from an existing plan | "execute the plan at focus-02" |
| `ask` | Get opinions on existing work | "what does codex think of this PR", "review my approach at <path>" |

The team lead can chain stages in one invocation: `research → plan → execute → done`. No hard round cap — the team lead converges when peers stop surfacing new signal.

## Commands (the helper CLI)

Most users will only ever type `paircode install` and then use `/paircode` inside their LLM CLI. The binary's other commands are helpers the team-lead slash command calls on your behalf:

```
paircode                         print current .paircode/ state
paircode install                 register /paircode in every detected LLM CLI
paircode uninstall               remove /paircode from LLM CLIs (idempotent)
paircode ensure-scaffold         idempotent .paircode/ init + handshake (silent)
paircode focus new <slug>        create a new focus dir, print its path
paircode focus active            print the active focus path
paircode roster [--alpha <cli>] [--peer <id>] [--peers <id,id>]
                                 print peer ids, best-effort, never errors
paircode invoke <peer-id> "<prompt>" --out <path>
                                 fire one peer, write file-trace to --out
paircode converge <stage>        copy each participant's latest vN to *-FINAL.md
```

## Model compatibility

| CLI | `/paircode` slash command | Peer invocation | Parallel peers? | Status |
|---|---|---|---|---|
| Claude Code (`claude`) | ✓ file-drop at `~/.claude/commands/paircode.md` | ✓ `claude -p <prompt>` | ✓ via Agent tool + `run_in_background=true` | stable |
| Codex (`codex`) | ✓ via `codex marketplace add` | ✓ `codex exec <prompt>` | ✗ serial-only (codex constraint) | stable |
| Gemini (`gemini`) | ✓ via `gemini extensions install` | ✓ `gemini -p <prompt>` | ✗ serial-only (gemini constraint) | stable |
| Ollama (`ollama`) | — (local models, no slash-cmd host) | ✓ `ollama run <model> <prompt>` | n/a | peer-only |
| Aider / others | — | best-effort, PRs welcome | — | planned |

Peer roster is auto-detected at first install via `paircode handshake` (silent, called by `ensure-scaffold`). Edit `.paircode/peers.yaml` to customize.

## Why this exists

See [`diary/001-step-a-architecture.md`](diary/001-step-a-architecture.md). Short version: running two LLMs adversarially surfaces silent-agreement bug classes that neither engine alone catches — cross-engine agreement is not the same as correctness when both engines share a blind spot.

See [`diary/003-arch-b-pivot-grappling.md`](diary/003-arch-b-pivot-grappling.md) for why v0.11 moved orchestration out of a Python driver and into the slash-command's team-lead LLM.

## License

MIT. See [LICENSE](LICENSE).

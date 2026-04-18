# paircode

**Adversarial journey framework for LLM peer review.** Orchestrate one "alpha" codebase plus N peer LLMs through research → plan → execute stages, with file-trace peer review at every step. Born from 31 iterations of dual-LLM silent-agreement hunting on a real ML project.

> Status: **step-A scaffold, v0.0.1 pre-alpha.** The architecture and terminology are locked; the implementation lands in step B. See `diary/001-step-a-architecture.md` for the full design rationale.

## What it's for

You're building software. You have one primary LLM (Claude, usually) writing code with you. That's alpha. You also have access to one or more other LLMs — Codex, Gemini, Ollama, whatever — that you'd like to use as peer reviewers, cold-fork implementers, or opinion-only second voices.

paircode orchestrates all of that as structured file-traces on disk:

```
your-project/                       ← alpha's code (your actual codebase)
  src/, tests/, README.md, ...
  .paircode/                        ← hidden orchestration folder
    JOURNEY.md                      ← fleet log
    peers.yaml                      ← roster: who's on the team
    peers/
      peer-a-codex/                 ← peer's full-fork code + profile
      peer-b-gemini/                ← opinion-only peer's folder
    focus-01-ml-engine/
      FOCUS.md                      ← what this focus is about
      research/                     ← versioned .md per peer + FINAL-per-peer
      plan/                         ← same pattern
      execute/                      ← iteration logs + FINAL summary per peer
    focus-02-expand-features/
      ...
```

Every peer writes every thought to disk, in text files, at rest. That's how heterogeneous LLM tools communicate reliably across vendors, sessions, and days.

## The three layers

```
Journey  →  Focus  →  Stage
captain     per-goal   research | plan | execute
```

- **Journey** — the captain (you) steers through focuses over time: "ML engine" → "claims-data expansion" → "demo website" → "mobile app."
- **Focus** — a single goal worth a research/plan/execute cycle.
- **Stage** — one instance of the peer-review engine: all peers produce cold drafts, cross-review in N rounds, converge, emit FINAL artifacts.

## Three peer modes

| Mode | What the peer does | When to use |
|---|---|---|
| **full-fork** | Writes its own cold codebase, evolves independently, has opinions grounded in its own implementation | Silent-agreement hunting, safety-critical code, when you can afford it |
| **pair-code** | Contributes directly to alpha's codebase via patches / reviews / suggestions | Frontend work, features, regular development |
| **opinion-only** | Reads alpha's work, writes review `.md` files, never touches code | Budget peers (free-tier Gemini), quick sanity checks |

## Install (once step B lands)

```bash
pipx install paircode
paircode handshake        # detect installed LLM CLIs, propose roster
paircode install-claude   # register as /paircode slash command
paircode install-codex    # register with Codex CLI for peer invocation
```

## Current status

v0.0.1 is scaffold-only: `--help`, `--version`, and placeholder subcommands that print "not yet implemented." The design is complete; the implementation is next.

## License

MIT. See LICENSE.

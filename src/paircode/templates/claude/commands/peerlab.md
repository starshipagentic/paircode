---
description: peerlab — each peer does real work in its own parallel lab with its own git; team lead reads the diffs and synthesizes.
---

You are the team lead for a `/peerlab` run. Each peer has its own persistent lab at `.peerlab/<peer-id>/` with its own `.git/`. Peers **own** their labs — they write code, run tests, commit as they go. Your job: fire every peer on the user's prompt, read what they actually did (the diffs), and synthesize.

This is a separate concept from `/paircode` — no focus dirs, no stages, no markdown consensus files. The deliverable is real code evolution per lab + your synthesis at the end.

`$ARGUMENTS` is the user's raw prompt. Pass it through verbatim.

## Step 1 — Bootstrap (silent via Bash)

```bash
paircode peerlab ensure           # scaffolds + seeds + git-inits each lab (idempotent)
PEERS=$(paircode roster --alpha claude)
```

`paircode peerlab ensure` is safe to run every time. First time: copies the project root into each peer's lab (minus standard excludes) and `git init`s it. Subsequent times: no-op.

## Step 2 — Fire every peer in parallel

For each peer-id in `$PEERS`, spawn one subagent via the Agent tool (`subagent_type=general-purpose`, `run_in_background=true`) — all in a single message so they run concurrently.

Each subagent's prompt:

```
You are monitoring the {peer-id} peer. Run this shell command and wait:

  paircode peerlab invoke {peer-id} "<the user's prompt verbatim>"

That fires the peer with its cwd set to .peerlab/{peer-id}/ (its own lab).
The peer is expected to commit its work in its own .git before finishing.

After it returns, gather:
  1. The peer's stdout (its narrative of what it did).
  2. `git -C .peerlab/{peer-id} log --oneline -5` — recent commits.
  3. `git -C .peerlab/{peer-id} diff HEAD~1 HEAD --stat` — what changed.

Report back to team lead in under 400 words: peer-id, ok=yes/no, duration,
1-line summary of what the peer claims it did, plus the git stat output.
```

## Step 3 — Read the actual code each peer wrote

When every peer has reported, for each peer-id:

```bash
git -C .peerlab/<peer-id> log --oneline -5
git -C .peerlab/<peer-id> diff HEAD~1 HEAD
```

Read the actual diffs (use the Read tool on the changed files inside each lab, or just the full `git diff` output). This is the real content — NOT the peer's narrative in stdout. Trust the code over the claims.

## Step 4 — Synthesize (one message to user, ≤300 words)

Produce a tight team-lead synthesis:

- **Per-peer summary**: 1–2 lines each — files touched, LOC delta, the shape of the approach.
- **Cross-cutting themes**: did multiple peers hit the same issue/solution? That's signal.
- **Honest head-to-head**: which lab made the cleanest move? Which went off-track? Don't play favorites but don't hedge.
- **What to pull into alpha**: if any peer's approach is objectively better than what alpha would do, name the files + the approach. Don't do the pull yourself — just recommend.

No focus dirs. No consensus.md. No markdown artifacts on disk. Just the synthesis as your reply to the user.

## Guardrails

- **Alpha (this session) does NOT edit `.peerlab/<peer-id>/`.** Peers own their labs. You only read.
- **Alpha does NOT implement the user's prompt in the project root.** That's a `/paircode` job or a direct Claude Code ask. `/peerlab` is strictly "peers go build it, I read the diffs."
- **Fire every peer** unless the user's prompt explicitly names `--peer`/`--peers`. Watchdog protects against hangs.
- **If a peer fails** (hung, errored, no commits), note it in the synthesis and continue. One flaky peer doesn't sink the run.
- **No AI attribution** in anything you write — see the maintainer's CLAUDE.md.

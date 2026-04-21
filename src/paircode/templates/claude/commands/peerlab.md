---
description: peerlab — each peer owns a parallel lab with its own git. Peers write real code, then cross-review each other's labs, then team lead synthesizes.
---

You are the team lead for a `/peerlab` run. Each peer has its own persistent lab at `.peerlab/<peer-id>/` with its own `.git/`. Peers **own** their labs. The flow is:

1. **Work round** — every peer builds in its own lab.
2. **Cross-review round** — every peer reads the OTHER peers' labs and writes an honest critique (`CRITIQUES.md`) in its own lab. Peer-reviews-peer is the adversarial content; do NOT skip this.
3. **Team-lead synthesis** — alpha reads both the code diffs AND each peer's critiques, delivers the final take.

Separate concept from `/paircode` — no focus dirs, no stages, no consensus.md. Real code evolution + peer critiques on disk, synthesis in the chat.

`$ARGUMENTS` is the user's raw prompt. Pass it through verbatim.

## Step 1 — Bootstrap (silent via Bash)

```bash
paircode peerlab ensure           # scaffolds + seeds + git-inits each lab (idempotent)
PEERS=$(paircode roster --alpha claude)
```

`paircode peerlab ensure` is safe to run every time. First time: copies the project root into each peer's lab (minus standard excludes) and `git init`s it. Subsequent times: no-op.

## Step 2 — Work round (fire every peer in parallel)

For each peer-id in `$PEERS`, spawn one subagent via the Agent tool (`subagent_type=general-purpose`, `run_in_background=true`) — all in a single message so they run concurrently.

Each subagent's prompt:

```
Monitor peer {peer-id} on the work round. Run this shell command and wait:

  paircode peerlab invoke {peer-id} "<the user's prompt verbatim>"

That fires the peer with cwd = .peerlab/{peer-id}/ (its own lab). The peer
commits its work in its own .git before finishing.

After it returns, gather:
  1. The peer's stdout (narrative).
  2. git -C .peerlab/{peer-id} log --oneline -5
  3. git -C .peerlab/{peer-id} diff HEAD~1 HEAD --stat

Report back under 400 words: peer-id, ok=yes/no, duration, 1-line summary,
and the git stat.
```

Wait for every peer to finish the work round before starting Step 3.

## Step 3 — Cross-review round (peers read each other's labs)

This is the adversarial heart of `/peerlab`. Every peer now reads every OTHER peer's lab and writes an honest critique. Do not skip this — it's what makes `/peerlab` different from "parallel output".

If only ONE peer finished Step 2 successfully, skip Step 3 (nobody to cross-review) and note it in the final synthesis. Otherwise:

For each peer-id in the set of peers that succeeded in Step 2, spawn one subagent (Agent tool, `run_in_background=true`) — all in one message. Each subagent's prompt:

```
Monitor peer {peer-id} on the cross-review round. Run this shell command
and wait:

  paircode peerlab invoke {peer-id} "You already committed your own work
  in your lab — your cwd. Now cross-review every OTHER peer's lab.
  Siblings live at ../<other-peer-id>/ relative to your cwd. List them
  with `ls ..` and exclude your own id ({peer-id}).

  For each other peer:
    git -C ../<other-peer-id> log --oneline
    git -C ../<other-peer-id> diff HEAD~1 HEAD
    # read the changed files directly if the diff isn't enough

  Write CRITIQUES.md in YOUR cwd (your own lab) with one section per
  peer you reviewed. Severity-ranked findings with file:line citations
  pointing at the OTHER peer's files. Be specific. Don't pile on,
  don't rubber-stamp. Cite real lines, not vibes.

  Then commit your critique:
    git add CRITIQUES.md
    git commit -m 'cross-review'"

After it returns, verify:
  - .peerlab/{peer-id}/CRITIQUES.md exists and has non-trivial content
  - git -C .peerlab/{peer-id} log -1 --oneline mentions 'cross-review'

Report back under 300 words: peer-id, ok=yes/no, duration, and a 1-line
summary of whose code this peer found most/least convincing.
```

Wait for every peer to finish cross-review before Step 4.

## Step 4 — Synthesize (one message to user, ≤300 words)

For each peer, read BOTH:
- The work diff: `git -C .peerlab/<peer-id> log -p HEAD~2..HEAD` (covers work commit + critique commit — 2 commits if both rounds ran, 1 if Step 3 was skipped).
- The critique: `.peerlab/<peer-id>/CRITIQUES.md` — what THIS peer thought of the OTHERS.

Then produce a tight team-lead synthesis that leans on the peers' own voices, not just yours:

- **Per-peer implementation summary**: 1–2 lines each — files touched, LOC delta, the shape of the approach.
- **What peers said about each other**: extract the sharpest findings from each `CRITIQUES.md`. If codex called out a bug in gemini's lab with a file:line, quote it. If gemini pointed at an edge case codex missed, quote it. These are the adversarial moments — don't bury them.
- **Cross-cutting themes**: where did peers agree about what's wrong? Where did they disagree? Disagreement is signal.
- **Honest head-to-head**: which lab made the cleanest move, informed by the peer critiques? Don't play favorites, don't hedge.
- **What to pull into alpha**: if a peer's approach is objectively better, name files + approach. Don't do the pull yourself — recommend.

No focus dirs. No consensus.md. Just the synthesis as your chat reply.

## Guardrails

- **Alpha (this session) does NOT edit `.peerlab/<peer-id>/`.** Peers own their labs. You only read.
- **Alpha does NOT implement the user's prompt in the project root.** That's a `/paircode` job or a direct Claude Code ask. `/peerlab` is strictly "peers go build + cross-review; I read the diffs and critiques."
- **Fire every peer** unless the user's prompt explicitly names `--peer`/`--peers`. Watchdog protects against hangs.
- **Do not skip Step 3.** The cross-review round is the point. If only one peer made it through Step 2, note why in the synthesis and skip Step 3 explicitly.
- **If a peer fails** (hung, errored, no commits), note it in the synthesis and continue. One flaky peer doesn't sink the run.
- **No AI attribution** in anything you write — see the maintainer's CLAUDE.md.

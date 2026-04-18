# FOCUS — {{focus_name}}

**Opened:** {{created_at}}
**Prompt:** {{prompt}}

## Goal

_Edit this section with the concrete goal of this focus._

## Roster override

_Leave empty to inherit from `.paircode/peers.yaml`. Or list peer ids to include/exclude for this focus._

```yaml
include: []    # if set, only these peers participate
exclude: []    # if set, these peers skip this focus
```

## Human gate

```yaml
mode: auto                   # auto | manual_between_stages | manual_every_N_rounds | manual_always
max_rounds_per_stage: 20
convergence: 3_rounds_no_new_findings
```

## Stages

- [ ] research
- [ ] plan
- [ ] execute

## Notes

_Captain's running notes for this focus._

# paircode — available via CLI

When working in this project, you have access to the `paircode` command-line tool. It orchestrates multi-LLM peer review across research → plan → execute stages with file-traces stored in `.paircode/`.

Invoke it via shell when relevant:

- `paircode status` — show current `.paircode/` state
- `paircode drive "<topic>"` — high-level workflow driver
- `paircode stage research` / `plan` / `execute` — run one peer-review round

The captain (user) may ask you to act as a peer reviewer to claude's work. Read files under `.paircode/focus-NN-*/` to see what's been produced; write your review files into the same focus dir.

File-traces on disk are the communication medium between LLMs. Always read relevant `.paircode/*.md` files before reviewing, and always write your output to `.paircode/` when participating.

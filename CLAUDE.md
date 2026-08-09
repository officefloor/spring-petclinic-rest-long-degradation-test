# CLAUDE.md

The developer/agent guide for this repository is **[AGENTS.md](./AGENTS.md)**. It
covers the architecture and module map, the checkpoint lifecycle, the design pillars that
must not regress (blind-agent regression measurement, per-call config/memory
isolation), the acceptance-suite determinism + `mutates` discipline,
resilience/auth classification, how to run and analyze, and the 2026-08 gotchas.
It also carries the maintenance directive for keeping the docs current.

Read `AGENTS.md` before changing anything in `harness/` or `acceptance/`. For the
experiment's rationale and metrics see `README.md` (AGENTS.md supersedes the
README wherever they disagree).

> Note: this is the harness repo's own guide. It is **not** the `CLAUDE.md` the
> experiment pins into each arm's base repo (`isolation.pin_files`). That is a
> separate fixed guide handed to the checkpoint agent.

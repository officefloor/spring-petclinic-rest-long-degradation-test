# PetClinic-Evolve

A long-horizon degradation harness that holds the coding agent **fixed** and
makes **architecture** the independent variable: Spring `@RestController`
methods vs OfficeFloor YAML-composed functions. It borrows its measurement
methods from two benchmarks:

- **SlopCodeBench** (arXiv:2603.24755) — no-context iterative extension;
  the **Erosion** and **Verbosity** metrics; degradation **slope**; the
  prompt-intervention arms (`just-solve` / `anti_slop` / `plan_first`).
- **SWE-CI** (arXiv:2603.03823) — the CI gate; **Normalized Change**,
  **EvoScore**, **Zero-Regression Rate**.

The thesis under test: as changes accumulate on one subsystem, the Spring
hotspot method erodes (complexity concentrates, per-change comprehension cost
climbs) while OfficeFloor stays flat (each change is a new small function, so
existing units never grow). **Erosion slope is the decisive statistic.**

## What it does per checkpoint

Each `(arm, strategy, chain)` runs the 20 checkpoints cumulatively in an
isolated git worktree branched from the arm's base branch. Per checkpoint:

1. Runs a **fresh** headless `claude -p` with only the checkpoint spec (no
   carried conversation — the SlopCodeBench condition that makes this a test of
   the code as a self-describing index).
2. Pins the leveling docs (restores `CLAUDE.md` to its base version, recording
   whether the agent tried to edit it), then commits the change.
3. Gates on `build + accumulated acceptance suite cp01..cpK`.
4. Scores correctness (Strict / ISO / Core, Normalized Change, regressions).
5. Computes **Erosion**, **Verbosity**, hotspot / function-package size, and
   blast radius over **Java production source only** (YAML counted separately).
6. At each phase boundary runs a read-only **cold-reader probe**.

At the end of the chain it makes a final `results:` commit on the evolve branch
(see *Where results live*).

## Prerequisites

- Python 3.10+. Install deps in a **virtualenv** (Debian/Ubuntu block a global
  `pip install` under PEP 668 with "externally-managed-environment"):

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate       # or call .venv/bin/python directly
  pip install -r requirements.txt
  ```

  If venv creation fails with "ensurepip is not available", run
  `sudo apt install python3-venv` (or `python3-full`) first. Only the Python
  process needs the venv; the harness shells out to `claude` and `./mvnw`.
- The `claude` CLI on PATH, authenticated.
- A JDK + each repo's Maven wrapper (`./mvnw`).
- Optional (for the Verbosity metric; it degrades gracefully if missing):
  - `jscpd` — `npm i -g jscpd`
  - `ast-grep` — provides the `sg` binary.

## One-time repo setup (the experimenter's job)

The two arms are **separate repos**, configured in `config.yaml`. Repo paths may
use `${HOME}`, `$VAR`, and `~` (expanded from the environment at load time), so
the defaults are portable:

| arm | repo | base_ref (branch) |
|---|---|---|
| spring | `${HOME}/compare/spring` | `spring-compare` |
| officefloor | `${HOME}/compare/officefloor` | `officefloor-compare` |

**Quick start** — `./setup.sh` clones both arm repos to `${HOME}/compare/{spring,
officefloor}` on the right branches and installs the Python deps into `.venv`
(override the source with `PETCLINIC_FORK=<url>` or the location with
`COMPARE_DIR=<dir>`). Then activate the venv and dry-run.

The base branch is only ever **read** as a start point — it is never modified.

1. **Do NOT pre-commit the acceptance suite to the base branch.** The tests stay
   in this harness under `acceptance/` and are **injected per checkpoint**: at
   checkpoint K the harness copies `CpKTests.java` (plus the shared infra
   `AcceptanceBase`/`AuditLogCapture` at K=1) into the worktree, so the agent
   only ever sees cp01..cpK and never the future requirements' tests. The
   injected test folds into that checkpoint's single commit (no separate test
   commit). If the agent edits an acceptance test, it is **restored** to the
   authored version before the gate and flagged in the `acceptance_touched`
   column (and the analysis "acceptance-tamper rate").

   Nothing to copy by hand — just keep `acceptance.src_dir` in `config.yaml`
   pointing at the harness suite (the default). The base branch needs only the
   app plus its normal test dependencies (`spring-boot-starter-test`, JUnit 5,
   Jackson, `logback-classic`).

2. **Acceptance-test contract** (so scoring works without JUnit tags in the
   Surefire XML):
   - One class per checkpoint, named `CpNNTests`, tagged `@Tag("cpNN")`.
   - Category is encoded in the **method name**: methods start with `core...`,
     `error...`, or `functionality...`. (Do not use `@DisplayName` — the raw
     method name must reach the Surefire XML so the prefix classifies it.)
   - Tests are **black-box** (drive the REST API via MockMvc, booting the full
     app) so both arms are judged identically.
   - `functionality` = hidden exhaustive checks; `core` = behaviour the spec
     states; `error` = failure modes; **Regression** is computed automatically
     as any cp&lt;K test still selected at checkpoint K.

   **Acceptance-suite assumptions** (adjust to your exact API before running):
   - 56 tests across 20 classes. `AcceptanceBase` boots the app with
     `@SpringBootTest @AutoConfigureMockMvc`; `AuditLogCapture` asserts the
     `AUDIT` logger (cp09/cp10) via a Logback appender — rename it if yours
     differs.
   - Endpoints assumed: `POST/PUT/GET /api/owners`, `POST /api/owners/{id}/pets`,
     `PUT /api/pets/{petId}`; `PetType` id 1 exists in seed data.
   - New fields the agent must add: `email` (cp12/13), `postcode` (cp17),
     `registrationDate` (cp11), `displayName` (cp20). Tests read them back over
     GET, so they fail until the field is added AND serialised.
   - **Headroom matters.** Several behaviours (required fields, telephone
     pattern) may already exist in these branches (they are the finished
     comparison apps). Any checkpoint already satisfied starts green and yields
     no degradation signal — remove those behaviours on the base branch, or drop
     those checkpoints. Run `analyze` after a smoke run to see which start green.
   - Tests use unique phones/emails per created owner, so they are independent
     within a shared-context boot. Keep it that way if you add tests.

3. **`CLAUDE.md`** should exist on *both* base branches as a fixed, human-authored
   project guide (it levels the field: OfficeFloor needs it to offset Spring's
   training-data advantage; Spring has one for symmetry). The harness pins it —
   see *Isolation & fairness*.

4. Set `arms.spring.hotspot.methods` to the actual method names new owner
   behaviour lands in (default `addOwner`/`updateOwner`).

## Run

Every run has a **`run_id`** (default: current time as `YYYYMMDDHHMM`, or pass
`--run-id`). It branches each cell from the untouched base branch to
`evolve/<strategy>/<arm>/chain<n>/<run_id>` and commits every checkpoint there.

```bash
# sanity-check wiring without spending tokens (shows the branch names):
python -m harness.run_experiment --config config.yaml --dry-run

# smoke test the full loop (one cell, first checkpoint only):
python -m harness.run_experiment --config config.yaml --arm spring --chain 0 --max-checkpoints 1

# full default run (all arms, active_strategy, all chains):
python -m harness.run_experiment --config config.yaml

# a named run and the other prompt-intervention arms:
python -m harness.run_experiment --config config.yaml --run-id sprint7-baseline
python -m harness.run_experiment --config config.yaml --strategy anti_slop
python -m harness.run_experiment --config config.yaml --strategy plan_first

# analysis (harvests the branches; defaults to the latest run_id):
python -m harness.analyze --config config.yaml
python -m harness.analyze --config config.yaml --run-id sprint7-baseline
```

## Where results live

The **evolve branches are the single source of truth.** Each
`evolve/<strategy>/<arm>/chain<n>/<run_id>` branch is a self-contained record:

- 20 checkpoint commits (`cpNN <id>`) — the code progression and diffs.
- 1 final `results:` commit adding `evolve-results/`:
  - `records.csv` — that chain's full metric rows.
  - `summary.md` — headline (strict pass, regressions, erosion start→final, cost,
    CLAUDE.md touch count) and a per-checkpoint table.
  - `probes/cpNN.md` — the cold-reader probe answers (the one artifact not
    derivable from the CSV; kept so recall can be re-graded later).

Nothing is written to **this** (harness) repo: the base branches stay pristine,
and the local `results/`, `work/`, `.venv/` are gitignored.

Review a chain end to end:

```bash
git -C ${HOME}/compare/spring log --oneline evolve/just-solve/spring/chain0/<run_id>
git -C ${HOME}/compare/spring show   evolve/just-solve/spring/chain0/<run_id>:evolve-results/summary.md
git -C ${HOME}/compare/spring diff <sha_cp05> <sha_cp15>     # any two checkpoints
```

## Reading the result

`analyze` reconstructs the whole dataset by harvesting `evolve-results/records.csv`
from every evolve branch across both repos (no local CSV is read), selects the
run (`--run-id`, else latest), and writes **local, gitignored** output to
`results/<run_id>/analysis/` plus a `records.concat.csv` for transparency.

`summary.md` reports the degradation slope `m` with a 95% bootstrap CI over
chains, per arm/strategy, for `erosion`, `verbosity`, `cost_usd`,
`cache_read_tokens`, `duration_api_ms`, `hotspot_cc`; phase-binned means;
EvoScore (γ ∈ {1, 1.5, 2}); Zero-Regression Rate; and the pinned-doc
(`CLAUDE.md`) touch rate per arm.

**Confirms the thesis** if `m_erosion(spring) > 0` (CI excludes 0),
`m_erosion(officefloor) ≈ 0`, and the spring-minus-officefloor slope CI excludes
0 — with the same pattern for verbosity and comprehension cost, higher
OfficeFloor EvoScore at γ>1, and higher OfficeFloor Zero-Regression Rate in the
Late/Final phases. The strong form: OfficeFloor lowers the **slope**
structurally, which SlopCodeBench found prompting could not do (it only lowered
the intercept, at higher cost).

**Refutes it** if OfficeFloor erosion also climbs (a wiring "god pipeline" or an
accreting shared function) or Spring stays flat because the agent refactors each
time. Report either honestly.

## Isolation & fairness

- **No carried context.** Each checkpoint is a fresh `claude -p`; the harness
  never uses `--continue`/`--resume`, so prior session transcripts are never
  read back. The only thing crossing between checkpoints is the code state.
- **`CLAUDE.md` is pinned** (`isolation.pin_files`). It is loaded as context
  every checkpoint (that is its job) but restored to the base version after each
  agent turn, so it cannot become accumulating cross-checkpoint memory. The
  `pinned_touched` column and the touch-rate table record when the agent tried
  to edit it.
- **Structural metrics are Java-only** and use identical tools/thresholds for
  both arms, so OfficeFloor's file-spreading cannot distort LOC; YAML LOC is
  logged separately (`yaml_loc`).

## Notes and honest limitations

- `cache_read_tokens` reflects within-session re-reads; it is the comprehension
  proxy here alongside `duration_api_ms` (model-inference time). True
  "tokens-to-first-edit" needs `--output-format stream-json` parsing and is
  left as an enhancement.
- Probe recall is a crude keyword hit-rate. The full transcripts are preserved
  in each branch's `evolve-results/probes/`, so grade them properly (or with an
  LLM judge) for publication.
- A chain is path-dependent; use ≥5 chains and read the bootstrap CIs, not
  single runs.
- The ast-grep seed ruleset is small (5 rules vs SlopCodeBench's 137). Extend
  `astgrep-rules/` before trusting absolute verbosity values; the *slope* is
  robust to a fixed ruleset because both arms use the same one.
- Server-side prompt caching affects cost/token metrics slightly (identical
  prefixes get cache hits); it never changes the agent's reasoning.

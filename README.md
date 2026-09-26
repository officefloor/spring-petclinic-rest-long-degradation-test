## The paper for this test harness

Conserved amount, negotiable placement: prompting moves one architecture's complexity distribution and not the other's

Available: [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22967550.svg)](https://doi.org/10.5281/zenodo.22967550) 

# PetClinic-Evolve

<!-- MAINTAINERS: keep this README and AGENTS.md in sync with the harness on every
     behavioural change (see the maintenance directive at the top of AGENTS.md).
     This README is the experiment-facing doc (rationale, setup, run, read results);
     AGENTS.md is the harness-development guide and is the source of truth for
     internals. Update both together. -->

> **Developing or extending the harness?** Read **[AGENTS.md](./AGENTS.md)** (also
> referenced by `CLAUDE.md`) for the architecture, the checkpoint lifecycle, the
> design pillars, the acceptance-suite conventions, and the run/analyze internals.
> AGENTS.md supersedes this README wherever they disagree.

A long-horizon degradation harness that holds the coding agent **fixed** and
makes **architecture** the independent variable: Spring `@RestController`
methods vs OfficeFloor YAML-composed functions. It borrows its measurement
methods from two benchmarks:

> **Think a better AI would change the result?** The agent is fixed here on
> purpose, but the model is a one-flag override — re-run the whole experiment
> against any model and see whether the architecture signal holds. See
> **[docs/RUN_WITH_A_DIFFERENT_MODEL.md](docs/RUN_WITH_A_DIFFERENT_MODEL.md)**,
> and please share your branches back for independent replication.

- **SlopCodeBench** (arXiv:2603.24755): no-context iterative extension;
  the **Erosion** and **Verbosity** metrics; degradation **slope**; the
  prompt-intervention arms. The study runs four conditions — `just-solve` (control),
  `cohesion-prompt` (prompt lever), `impact_gated` (tool lever), `metric-in-prompt`
  (design-A, reproducibility) — plus the legacy `anti_slop` / `plan_first` prompts.
- **SWE-CI** (arXiv:2603.03823): the CI gate; **Normalized Change**,
  **EvoScore**, **Zero-Regression Rate**.

The thesis under test: as changes accumulate on one subsystem, the Spring
hotspot method erodes (complexity concentrates, per-change comprehension cost
climbs) while OfficeFloor stays flat (each change is a new small function, so
existing units never grow). The **decisive statistics** are *blast radius*,
*comprehension load* (`node_cc_median` — the complexity reachable from one handling
node, i.e. what you must understand to change one rule) and the
**structural-impact score** (the context-weighted cost of each change).

Two measurement cautions, both learned the hard way and documented in the glossary.
Whole-app **erosion** is location-blind and dominated by architecture-neutral leaf
algorithms, so it is reported for SlopCodeBench comparability only. And the
*entry-scoped* concentration metrics (`entry_cc`, `wmc_handler`, `erosion_handler`)
flatter a pipeline architecture, which can push work to the next node: OfficeFloor's
entry node is CC ~1.3 while its worst pipeline node reaches ~13, and its whole create
path carries the **same** total complexity as Spring's controller. What actually
differs is packaging — the same complexity in ~5x smaller units — which is what
`node_cc_median` and `node_exclusive_share` measure and `entry_cc` does not.

## How a run executes (start to finish)

There are two phases, invoked separately: `run_experiment` (drives the agent and
commits results onto branches) and `analyze` (reconstructs the data from those
branches and reports). File references point at `harness/`.

### Startup (`run_experiment.py:main`)

1. Compute a `run_id` (`--run-id`, else `YYYYMMDDHHMM`).
2. Load `config.yaml`. Every path is passed through `expand_path()`
   (`harness/__init__.py`): it expands `${HOME}`/`$VAR`/`~` and **fails fast**
   with a clear message if a variable is undefined; relative paths are then
   anchored to the config-file directory so the tree is movable.
3. Load `checkpoints.yaml` and number the checkpoints 1..N.
4. Loop over `arm × chain` (respecting `--arm` / `--strategy` / `--chain`). No
   local CSV is written by the run. Derived numbers are printed to the log only;
   `analyze` produces the CSV/tables from the branches afterwards.

### Per chain (`run_chain`)

`make_worktree` runs `git worktree add -b evolve/<run_id>/<strategy>/<arm>/chain<n>
<wt> <base_ref>`: a fresh checkout on a **new** branch started from the base
branch (note the order, `run_id` first). The base branch is only ever read,
never checked out, never committed to (a guard refuses any branch not under
`evolve/`).

Then, for each checkpoint `k` (1→N), in this exact order. Each checkpoint produces
**two commits**. An *agent* commit (exactly what the AI changed) followed by a
*reset* commit (the harness normalisation + setup for the next checkpoint):

0. **Blind agent view.** Only this checkpoint's own `CpKTests.java` (plus the
   shared infra) is present while the agent works, set by the *previous*
   checkpoint's reset commit (`set_agent_view`), or here at k=1. **The agent never
   sees prior tests.** This is deliberate: with a full checklist of prior tests
   visible, regressions are ~0 by construction. Blind, the agent must preserve
   earlier behaviour it cannot see, so a silent break becomes a measurable
   regression (see AGENTS.md → "Blind-agent regression measurement").
1. **Agent turn.** A **fresh** headless `claude -p` with only the checkpoint
   spec, no `--continue`/`--resume` (SlopCodeBench's no-carried-context
   condition), under a per-call login-only `CLAUDE_CONFIG_DIR` so no memory leaks
   between checkpoints or arms. Cost/tokens/`duration_api_ms` captured. On a
   **token/session limit OR an auth expiry**, the harness rolls back the attempt,
   **waits and retries the same checkpoint** (a manual `/login` mid-run resumes);
   a **transient** failure backs off short then retries (see AGENTS.md →
   "Resilience").
2. **COMMIT 1: `cpNN agent <id>`.** Parented on the pre-agent state, so its diff
   is **exactly what the agent changed**. `pinned_touched` / `acceptance_touched`
   are recorded first; the edits are *left in place* so this commit preserves them.
   An empty commit means a no-op checkpoint.
3. **Normalise + install the measurement suite:** restore `CLAUDE.md` to base (it
   can never become cross-checkpoint memory), then install the **full resolved
   cp01..cpK authored suite** (the priors the agent never saw), overwriting any
   agent test-tamper, both *before* the gate so a weakened visible test or edited
   guide can never produce a false pass.
4. **Gate** (`correctness.run_tests`). Compile, run `-Dgroups=cp01..cpK` on the
   full authored suite, parse Surefire XML. Classify by class (`CpNNTests`) and
   method prefix (`core`/`error`/`functionality`). Produce Strict / ISO / Core,
   **Normalized Change** (SWE-CI), and both `regressions` and `true_regressions`
   (the latter excludes breakage a mutative checkpoint intended, see the `mutates`
   discipline in AGENTS.md).
5. **COMMIT 2: `cpNN reset <id>`.** The harness normalisation plus
   `set_agent_view` for the **next** checkpoint (its own test only), so cp(K+1)
   starts blind and its agent commit stays pure. Kept even if empty, so every
   checkpoint is a clean two-commit boundary.
6. **Structural metrics** (Java production source only, `metrics.compute_all`),
   measured over the **agent commit** (`base_for_cp..agent`, i.e. the pure agent
   delta): `lizard` gives per-function CC/SLOC. Erosion is reported over **three
   scopes**: `erosion` over the whole app (SlopCodeBench-comparable), `erosion_scoped`
   over a **dynamic subsystem** (the production-Java files changed since `base_ref`,
   cumulative `git diff`), and `erosion_handler` over the entry handler's own class.
   Scoping stops one god method being diluted across ~280 unrelated functions, and
   because the subsystem is the touched-file set, a **new class the agent creates is
   automatically included** (no fixed-glob blind spot). The **hotspot** (single
   highest-CC function, with its name in `hotspot_fn`) is taken over that same
   subsystem. The erosions carry their `high_mass`/`total_mass` terms; `verbosity`
   carries its clone/pattern/union line counts; plus WMC/entry-handler, function-package
   size, blast radius (which excludes the injected tests via a git pathspec), and the
   context-weighted **structural-impact** score. Every structural number here is a **pure function of the
   committed source + git history**, so it is computed **only to narrate the
   progress log**, never persisted; `analyze` recomputes it. See *Capture vs.
   derive* below.
7. **Cold-reader probe** at each phase boundary: a read-only `claude -p` asks a
   fixed comprehension question; its raw text/cost/tokens go into the capture.
8. Write this checkpoint's **raw capture** (`capture/cpNN.json` + the agent event
   stream + the pre-normalization agent diff). The derived correctness/structural
   numbers are printed to the log for at-a-glance progress but **not stored**.

### Capture vs. derive (the expensive part is the commits, so capture only what's lost)

The agent turns are the costly, irreproducible part of a run. So the runner's job
is split in two:

- **Capture**: the per-checkpoint information that is *gone forever* if not
  recorded at the instant the agent runs, staged outside the worktree as the agent
  runs, then copied in and committed into `evolve-results/capture/` **as part of that
  checkpoint's reset commit (COMMIT 2)**, so each checkpoint commit is self-contained:
  - `cpNN.json`: the `request` (the spec **and** rendered prompt, so a checkpoint
    is self-describing without the harness repo); the agent envelope (cost/tokens
    incl. cache-creation, model, session id, stop reason, turns, durations) plus
    **`attempts`**, every try including failed/rate-limited ones with their
    cost/tokens and wait seconds, so true wall-clock and total (incl. wasted) cost
    are recoverable; the **raw `{test_id: passed}` map** + per-test timing/failure
    text (the atom behind regressions / Normalized Change / Zero-Regression Rate);
    pinned/acceptance flags; and this checkpoint's own `commit_sha` / base SHAs;
  - `cpNN.agent.jsonl`: the **full agent event stream** (every tool call, file
    read, command), the behaviour trace, otherwise discarded;
  - `cpNN.agent.diff`: the **true agent delta**, diffed *before* CLAUDE.md is
    pinned back and the acceptance tests are reset, so it preserves exactly what
    the agent did (including any reverted CLAUDE.md edit), which the normalized
    checkpoint commit can't reconstruct;
  - `cpNN.build.log`: the **full build + test console**, so a test that errors
    before producing a Surefire report (e.g. context startup) still leaves a trace;
Two run-level artifacts are **not** per-checkpoint capture. They are written **up
front in the branch's first `manifest:` commit** (`commit_run_manifest`), so a run
that dies partway is still self-describing and the control is recorded before it can
drift over a long chain:
  - `provenance.json`: model, harness git SHA, tool versions, and the **agent
    environment** (the CLI invocation flags plus hashes of the settings files and
    names of MCP servers / relevant env vars, hashes and names only, never contents
    or values, so the experiment's *control* is recorded without leaking secrets). It
    is **static**: no `checkpoint→SHA map` (that is derivable, each `cpNN.json`
    carries its own `commit_sha`, `""` for a no-op turn, so `analyze` reads it from
    the capture records and provenance never needs rewriting);
  - `config/`: a **snapshot of the analysis-shaping config** (`config.yaml`,
    `checkpoints.yaml`, `astgrep-rules/`), so the run is self-contained: `analyze`
    derives with the config that *shaped this run*, not whatever is live later.

Per-test `detail` also records **skipped** tests (excluded from scoring, so
"skipped" is distinguishable from "never selected").
- **Derive**: everything else (correctness scores, erosion, verbosity, blast
  radius, coupling, WMC, entry-handler, …) is a pure function of the commits +
  capture, so it is **never persisted**: `analyze` always rebuilds it from the
  checkpoint commits (materializing each in a throwaway detached worktree and
  calling the same `metrics.compute_all`, re-scoring correctness from the raw test
  map). **This is what lets you add a new metric and apply it to old runs without
  re-invoking the agent.** Do many runs once, analyse them from new angles forever.

### End of chain (`commit_chain_results`)

The final `results:` commit is a **completion marker**, an `--allow-empty` commit
carrying the summary headline, plus an `assemble_into` backstop for any capture not
already committed. Its presence on the branch means the chain *finished* (vs. dying
partway). It normally adds nothing new: `provenance.json` + `config/` already landed
in the **manifest** commit at the start, and each checkpoint's raw capture in its
**reset** commit. No derived table is stored. So each branch =
**1 manifest commit + 2N checkpoint commits (agent + reset per checkpoint) + 1
results marker**. Nothing is written to the harness repo.

### Analysis (`analyze.py`, run separately)

`analyze` **always recomputes** from the branches. The single source of truth is
the checkpoint commits + `capture/`, and nothing derived is read back. It
enumerates checkpoints from the per-checkpoint capture records' `commit_sha` (so
no-op checkpoints, recorded as `""`, are included) and derives with the run's own
`config/` snapshot (so metrics match how
that run was configured, not the live config). For the selected run it materializes
each checkpoint tree, runs `metrics.compute_all` over its source, re-scores
correctness from the captured raw test map, and writes gitignored output to
`results/<run_id>/analysis/`: degradation slope `m` with bootstrap CIs, phase
means, EvoScore, Zero-Regression Rate, the pinned-doc touch rate, the
acceptance-tamper rate, and PNG plots.

```
python -m harness.analyze --config config.yaml --run-id <id>
```

Add a metric to `metrics.compute_all`, re-run this, and it applies to every past
run. Structural metrics need only the commits; correctness/agent columns come
from `capture/` (blank for any older run recorded without it).

> Note on the two commits: COMMIT 1 (agent) preserves the agent's acceptance-test
> edits and CLAUDE.md edits for review, but step 3 restores both to authored/base
> *before* the gate, so a weakened test or edited guide can never produce a false
> pass. The edits are flagged in `acceptance_touched` / `pinned_touched`, and the
> reset (in COMMIT 2) carries the real test forward so cp(k+1)'s agent must satisfy
> it too.

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
  - `jscpd`: `npm i -g jscpd`
  - `ast-grep` provides the `sg` binary.

## One-time repo setup (the experimenter's job)

The two arms are **separate repos**, configured in `config.yaml`. Repo paths may
use `${HOME}`, `$VAR`, and `~` (expanded from the environment at load time), so
the defaults are portable:

| arm | repo | base_ref (branch) |
|---|---|---|
| spring | `${HOME}/compare/spring` | `spring-compare-no-tests` |
| officefloor | `${HOME}/compare/officefloor` | `officefloor-compare-no-tests` |

> The `*-no-tests` branches carry the app plus its test dependencies but **no
> pre-existing test suite**, so the only tests in play are the harness-injected
> acceptance suite. This removes the arm-asymmetric base tests (a compile-coupling
> and unguarded-tamper confound). The original `spring-compare` / `officefloor-compare`
> branches (with their shipped tests) remain for reference.
>
> **Why this matters. The real asymmetry.** When a shipped test suite is present,
> the agent runs it every turn and will *extend* it. It effectively builds its own
> regression net as it works. How much net it builds is correlated with the
> architecture. In the runs with tests, the Spring agent grew the existing controller
> test with duplicate and conflict assertions. A single `@RestController` invites an
> end-to-end MockMvc test that covers accumulated behaviour. The OfficeFloor agent
> added little executable coverage. Its logic is spread across many small wired
> functions with no single controller to target. So keeping the tests hands one arm a
> stronger self-built regression suite than the other. That confounds the correctness
> comparison. Removing the tests makes the harness-injected acceptance gate the *only*
> correctness signal, equal for both arms. (Whether an architecture leads the AI to
> build better regression protection is itself interesting. But it is a separate
> question. Measure it on its own. Do not bake it into the degradation comparison.)

**Quick start.** `./setup.sh` clones both arm repos to `${HOME}/compare/{spring,
officefloor}` on the right branches and installs the Python deps into `.venv`
(override the source with `PETCLINIC_FORK=<url>` or the location with
`COMPARE_DIR=<dir>`). Then activate the venv and dry-run.

**Reset.** `./clean.sh` is the inverse of `setup.sh`: it removes the arm repos
(and every `evolve/<run_id>/…` branch), the `work_root` area (worktrees, capture,
analyze scratch), and `sandbox_root` (the agent's history-less sandbox project dir).
It prompts first (skip with `-y`), keeps `.venv` and `results/` unless you pass
`--venv` / `--results`, and honours the same `COMPARE_DIR=` / `WORK_ROOT=` /
`SANDBOX_ROOT=` overrides. Run `./clean.sh -y && ./setup.sh` for a full clean rebuild.

**Publish.** `./push.sh [run_id]` pushes each arm repo's `evolve/<run_id>/…` chain
branches to the fork, so every chain's record survives outside the local clone. It
pushes only what is missing or stale on the remote, never force-pushes a diverged
branch, and refuses to run while an arm worktree is dirty (`--allow-dirty` overrides;
`--dry-run` lists without pushing). `setup.sh` clones over https, which has no
credentials in a non-interactive shell, so the push target defaults to the ssh form of
`origin` (`PUSH_HTTPS=1` or `PUSH_URL=<url>` to override). **Push before you clean** —
`clean.sh` deletes the arm repos and every unpushed `evolve/…` branch with them. The
aggregate `results/<run_id>/` CSV + analysis stay local and gitignored either way.

The base branch is only ever **read** as a start point. It is never modified.

1. **Do NOT pre-commit the acceptance suite to the base branch.** The tests stay
   in this harness under `acceptance/` and are **installed per checkpoint**. While
   the agent works it sees **only this checkpoint's own `CpKTests.java`** (plus the
   shared infra `AcceptanceBase`/`AuditLogCapture`), never the prior tests (the
   blind-agent design). The full cp01..cpK suite is installed only for the
   post-commit gate. If the agent edits a *visible* test it is restored to authored
   before the gate and flagged in `acceptance_touched` (and the analysis
   "acceptance-tamper rate").

   Nothing to copy by hand. Keep `acceptance.src_dir` in `config.yaml` pointing at
   the harness suite (the default). The base branch needs only the app plus its
   normal test dependencies (`spring-boot-starter-test`, JUnit 5, Jackson 3
   (`tools.jackson`), `logback-classic`).

2. **Acceptance-test contract** (so scoring works without JUnit tags in the
   Surefire XML). Full detail in **AGENTS.md → "The acceptance suite"**:
   - One primary class per checkpoint, `CpNNTests`, tagged `@Tag("cpNN")`; a
     mutative checkpoint also ships `cpNN/CpMMTests.java` replacements that
     overwrite the prior tests it changes (the `mutates` discipline).
   - Category is encoded in the **method name** (`core`/`error`/`functionality`);
     do not use `@DisplayName` (the raw method name must reach the Surefire XML).
   - Tests are **black-box** (MockMvc, full app boot) so both arms are judged
     identically, and **deterministic**. Every assertion is an exact/computed/
     pinned value (never `exists`/a TODO), because the suite is the regression
     oracle.
   - `regressions` = any prior test that fails at checkpoint K; `true_regressions`
     excludes failures a mutative checkpoint intended (its `mutates` list).

   **Current suite:** 60 primary `CpNNTests` + the mutative `cpNN/` replacements +
   shared infra. `AcceptanceBase` boots the app with `@SpringBootTest
   @AutoConfigureMockMvc` and holds the pinned reference tables + hash/Luhn/
   business-day helpers; `AuditLogCapture` asserts the `AUDIT`/`NOTIFY` loggers.
   All rules land on `POST /api/owners`, except cp46 which converts the
   pre-existing `DELETE /api/owners/{id}` from a hard delete to a soft delete.

   > **Headroom / base-app assumptions matter.** The arm base branches are the
   > finished comparison apps, so some behaviour may already exist (e.g. both ship a
   > *hard-delete* owner DELETE, cp46 depends on that). A checkpoint already
   > satisfied starts green and yields no signal. Smoke-run and check before a full
   > run.

3. **`CLAUDE.md`** should exist on *both* base branches as a fixed, human-authored
   project guide (it levels the field: OfficeFloor needs it to offset Spring's
   training-data advantage; Spring has one for symmetry). The harness pins it.
   See *Isolation & fairness*. (This is the arm-repo guide, distinct from the
   harness repo's own `CLAUDE.md`/`AGENTS.md`.)

4. Set `arms.<arm>.entry_handler` to the ONE create function whose complexity
   trajectory is tracked (default Spring `OwnerRestControllerV1::addOwner`,
   OfficeFloor `BuildOwner::service`); the hotspot/erosion subsystem is otherwise
   dynamic (files changed since `base_ref`), so no fixed method list is needed.

## Run

Every run has a **`run_id`** (default: current time as `YYYYMMDDHHMM`, or pass
`--run-id`). It branches each cell from the untouched base branch to
`evolve/<run_id>/<strategy>/<arm>/chain<n>` and commits every checkpoint there.
`make_worktree` is idempotent per run_id, so passing an existing `--run-id` with
`--arm`/`--chain` re-runs just that cell (e.g. to redo a chain lost to an auth
stall) without touching completed chains.

`--test-mode` is **required** on every run (no default). It selects which acceptance
tests the agent sees while it works. `blind` gives it only this checkpoint's own test,
neutralised (prior tests hidden). `full` gives it the whole cp01..cpK regression suite
with real `CpNN` names. The post-agent gate runs the full authored suite either way, so
the correctness scoring is identical across modes. Only the agent's test visibility
changes. The chosen mode is printed at the top of each checkpoint and recorded in
`provenance.json` (`test_mode`), so a chain's mode is always recoverable.

```bash
# sanity-check wiring without spending tokens (shows the branch names + mode):
python -m harness.run_experiment --config config.yaml --test-mode blind --dry-run

# smoke test the full loop (one cell, first checkpoint only):
python -m harness.run_experiment --config config.yaml --test-mode blind --arm spring --chain 0 --max-checkpoints 1

# full default run (all arms, active_strategy, all chains), blind vs full-suite conditions:
python -m harness.run_experiment --config config.yaml --test-mode blind
python -m harness.run_experiment --config config.yaml --test-mode full

# a named run and the four study conditions (impact_gated has its own section below):
python -m harness.run_experiment --config config.yaml --test-mode blind --run-id sprint7-baseline
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy just-solve       # 1. control
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy cohesion-prompt   # 2. prompt lever
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy metric-in-prompt  # 4. reproducibility (design-A prompt)
# legacy prompt arms:
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy anti_slop
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy plan_first

# reproduce with a DIFFERENT AI model (the model is the only variable that changes):
python -m harness.run_experiment --config config.yaml --test-mode blind --model claude-opus-5 --run-id opus5

# analysis (recomputes from the branches' commits + capture; defaults to latest run_id):
python -m harness.analyze --config config.yaml
python -m harness.analyze --config config.yaml --run-id sprint7-baseline
```

**Want to try a different AI model?** The full walkthrough — cost/time budgeting,
what to compare, and how to share your run back for independent replication — is
in **[docs/RUN_WITH_A_DIFFERENT_MODEL.md](docs/RUN_WITH_A_DIFFERENT_MODEL.md)**.

## The impact-gated pipeline (ImpactGate refactor gate)

Every strategy above just *implements* each checkpoint; concentration is observed, never
acted on. The **`impact_gated`** strategy instead puts [ImpactGate](../ImpactGate)
in the merge path as a gate that **triggers refactors**. The thesis it tests: given
an active structural-impact gate and a refactor budget, does each architecture reach
cp60, and can prompting flatten the **`node_cc_median`** (comprehension-load) slope —
the concentration the fixed prompt could not, in the prior run, keep out of Spring's one
growing handler?

This is **condition 3 of the four-condition study** (see `config.yaml: prompt_strategies` for the
canonical statement): `just-solve` (control), `cohesion-prompt` (prompt lever), `impact_gated`
(tool lever, below), and `metric-in-prompt` (design-A formula prompt, kept for reproducibility).

**The per-checkpoint loop** (only when `--strategy impact_gated`; every other strategy
is an untouched control). Default `enforcement: advisory`:

1. **Implement.** The agent implements the checkpoint (same isolation, same blind view) with the
   **NEUTRAL** prompt (spec only, no formula — design B). The AI is never told the metric it is
   scored on; telling it (the `metric-in-prompt` condition) got Goodhart-gamed — measured over
   10 chains per arm in `blind-202609010045`: 45× lower impact slope, *unchanged* total
   complexity (it relocated into new files), ~21 new static-utility classes per Spring chain,
   and `strict_pass` 0.787 → 0.440. See **AGENTS.md → "Condition 4 measured"** for the full
   result and the caveats.
2. **Score.** The production diff is staged and scored by the standalone `impact-gate`
   CLI: `impact-gate score --mode staged --curve`, graded against the reference distribution.
3. **Below `block_percentile`?** **Accept**; continue to the normal correctness gate, **and record
   the impact** (`ig_impact_first == ig_impact`, no refactor needed).
4. **At/above?** **Discard the change** (worktree reset to the clean pre-checkpoint state) and run
   **one** refactor turn on that clean base, told which classes ImpactGate flagged (**locations
   only, no cost figures**) and the change that is coming. Its own added lines must pass the
   deterministic **quality gate** (jscpd clones + ast-grep smells); it is committed as
   **`cpNN refactorM <id>`**.
5. **Re-attempt & record.** The change is re-implemented on the refactored base and re-scored
   (`ig_impact`). `max_refactors` defaults to **1** — one clean-up refactor, then re-attempt.
6. **Accept & continue (advisory).** The re-attempt is **accepted whatever its grade**; the chain
   never stops and reaches cp60. Both the direct (`ig_impact_first`) and post-refactor (`ig_impact`)
   impacts are recorded, so `analyze` reports the one-refactor cohesion effect per checkpoint,
   comparable to `just-solve` / `cohesion-prompt`.
   - Set **`enforcement: block`** to run the design-B HARD gate instead: still over the line after
     `max_refactors` → chain stops (`stop_reason=impact`); a refactor that will not come statically
     clean within `max_review_turns` → chain stops (`stop_reason=quality`). `stop_scope` (`chain`,
     default, vs `run`) then decides whether the other arms/chains still run. Retained as the
     stress-test condition; not the default.

So a gated checkpoint's commits are `0..N × cpNN refactorM` + `cpNN agent` + `cpNN reset`.
The refactor commits are ancestors of the agent commit, so `analyze` (which enumerates from
the agent commit) materializes a checkpoint tree that already includes them — erosion / WMC /
entry-CC snapshots reflect refactor+implement with no analysis rework. ImpactGate's measure is
the **same before-context-WMC** signal `analyze` reports as `impact_composite`, so the gate
gates exactly the erosion metric the run analyses.

**Configure** it under `impact_gate:` in `config.yaml` — `cmd` (how to invoke `impact-gate`),
`strategy` (the activating strategy name), `enforcement` (`advisory` default / `block`),
`baseline_file` (a reference-arm distribution to grade against; null → the seed) +
`curve_prior_weight` (0 → grade purely against it), `block_percentile` / `warn_percentile`,
`max_refactors` (default 1), `max_review_turns`, `stop_scope` (only under `block`),
`implement_strategy` (the neutral implement prompt, design B), `record_refactor_correctness` (run
the full gate on each refactor, recorded but never enforced), and the `refactor_prompt` template
(`{spec}`/`{files}`/`{drivers}`/`{grade}`/`{block}` placeholders). **Neither** `impact_gated` prompt
states the impact formula (design B): the implement turn is neutral and the `refactor_prompt` is
symptom-only. The formula is handed to the AI **only** in the separate `metric-in-prompt` strategy
(condition 4, reproducibility) and in `impact_stats` in `metrics.py` — keep those in sync if the
measure changes.

### Calibrating the gate to OfficeFloor's cohesion (the experiment)

The [prior run](https://blog.officefloor.net/2026/08/the-same-complexity-one-unit-or-twenty.html)
showed OfficeFloor spreads work into many small wired functions and does **not** erode into god
classes, while Spring's one `@RestController` does. So the real question is: **can the refactor
prompting hold Spring to OfficeFloor's cohesion?** Answer it by grading every change not against
ImpactGate's generic OSS seed but against **OfficeFloor's own observed change-impact distribution**:

The reference distribution is **already built and committed** at `baselines/officefloor.json`
(from the prior run `blind-202608100006`), and `config.yaml` already points at it, so a fresh
checkout needs no rebuild. To regenerate it (e.g. from a newer OfficeFloor run):
```bash
python -m harness.build_impact_baseline --config config.yaml --run-id blind-202608100006 \
    --arm officefloor --strategy just-solve --out baselines/officefloor.json
```
It reads the run's per-checkpoint `impact_composite` (from `results/<run_id>/records.concat.csv`,
or recomputed with `--recompute`) and writes an ImpactGate baseline JSON, printing the
percentile → composite grid. The gate points at it via `impact_gate.baseline_file`
(committed in-repo so it travels with a checkout) with `curve_prior_weight: 0` (grade **purely**
against OfficeFloor, ignoring the seed). So `block_percentile` is read against OfficeFloor:
**95 = "refactor when a change is more impactful than 95% of OfficeFloor's changes."**

This one shared cutoff is applied **identically to both arms** — run `--strategy impact_gated`
with **no `--arm` filter** and Spring *and* OfficeFloor are graded against the same OfficeFloor-derived
line, so OfficeFloor is held to it too (a drift into a "god pipeline" would fire). A *lower*
`block_percentile` is the *stricter* end (harder to pass); a *higher* one is more lenient.

> **Pick the percentile deliberately.** From `blind-202608100006`, OfficeFloor's `impact_composite`
> is p50≈369, p90≈3,410, p95≈5,922, p98≈14,148. Spring's *median* change (≈4,736) already exceeds
> OfficeFloor's p90. The shipped default is **p95 (composite ≈5,922)**: OfficeFloor fires on ~5% of
> its own changes, Spring on ~45% — held to OfficeFloor's cohesion without being impossible to pass.
> Raise toward **p98 (≈14,148, ~30% of Spring)** for more headroom; lower toward **p90 (≈3,410, ~61%
> of Spring)** for OfficeFloor's *typical* cohesion (stricter, early stops likely). Leave
> `baseline_file: null` to fall back to the generic seed curve instead.

### Setting up `impact_gated` on a fresh machine

A checkout of the harness + `~/ImpactGate` on `main` is **not** quite enough. Do all of this,
then leave it running (a full gated run is 60 checkpoints × 2 arms × 10 chains and can run for
days):

1. **Clone to matching `${HOME}` paths.** `config.yaml` resolves `~/compare`, `~/pe-work`,
   `~/sandbox`, and `~/ImpactGate/.venv/...` from `${HOME}`. Keep ImpactGate at `~/ImpactGate`.
2. **`./setup.sh`** — clones the arm repos to `~/compare/{spring,officefloor}` on their base
   branches and builds the harness `.venv`.
3. **Create ImpactGate's venv** (venvs are gitignored; the default `impact_gate.cmd` points at
   `~/ImpactGate/.venv/bin/impact-gate`):
   ```bash
   cd ~/ImpactGate && python3 -m venv .venv && .venv/bin/pip install -e . 'lizard==1.23.0'
   ```
   Alternatively set `impact_gate.cmd: ["impact-gate"]` and use setup.sh's editable install in
   the harness venv (run with that venv activated). **Pin the same lizard as
   `requirements.txt`** — that venv's parser decides every gate verdict, and lizard 1.24.0
   cannot parse `@Entity`/`@Table` classes at all, so changes to them score 0 and can never
   fail the gate (`setup.sh` applies the pin for you when `~/ImpactGate/.venv` exists).
4. **The baseline travels with the repo.** `baselines/officefloor.json` is committed and
   `config.yaml` points at it, so there is nothing to copy. (It is a run *input*. The source
   run's evolve branches are on GitHub, but rebuilding on a fresh clone means fetching those
   heads into local `refs/heads/evolve` then a slow recompute, so the 4 KB file is committed to
   keep the config self-contained.)
5. **Landlock (Linux only).** The blind-agent confinement uses Landlock and **fails closed**: on
   macOS or a kernel without Landlock, every checkpoint is *refused*, not run. Verify first:
   `python harness/landlock_selftest.py` (expect `OVERALL: PASS`).
6. **`claude` auth is the top unattended risk.** Quota/session limits auto-wait and resume, but
   an auth/OAuth expiry needs a manual `/login` and will otherwise stall the run. Ensure a
   long-lived login and check in periodically. The auth-dead signature is `$0 / 1 turn / empty
   commit`.
7. **Disable sleep/hibernate** (hibernation interrupts a run):
   `sudo systemctl mask sleep.target suspend.target hibernate.target`, and set lid-close to
   ignore.
8. **JDK + Maven** present; the first `./mvnw` build downloads dependencies (needs network), then
   `~/.m2` is warm.

**Pre-flight** (before leaving it for the week):
```bash
python harness/landlock_selftest.py                                   # OVERALL: PASS
python -m harness.parser_selftest --config config.yaml                # OVERALL: PASS
python -m harness.run_experiment --config config.yaml --test-mode blind \
    --strategy impact_gated --dry-run    # line reads: block p95 vs baseline officefloor.json (K=0)
```

The parser check proves both measurement stacks — this venv's lizard and the `impact-gate`
CLI's own — can still see methods on an annotated (`@Entity`/`@Table`) class. It runs
automatically at the start of every run and refuses to proceed if either is blind, because
a file the parser cannot read scores as zero complexity rather than as an error.

**Run and read it:**

```bash
# wiring check (shows the gate is ON, the block percentile, and the resolved impact-gate cmd):
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy impact_gated --dry-run

# smoke one cell / one checkpoint:
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy impact_gated --arm spring --chain 0 --max-checkpoints 1

# full gated run for both arms, then analyze (compares impact_gated vs just-solve per arm):
python -m harness.run_experiment --config config.yaml --test-mode blind --strategy impact_gated
python -m harness.analyze --config config.yaml
```

`analyze` adds an **ImpactGate pipeline** table (per arm: chains that reached the final
checkpoint, stop count, share of checkpoints needing a refactor, mean refactors/checkpoint,
summed refactor cost, and the accepted change's mean grade) and per-checkpoint columns
`ig_refactors` / `ig_passed` / `ig_stopped` / `ig_grade` / `ig_refactor_cost_usd` /
`ig_refactor_tokens`. The headline comparison is the **`node_cc_median`** slope (comprehension
load — the CC you must hold to change one rule; the decisive concentration statistic, and
relocation-proof so a refactor can't just push complexity to the next node), with
**`node_exclusive_share`** (cohesion) alongside it, `impact_gated` vs `just-solve` per arm.
Confirmation for the gate: Spring's `node_cc_median` slope *flattens* under `impact_gated`
(the refactors decompose the god-method so no single node's reachable complexity keeps
climbing) while its cohesion holds, and it still reaches cp60 — without the gate lowering
the *slope* being the strong result SlopCodeBench found prompting alone could not achieve.
(`entry_cc` / `wmc_handler` / `erosion_handler` are reported too but flatter a pipeline
architecture — they can read flat while work piles into a later node — so they are not the
decisive line here.) Each checkpoint's capture record carries an
`impact_gate` block (per-attempt grade/verdict/flagged-files, and the refactor turns'
irreproducible cost/tokens).

## Where results live

The **evolve branches are the single source of truth**, and they carry **raw data
only**. Every derived number is recomputed by `analyze`. Each
`evolve/<run_id>/<strategy>/<arm>/chain<n>` branch is a self-contained record:

- **1 manifest commit** (`manifest: …`) adding the run-level `provenance.json` +
  `config/` up front (see below).
- **2N checkpoint commits** (`cpNN agent <id>` + `cpNN reset <id>`), the pure
  agent delta, and the harness normalisation **plus that checkpoint's raw capture**,
  for each of the N checkpoints:
  - `capture/cpNN.json`: the per-checkpoint record (spec + rendered prompt, agent
    envelope incl. all attempts, the raw `{test_id: passed}` map + per-test detail,
    build flags, this checkpoint's `commit_sha`, `""` for a no-op turn).
  - `capture/cpNN.agent.jsonl`: the full agent event stream (behaviour trace).
  - `capture/cpNN.agent.diff`: the pre-normalisation agent delta.
  - `capture/cpNN.build.log`: the full build + test console.
  - `capture/cpNN.probe.jsonl`: the cold-reader probe transcript (at probe checkpoints).
- **1 final `results:` commit**, a completion marker (`--allow-empty` + capture
  backstop). The run-level artifacts, written in the **manifest** commit:
  - `provenance.json`: model, harness SHA, tool versions, secret-free agent
    environment. **Static**. No checkpoint→SHA map (derived from `capture/`).
  - `config/`: a snapshot of `config.yaml` / `checkpoints.yaml` / `astgrep-rules`
    so the run is self-contained.

No derived table (no `records.csv`/`summary.md`/`metrics/`) is stored on the
branch. `analyze` rebuilds all of it. Nothing is written to **this** (harness)
repo: the base branches stay pristine; local `results/`, `work/`, `.venv/` are
gitignored.

Review a chain end to end:

```bash
git -C ${HOME}/compare/spring log --oneline evolve/<run_id>/just-solve/spring/chain0
git -C ${HOME}/compare/spring show   evolve/<run_id>/just-solve/spring/chain0:evolve-results/capture/cp30.json
git -C ${HOME}/compare/spring diff <sha_cp05> <sha_cp15>     # any two checkpoints
```

## Reading the result

`analyze` **always recomputes** from the commits + `capture/` (no derived data is
read back). It selects the run (`--run-id`, else latest), enumerates checkpoints
from the capture records' `commit_sha` (so no-op checkpoints, recorded as `""`, are
included), materializes each checkpoint tree in a throwaway worktree, re-runs
`metrics.compute_all`,
re-scores correctness from the captured raw test map, and writes **local,
gitignored** output to `results/<run_id>/analysis/`.

It reports the degradation slope `m` with a 95% bootstrap CI over chains, per
arm/strategy, for the three erosion scopes, `verbosity`, `cost_usd`,
`cache_read_tokens`, `duration_api_ms`, `hotspot_cc`, `fn_nloc_max`,
`existing_fns_modified`, `files_created`, `wmc_max`, `wmc_handler`, `node_cc_median`,
`node_cc_max`, `node_path_cc`, `entry_cc`,
`packages_touched`, `reedit_rate`, and the impact family (`impact_mutation` /
`impact_godclass` / `impact_composite`, each in all / additive-only / mutative-only
slices); phase-binned means; EvoScore (γ ∈ {1, 1.5, 2}); Zero-Regression Rate (over
`regressions` and `true_regressions`); and the pinned-doc (`CLAUDE.md`) touch rate.
Every metric is defined in the **Metrics glossary** below.

**Adding a metric applies it to every past run.** Structural metrics need only
the commits; correctness/agent columns come from `capture/`. Add it to
`metrics.compute_all` and re-run `analyze`; no agent re-invocation.

If the metric needs **new config**, note how the two configs combine. `analyze`
derives with the run's own committed snapshot (so metrics match how that run was
configured), and a key the snapshot never had is filled from the live `config.yaml`
and logged as `! arms.<arm>.<key> absent from the run's config snapshot`. Without
that fill a new metric degrades silently to its fallback: `node_roots` was added
after both published runs, and on the first backfill OfficeFloor's node closure
collapsed to its single entry node — CC 8 rather than a 19-node pipeline, a number
with nothing obviously wrong with it. Recorded snapshot values always win; only
absent keys are filled.

**Confirms the thesis** if the *concentration* slopes climb for Spring and stay
flat for OfficeFloor with disjoint CIs — `node_cc_median`, `entry_cc`, `wmc_handler`, handler-scoped
erosion, and above all the **structural-impact** score (`impact_composite` /
`impact_mutation`) — while blast radius (`existing_fns_modified`) and coupling
(`reedit_rate`) stay lower for OfficeFloor, and OfficeFloor shows higher EvoScore at
γ>1 and fewer true regressions. The strong form: OfficeFloor lowers the **slope**
structurally, which SlopCodeBench found prompting could not do (it only lowered the
intercept, at higher cost). (Whole-app `erosion` is *not* part of this test — see the
glossary.)

**Refutes it** if the impact/concentration slopes also climb for OfficeFloor (a
wiring "god pipeline" or an accreting shared function) or Spring stays flat because
the agent refactors each time. Report either honestly.

## Metrics glossary

Every column `analyze` recomputes per checkpoint, grouped as in
`run_experiment.CSV_FIELDS`. Structural metrics are over **production Java only**
(YAML wiring is counted separately, never mixed into a Java denominator), with
identical tools/thresholds for both arms.

**Identity / bookkeeping** — `run_id`, `branch`; `arm`, `strategy`, `chain`,
`checkpoint`; `checkpoint_id` (the rule's id); `checkpoint_type` (`additive` or
`mutative` — a mutative rule revises prior rules); `phase` (checkpoint binned into
Start/Early/Mid/Late/Final).

**Process (agent cost/effort)** — `agent_ok`; `cost_usd`; `input_tokens`,
`output_tokens`, `cache_read_tokens` (the last a comprehension-cost proxy — how much
context it re-read); `num_turns`; `duration_ms`, `duration_api_ms` (wall-clock;
model-inference time).

**Correctness (black-box acceptance suite; SlopCodeBench + SWE-CI)**

| field | definition |
|---|---|
| `build_ok` | the project compiled |
| `total_selected` | tests selected for this checkpoint |
| `strict_pass` | **all** selected tests green |
| `iso_pass` | all *non-regression* tests (this checkpoint's Core+Error+Func) green |
| `core_pass` | all **Core** (happy-path) tests green |
| `core_p/t`, `error_p/t`, `func_p/t`, `regr_p/t` | pass/total for Core, Error-handling, hidden Functionality, and Regression suites |
| `regressions` | tests green *before* this checkpoint, red *after* (`prior − now`) |
| `true_regressions` | regressions on prior checkpoints a **mutative** step did not intend to change — the safety signal (broke a rule it wasn't asked to touch); for additive checkpoints all regressions are "true" |
| `normalized_change` | SWE-CI asymmetric Normalized Change in [−1,1]: improvement `(passed−base)/(target−base)`, regression `(passed−base)/base` |

**Erosion (SlopCodeBench Eq. 3)** — `mass(f)=CC·√SLOC`; a function is "eroded" when
`CC>10`; `erosion = Σ_{CC>10} mass / Σ_all mass` (fraction of complexity-mass in
over-threshold functions), reported over three scopes:

| field | scope |
|---|---|
| `erosion` (+ `_high_mass`, `_total_mass`, `_hot_fns`) | **whole app** (SlopCodeBench-comparable). *Not decisive here — location-blind, leaf-algorithm-dominated.* |
| `erosion_scoped` (+ intermediates, `subsystem_nfns`) | **touched-file subsystem** (files changed since base) |
| `erosion_handler` (+ intermediates, `_class`, `_nfns`) | the **entry-handler's own class only** — the clean concentration signal (Spring's controller erodes; OfficeFloor's `BuildOwner` stays flat) |

**Verbosity (SlopCodeBench Eq. 4)** — `verbosity = |clone-lines ∪ ast-grep-flagged
lines| / LOC` (jscpd duplication ∪ ast-grep anti-patterns); `verbosity_clone_lines`,
`verbosity_pattern_lines`, `verbosity_union_lines` are the components. `java_loc`,
`yaml_loc` are the two LOC pools (kept separate).

**Hotspot & function-size (lizard)** — `hotspot_cc` / `hotspot_nloc` / `hotspot_fn`:
the single highest-CC function in the touched subsystem (CC, size, `File::method`).
`fn_count`, `fn_nloc_avg`, `fn_nloc_max`, `fn_cc_max`: OfficeFloor's wired-function
package distribution (healthy growth = count rises while avg/max stay flat).

**Blast radius (how much pre-existing code a rule disturbs vs. adds)**

| field | definition |
|---|---|
| `diff_added`, `diff_removed`, `files_touched` | raw diff shortstat |
| `existing_fns_modified` | functions in **already-present** files the diff touched — the blast radius proper |
| `files_modified`, `files_created` | already-present files touched; new production files added for the rule |
| `churn_added`, `churn_removed` | production-line churn |

**Concentration / coupling**

| field | definition |
|---|---|
| `wmc_max` (+ `_class`, `_methods`, `_nloc`) | god-**class** indicator: highest Weighted-Methods-per-Class (Σ method CC) in the touched subsystem. Role-blind: the arms can answer with different kinds of class (an entity of accessors vs a controller of decisions), so prefer `wmc_handler` for between-arm claims |
| `wmc_handler` (+ `_class`, `_methods`, `_nloc`) | the same WMC pinned to the class the create endpoint routes through, in **both** arms (same class scoping as `erosion_handler`). The like-for-like god-class number; blank until that class exists. Entry-scoped, so read it with `node_path_cc` |
| `node_count`, `node_cc_median` / `_mean` / `_p90` / `_max`, `node_methods_median` | per-node comprehension load: CC transitively reachable from ONE handling node — what you must understand to change one rule. Nodes come from the arm's declared wiring (`node_roots.wiring_file`), or the single `entry_handler` when an arm declares none. Relocation-proof: work pushed to a later node lands in that node's closure |
| `node_exclusive_share` | cohesion: fraction of node-reachable CC reachable from exactly ONE node. Low = thin wrappers over a shared blob. Blank when an arm has a single node (trivially 1.0) |
| `node_path_cc`, `node_path_methods` | the union across nodes: the whole handling path, transitively. The honest total that answers "you just moved it downstream" |
| `entry_cc` (+ `_nloc`, `_fn`) | cyclomatic complexity of the **one** function the create endpoint routes through (`addOwner` / `BuildOwner::service`) — does the front door bloat |
| `packages_touched` | distinct packages the rule's production-Java diff reaches (change spread) |
| `reedit_rate` (+ `reedit_body_lines`, `reedit_prior_lines`) | temporal coupling: of the lines in functions this checkpoint edited, the share authored by **earlier** checkpoints |

**Structural-impact score** — per changed function,
`cost = max(WMC_other, 1) · CC · max(1, Δlines)`, where `WMC_other` = Σ CC of the
*other* methods in that function's class (the context you must hold to change it
safely); the whole commit is then multiplied by `files_changed` (a spread penalty).
So mutating a method inside a heavy god-class costs far more than the same edit to an
isolated unit; a brand-new class is floored to `1·CC·nloc·files` (small but non-zero,
closing the fragmentation loophole). A within-commit **rename** (body Jaccard ≥ 0.6)
is scored as a mutation, not a free addition.

> **What it cannot see.** Only lines inside a parsed **function body**, in a file
> `lizard` reads as source, are charged. Logic expressed declaratively — a MapStruct
> `@Mapping(expression = "java(...)")` on an interface method, `openapi.yml`,
> `schema.sql`, OfficeFloor's wiring `.yml` — scores **0**. Both arms have that escape
> hatch, so it is not an arm bias, but read a 0 as "the logic went where this metric
> cannot look", not as "the change was cheap". And because an unreadable file also
> yields no functions, a **parser** that fails to parse a file makes it look perfect:
> `python -m harness.parser_selftest --config config.yaml` must print `OVERALL: PASS`
> before a run or an analysis is trustworthy (see AGENTS.md, 2026-09 gotcha).

| field | definition |
|---|---|
| `impact_mutation` | Σ over **modified/renamed existing** functions, × `files_changed` |
| `impact_godclass` | Σ over **new** functions (new files + methods fed into existing classes), × `files_changed` |
| `impact_composite` | `impact_mutation + impact_godclass` |
| `impact_files_changed` | distinct production-Java files the commit touched |
| `impact_new_files`, `impact_new_fns`, `impact_mut_fns`, `impact_renames` | raw counts |

Each of `impact_mutation/godclass/composite` is analyzed in three **slices** — all
checkpoints, additive-only (`_add`), mutative-only (`_mut`) — as filtered views (a
mutative checkpoint is a mandated rule revision, so the context weight makes it
genuine architectural signal: the arm that isolated the concern pays less).

**Placement metrics (`harness/placement.py`)** — *where* the complexity sits, as
distinct from how much there is. Added because the `impact_*` score above was
identified on this experiment and so cannot be the evidence for a claim about it;
everything in this group is a published or textbook measure that predates the work.

*Amount — expected to show NO arm difference (Tesler's conservation):*

| field | meaning |
|---|---|
| `total_cc` | total cyclomatic complexity, whole app (McCabe 1976) |
| `pmd_cognitive_total` / `_max` / `_mean` | cognitive complexity (Campbell/SonarSource 2018) — penalises nesting, forgives flat sequences, so it separates a nested method from a long flat dispatch |
| `pmd_npath_total` / `_max` | acyclic execution paths (Nejmeh 1988) |
| `halstead_volume`, `halstead_effort`, `halstead_vocab` | Halstead (1977) — vocabulary size, an operationalisation independent of control flow |
| `mi_mean`, `mi_min` | Maintainability Index (Coleman et al. 1994), computed **per file** then averaged; `mi_min` is the worst file |
| `ck_wmc_total` | total WMC from CK — an independent parser's cross-check on the lizard numbers |
| `total_fns`, `total_files`, `total_packages` | unit counts |

*Concentration — the thesis. Reported over functions, files, packages and classes:*

| field | meaning |
|---|---|
| `ccdist_{fn,file,pkg}_{gini,hhi,top1,top5,hnorm,n}` | how total CC distributes. `gini` is **scale-free** (shape only); `hhi`/`top1`/`top5` are **not** (an arm with more files scores lower for free). Publish both: if Gini matches and HHI does not, the honest statement is "the units are larger", not "the distribution is more unequal" |
| `ccdist_file_lorenz` | 11 cumulative-share points, so the exact Lorenz curve can be drawn (`analysis/lorenz.png`) |
| `wmcdist_class_*`, `cogdist_fn_*`, `voldist_file_*` | the same panel over WMC, cognitive complexity and Halstead volume |
| `change_entropy`, `change_entropy_norm`, `change_top1/top5`, `change_hhi`, `change_files` | Hassan (2009) change entropy for **this** checkpoint: how the rule's diff spreads over files |
| `cum_change_*` | the same, cumulatively from `base_ref` — an architecture where every rule lands in one file keeps low cumulative entropy no matter how each rule looks alone |

*Cohesion & coupling (CK tool, Aniche 2015 — source-only via Eclipse JDT):*

| field | meaning |
|---|---|
| `ck_lcom_{mean,max}`, `ck_lcom_star_mean` | lack of cohesion (C&K 1994; Henderson-Sellers 1996) — **low is cohesive** |
| `ck_tcc_mean`, `ck_lcc_mean` | tight/loose class cohesion (Bieman & Kang 1995) — **high is cohesive**, the opposite sign to LCOM, which is why both are reported |
| `ck_cbo_*`, `ck_rfc_*`, `ck_fanin/fanout_*`, `ck_dit_mean` | coupling, response set, fan-in/out, inheritance depth |
| `ck_handler_*` | the same metrics pinned to the **handler class**, the like-for-like role in both arms |

*Published detector verdicts — binary, with thresholds nobody here chose:*

| field | meaning |
|---|---|
| `pmd_god_classes` | classes tripping PMD's `GodClass`, i.e. Lanza & Marinescu (2006): WMC ≥ 47 ∧ ATFD > 5 ∧ TCC < 1/3 |
| `pmd_handler_is_god_class` | whether the endpoint's own handler class trips it |
| `pmd_data_classes`, `pmd_demeter_violations` | `DataClass`; Law of Demeter (Lieberherr 1989) |

*The distribution tax — expected to favour the CONCENTRATED arm (Brooks):*

| field | meaning |
|---|---|
| `indirection_median/_max/_deep_share/_reached` | call hops from a handling node. **Understates a pipeline arm**: its wired steps are all depth 0 and its hops are YAML, not Java calls — read it as this plus `node_count` |
| `propagation_cost` | MacCormack et al. (2006): density of the transitive closure of the file dependency matrix. The `n²` denominator rewards more files and the conservative call resolver drops edges, so use the **between-arm** comparison only |
| `propagation_fanout_median/_max` | raw reachable-file counts, **not** normalised — these show whether the dependency structure differs or only the packaging |

*Validity:* `container_{advice,aspect,filter,entity_listener,validator,body_advice,total}`
counts classes the **framework** dispatches, which no call-graph statistic can see. If
this moves off its baseline, every `node_*` number for that chain is measuring a
shrinking fraction of the code.

**Statistical reporting.** With 80+ metrics a 95% CI alone manufactures several false
positives per run, so `summary.md` reports **Benjamini-Hochberg FDR** beside the raw
`excludes 0`, **Cliff's delta** as an effect size, both a **slope** and an end-state
**level** test, a **Counter-signals** section listing every measure that contradicts
its pre-declared expectation, and an **Outcome-prediction matrix** regressing each
structural metric against independently measured outcomes. Quote the FDR column.

**Probe & integrity (nullable)** — `probe_*`: the read-only cold-reader probe (cost,
and `probe_recall` = how well a fresh agent recalls the accumulated rules);
`pinned_touched` (pinned guide files the agent edited — should be empty);
`acceptance_touched` (test files the agent edited — tamper signal, restored after
detection); `notes`.

**Derived scores in `summary.md`** — degradation **slope** `m` (OLS on checkpoint,
95% bootstrap CI over chains); phase-binned means; **EvoScore** (SWE-CI, γ-weighted
mean of `strict_pass`, γ ∈ {1, 1.5, 2}, higher γ rewarding staying green late);
**Zero-Regression Rate** (over `regressions` and `true_regressions`); the
intended-vs-true regression split; pinned-doc and acceptance-tamper rates.

## Isolation & fairness

- **No carried context.** Each checkpoint is a fresh `claude -p`; the harness
  never uses `--continue`/`--resume`, so prior session transcripts are never
  read back. The only thing crossing between checkpoints is the code state.
- **`CLAUDE.md` is pinned** (`isolation.pin_files`). It is loaded as context
  every checkpoint (that is its job) but restored to the base version after each
  agent turn, so it cannot become accumulating cross-checkpoint memory. The
  `pinned_touched` column and the touch-rate table record when the agent tried
  to edit it.
- **Per-call config/memory isolation.** Each `claude -p` runs under a throwaway
  `CLAUDE_CONFIG_DIR` seeded with only the login credentials, so Claude Code
  auto-memory can't write project "learnings" that leak across checkpoints or,
  asymmetrically, between arms. The real `~/.claude` is never read or written.
- **Filesystem confinement (Landlock).** A clean sandbox isn't enough. The agent
  process can still `find /` the rest of the disk (the harness `acceptance/` suite,
  `checkpoints.yaml`, and prior runs sitting in Trash all leak the withheld
  sequence). So `agent.run_agent` restricts the agent, and every child it spawns,
  to the sandbox + toolchain via Landlock (`isolation.agent_confinement`, no root),
  denying everything else. It **fails closed**: if a withheld sentinel is still
  readable, or Landlock is unavailable, the checkpoint is refused rather than run
  un-blinded. Verify with `python harness/landlock_selftest.py`.
- **Structural metrics are Java-only** and use identical tools/thresholds for
  both arms, so OfficeFloor's file-spreading cannot distort LOC; YAML LOC is
  logged separately (`yaml_loc`).
- **Resilience.** A token/session limit **or an OAuth expiry** pauses and retries
  the same checkpoint (a manual `/login` mid-run resumes); a transient
  network/overload failure backs off short then retries. Watch for the auth-dead
  signature (`$0` / 1 turn / empty commit) as a sign a chain needs re-running. See
  AGENTS.md → "Gotchas".

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

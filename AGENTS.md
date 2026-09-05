# AGENTS.md: PetClinic-Evolve harness developer guide

Canonical orientation for anyone (human or AI) **developing or extending the
harness itself**. `CLAUDE.md` points here; `README.md` covers the experiment
rationale and how to run it. Where any doc disagrees with this file, **this file
wins** (the README predates several 2026-08 design changes noted below).

> **MAINTENANCE DIRECTIVE. Read before you change code.**
> This file and `README.md` are the entry points others rely on to extend the
> harness with AI. **Whenever you change harness behaviour, update both in the
> same change:**
> - a change to `harness/*.py` behaviour, the run lifecycle, capture/derive
>   split, isolation, or resilience → update the matching section here **and** the
>   README;
> - a change to the checkpoint plan, acceptance-suite conventions, `mutates`
>   discipline, or the reference tables → update "The acceptance suite" here and
>   the README's suite section;
> - a new config knob → update "Config knobs" here and `config.yaml`'s comments.
> Keep the "Module map" table and the "Gotchas / lessons" list current. They are
> the fastest way for a newcomer to get oriented. If you add a doc, link it here.

> This is the guide for the *harness* repo. It is unrelated to the `CLAUDE.md`
> that the experiment **pins into each arm's base repo** (`isolation.pin_files`);
> that one is a fixed project guide handed to the checkpoint agent, not this file.

## What the experiment is

Hold the coding agent **fixed** (`claude-opus-4-8`) and make **architecture** the
independent variable (Spring `@RestController` methods vs OfficeFloor
YAML-composed functions), then measure how each codebase degrades as ~60
accumulating change "checkpoints" land on the **one** endpoint `POST /api/owners`.
Thesis: Spring's single handler erodes (complexity concentrates into a
god-method; comprehension cost climbs) while OfficeFloor stays flat (each rule is
a new small wired function). Methods borrow from SlopCodeBench (arXiv:2603.24755)
for Erosion, Verbosity, degradation slope and prompt arms, and SWE-CI
(arXiv:2603.03823) for Normalized Change, EvoScore and Zero-Regression Rate.

**Decisive statistics (updated after run `blind-202608100006`).** The hypothesis
is about *where* complexity lands (concentration vs. distribution), so the decisive
statistics are the ones that measure placement and blast radius:

- **Blast radius** — `existing_fns_modified`, zero-blast checkpoints, `files_created`.
- **Comprehension load** — `node_cc_median` / `node_cc_max` / `node_exclusive_share`:
  complexity transitively reachable from ONE handling node, i.e. what must be understood
  to change one rule. **This is the concentration statistic to lead with**, because it is
  the only one immune to relocation (below).
- **Concentration** — `entry_cc` and `wmc_handler` (god-method / god-class), corroborated
  by `erosion_handler` (erosion scoped to the entry handler's own class). **All three are
  scoped to the ENTRY node and therefore understate a pipeline arm.** OfficeFloor's entry
  node is CC ~1.3 while its worst pipeline node reaches CC ~13, and once helper calls are
  followed its whole create path carries the *same* total complexity as Spring's
  controller (`node_path_cc` 229 vs 202 on a blind chain0) with a worst single method as
  bad or worse (17.6 vs 16.6). Never publish `entry_cc`/`wmc_handler` without
  `node_path_cc` beside them; a reader who opens `owners.POST.yml` will otherwise make
  the objection for you.
  **Prefer `wmc_handler` over `wmc_max` for the between-arm claim.** `wmc_max` reports
  the heaviest class *whatever its role*, and the arms answer with different kinds of
  class: on `full-202608102319` OfficeFloor's heaviest is the Owner ENTITY in 9 of 10
  chains (≈60 accessors at CC 1, WMC ≈67) while Spring's is usually the CONTROLLER
  (≈32 methods averaging CC 3+, WMC ≈142) — and the entity in 4 of 10 chains, so the
  metric partly tracks entity growth in both arms. `wmc_handler` pins the measurement
  to the class the endpoint routes through in both arms (same `_handler_files` scoping
  as `erosion_handler`), which is the like-for-like number. `wmc_max` stays reported.
- **Structural impact** — `impact_composite` / `impact_mutation` / `impact_godclass`:
  per-checkpoint blast on existing code *weighted by the complexity of the context it
  touches* (`max(WMC_other,1)·CC·max(1,Δlines)·files_changed`; fields and formula defined
  in the README **Metrics glossary**). In `blind-202608100006` the Spring−OfficeFloor slope
  CIs are fully disjoint for `impact_composite` and `impact_mutation` (~12× and ~28×);
  `impact_godclass` alone overlaps, since with the floor+spread both arms pay for
  additions — the discrimination correctly lives in the context-weighted mutation term.

**Whole-app `erosion` is demoted from decisive.** It is location-blind (it can't tell
a CC-19 god-method from a CC-19 isolated single-responsibility algorithm) and is
dominated by architecture-neutral leaf algorithms (soundex, phone/E.164, dedup) that
both arms implement — so on `blind-202608100006` its slope ordering came out *backwards*
(OfficeFloor > Spring). It stays reported for SlopCodeBench comparability, but read it
as leaf-algorithm-dominated, not as a thesis test; use `erosion_handler` and the impact
metrics for the concentration signal.

### The structural-impact metric (`impact_stats` in `metrics.py`)

The **definition** of the impact score and every `impact_*` field lives in the README's
*Metrics glossary* — don't duplicate it here. This section records only the maintainer
rationale (the "why", so it doesn't silently regress):

- **Computed over ALL checkpoints — no additive-only discount.** Unlike the correctness
  metrics (intended-vs-true), impact keeps the mutative checkpoints. The context weight
  makes a mandated rule revision *genuine* architectural signal, not spurious re-touch:
  the arm that isolated the concern pays less (Spring ~36k per mutative checkpoint vs
  OfficeFloor ~4.8k). Discounting them (as the old count-based blast metric did) would
  drop the most on-point evidence *and* make impact the lone structural metric not over
  all checkpoints. `analyze` also emits additive-only (`_add`) and mutative-only (`_mut`)
  slice views. Including mutative compresses the additive-only ratio (17× → ~10× composite)
  because it is a harder test where OfficeFloor must also mutate — honest signal, not dilution.
- **The `× files_changed` spread term is a deliberate Goodhart trade.** It anti-correlates
  with the context weight across the arms (Spring concentrates → few files/high WMC_other;
  OfficeFloor distributes → more files/low WMC_other), so it *costs* a little arm-separation
  to buy fragmentation-robustness. Keep it only while that trade is wanted.
- **The floor of 1 on `WMC_other` and the rename guard are load-bearing.** The floor is what
  stops fragmenting a rule into cohesionless new classes from being free (a pure `WMC_other`
  weight leaves that loophole open); the rename guard (body Jaccard ≥ `IMPACT_RENAME_JACCARD`)
  stops edits hiding behind renames. Don't remove either without re-checking the
  fragmentation / rename gaming paths.
- **It is a FUNCTION-BODY measure, so declarative work is free — by construction.** Only lines
  inside a parsed function's line range are charged, and only files lizard treats as source.
  A rule implemented as a MapStruct `@Mapping(expression = "java(...)")` on an interface
  method, or in `openapi.yml` / `schema.sql` / OfficeFloor's wiring `.yml`, scores **0** even
  though real logic was added (observed on `blind-202608312216` at cp05/cp06/cp14, where the
  Spring agent put the whole rule in a mapper annotation). Both arms have such an escape
  hatch, so it is not an arm bias, but a run with many 0-impact checkpoints should be read as
  "the logic went somewhere the structural metrics cannot see", not as "the change was cheap".
  Changing this would redefine the measure and invalidate `baselines/officefloor.json` — do
  not do it mid-experiment.

## Module map (`harness/`)

| file | responsibility |
|---|---|
| `run_experiment.py` | the driver. `run_chain` walks checkpoints; two commits per checkpoint; the agent-view / measurement-suite / gate / capture flow. Entry point `main`. |
| `agent.py` | wraps headless `claude -p`. `run_agent` streams stream-json events, classifies terminal outcomes (limit / transient / **auth**), and **isolates config per call** (see Isolation). `probe()` is the read-only cold-reader. |
| `correctness.py` | parses Surefire XML → raw `{test_id: passed}` map; `score_results` / `outcome_row` derive Strict/ISO/Core, Normalized Change, `regressions`, `true_regressions` (mutative-aware). |
| `metrics.py` | structural metrics over git commits: `compute_all` is the ONE definition called by both runner and analyze. lizard CC/SLOC, erosion (whole-app + `erosion_scoped` + `handler_scoped_erosion`), hotspot, WMC, blast-radius, change-spread, re-edit coupling, `impact_stats` (structural-impact score); jscpd + ast-grep for verbosity. |
| `capture.py` | assembles the raw, irreproducible per-checkpoint record (`checkpoint_record`) and run `provenance`. Carries the `impact_gate` block for gated checkpoints. |
| `impact_gate.py` | the `impact_gated` strategy's gate. Shells the standalone `impact-gate score --curve` CLI (`score`, optionally `--baseline-file` + `--curve-prior-weight`), decides the fail line (`is_blocked` — grade ≥ block_percentile), builds the symptom-only refactor prompt from the flagged-class LOCATIONS + spec (`refactor_prompt`; `_format_drivers` strips cost figures — design B), and shapes the capture entry per attempt (`attempt_summary`, incl. `quality`/`quality_turns`). No effect on the other strategies. |
| `quality_gate.py` | design-B code-quality gate on each refactor's ADDED lines: jscpd clones + ast-grep smells over `git diff --cached`, findings rendered as review text (`review`, `summary`). Deterministic; syntactic clones only. Reused by `_impact_gated_implement`'s quality sub-loop. |
| `quality_selftest.py` | fail-closed check that the PINNED `jscpd`/`@ast-grep/cli` (tools/package.json) are at the locked versions AND a golden clone+smell fixture fails the gate. `require()` runs beside `parser_selftest.require` in `run_experiment.main` when the gate is active; standalone `python -m harness.quality_selftest --config config.yaml`. |
| `build_impact_baseline.py` | builds an ImpactGate baseline JSON from a completed run's OWN per-checkpoint `impact_composite` (reads `results/<run_id>/records.concat.csv`, else recomputes). Used to calibrate the gate to OfficeFloor's observed cohesion so Spring is graded against it. Standalone `python -m harness.build_impact_baseline`. |
| `cumulative_impact.py` | audit answering "what did the WHOLE run add, everywhere": one diff from `base_ref` to the chain TIP, every changed file (not just `source_globs`), changed lines mapped to their function at the tip, CC summed over the DISTINCT functions touched. Reports the two buckets a CC sum cannot contain — `orphan` (inside a parsed file, outside every function body) split into boilerplate vs content vs **branch tokens**, and `opaque` (no lizard parser at all: `.yml`, `.xml`, `.json`) with OfficeFloor's wiring edges counted by a real YAML parse. Cross-check for the scoped per-checkpoint metrics, not a replacement. Run automatically at the end of `analyze`; also standalone via `python -m harness.cumulative_impact --config config.yaml` (adds `--top N`, the heaviest-touched-function listing that the summary section omits). |
| `class_shape.py` | class-shape audit: for the classes a run CREATED (tip minus `base_ref`, generated `rest/dto`+`rest/api` excluded), what KIND each is — `spring-bean` / `static-util` / `instance-class` / `exception` / `entity` / `annotation`. Categorises from lizard's function list, NEVER a regex (a `static final` field initialiser reads like a static method to a grep). Exists because the impact formula is cheapest to satisfy with `static` methods in tiny classes, so a run can lower its score by trading container-managed beans for procedural utilities with no improvement to the code — nothing else in the harness would show that. Reports per-chain RANGE as well as mean: one prompt yielding ten different mechanism choices is itself a finding. Runs at the end of `analyze`; standalone `python -m harness.class_shape --config config.yaml`. |
| `analyze.py` | **always recomputes** from commits + capture (no derived data is read back). Materializes each checkpoint tree, re-runs `compute_all`, re-scores correctness, fits slopes with bootstrap CIs, writes `results/<run_id>/analysis/`. Ends by running `cumulative_impact.run_audit` and `class_shape.run_audit` (best-effort: a failure prints and marks the section NOT AVAILABLE rather than losing the analysis) and appending their sections to `summary.md` + `cumulative_impact.json` / `class_shape.json`. |
| `parser_selftest.py` | fail-closed Java-parser check for BOTH measurement stacks (this venv's lizard, and the `impact-gate` CLI's own venv). Adds a method to an `@Entity`/`@Table` fixture class and asserts the parser sees it and the gate scores it > 0. `require()` is called by `run_experiment.main` (and the lizard half by `analyze.main`) before any work; standalone `python -m harness.parser_selftest --config config.yaml`. |
| `__init__.py` | shared helpers: `git_out` (graceful, for derive/analyze), `expand_path`. |

`acceptance/` holds the black-box test suite (see below). `checkpoints.yaml` is
the ordered rule stream; `config.yaml` wires arms/paths/limits.

## The checkpoint lifecycle (current design)

Per chain, `make_worktree` cuts a fresh branch **`evolve/<run_id>/<strategy>/<arm>/chain<n>`**
from the untouched `base_ref` (note the order: run_id first, so the README's older
`<strategy>/<arm>/chain/<run_id>` is wrong). The branch **opens with a `manifest:`
commit** (`commit_run_manifest`): the run's static `provenance.json` (run/model
identity, harness SHA, `tool_versions`, `agent_env`, `base_commit`, but **no**
`checkpoint_shas`) and the `config/` snapshot (`config.yaml`, `checkpoints.yaml`,
`astgrep-rules/`). Written **up front, not at chain end**, so a partial run is
self-describing and the control (tool/agent env) is captured before it can drift over
a multi-hour chain. Then for each checkpoint k, **two commits**:

1. **Agent view is set to ONLY this checkpoint's own test** (`set_agent_view`):
   the acceptance dir holds shared infra + `CpKTests.java` and *nothing else*.
   **The agent never sees prior tests**. This is the blind-agent design (below).
2. **Agent turn**. Fresh `claude -p`, spec only, no `--continue`. Retry loop
   (`_run_agent_turn`) handles limit / transient / auth (below).
3. **COMMIT 1 `cpNN agent <id>`**. Parented on the pre-agent state, so its diff
   is *exactly* the agent delta. Tamper/pin edits recorded (`detect_agent_tamper`,
   `pinned_touched`) then left in place for the commit.
4. **Normalize + install measurement suite**. Restore pinned `CLAUDE.md`; then
   `install_measurement_suite` installs the FULL resolved cp01..cpK authored suite
   (the priors the agent never saw), overwriting any agent test-tamper, so a
   weakened visible test can't buy a false pass.
5. **Gate** (`correctness.run_tests`) against that full suite → regressions become
   REAL: a failure on a prior rule the agent couldn't see is the signal. A gate that
   **aborts** (Surefire fork crash) is retried up to `build.test_attempts`; if every
   try aborts the checkpoint is flagged `gate_invalid` and its correctness fields are
   left BLANK (missing data, never a score). A gate whose tests merely **fail** is
   never retried — that is the measurement. See *Invalid gates* below.
6. **Structural metrics** over the agent commit (log-only; analyze recomputes).
7. **Cold-reader probe** at `probe.at_checkpoints`.
8. **Raw capture** (`cpNN.json`, `.agent.jsonl`, `.agent.diff`, `.build.log`, `.probe.jsonl`)
   is copied into `evolve-results/capture/`. The gate outcome and probe are already in
   hand, so the `cpNN.json` record is complete.
9. **COMMIT 2 `cpNN reset <id>`**. Normalization + `set_agent_view(next cp)` **and commits
   this checkpoint's capture** (step 8), so cp(k+1) starts blind, its agent commit stays
   pure, and each reset commit is self-contained (`git show <cpNN reset>:evolve-results/capture/cpNN.json`
   is that checkpoint's result inline).

End of chain: a `results:` commit is a **completion marker** (`commit_chain_results`).
An `--allow-empty` commit carrying the summary headline, plus an `assemble_into` backstop
for any capture not already committed. Its presence on the branch means the chain finished
(vs. dying partway). Provenance + config live in the **manifest** commit (start) and each
checkpoint's raw capture in its **reset** commit, so this normally adds nothing. No derived
table on the branch. `analyze` recomputes every metric, and derives the checkpoint→agent-SHA
map from the per-checkpoint capture records' `commit_sha` (which encodes a no-op turn as `""`),
**not** from provenance.

## The four-condition intervention study (2026-09)

The experiment compares FOUR conditions, each a full (arm × chain) sweep, each changing exactly
ONE lever so the per-checkpoint impact trajectory vs the control isolates what reduces decay:

1. **`just-solve`** — CONTROL. Plain "implement it" prompt, ungated. Baseline decay. **Unchanged.**
2. **`cohesion-prompt`** — the **PROMPT** lever. Same single ungated turn as just-solve; only the
   wording adds a plain-language request for good structure (no metric, no experiment mention).
   Its delta vs just-solve is the effect of better prompting *alone*.
3. **`impact_gated`** (enforcement `advisory`) — the **TOOL** lever. Neutral implement prompt, but a
   flagged change gets ONE quality-gated refactor guided by ImpactGate's flagged LOCATIONS, then is
   re-attempted and **accepted regardless of grade** (record-and-continue → always reaches cp60).
   Delta vs just-solve = the effect of a tool-guided refactor; delta vs cohesion-prompt = what the
   tool adds beyond good prompting.
4. **`metric-in-prompt`** — the design-A prompt that hands the AI the cost FORMULA as its objective.
   **Retained for reproducibility only** — it was Goodhart-gamed (dispersal + duplication). Run it
   from the archived design-A code or `--strategy metric-in-prompt`; it is not this repo's default.

Conditions 3 and 4 differ deliberately: 4 tells the AI the metric (and it games it); 3 never does —
the AI only ever sees the spec and, on a refactor, the symptom locations. The prompts live in
`config.yaml: prompt_strategies`; the header there is the canonical statement of the four conditions.

## The impact-gated pipeline (`impact_gated` strategy)

Added 2026-08. Makes ImpactGate an **active gate** in the checkpoint loop instead of a
post-hoc metric. Activated only when the active strategy equals `impact_gate.strategy`
(`_gate_active` in `run_experiment.py`); all other strategies run the unchanged flow above,
so it is a strict superset and a clean control comparison.

**Enforcement mode (`impact_gate.enforcement`, 2026-09).** Decides what a flagged change does:
- **`advisory`** (default; condition 3 above) — record-and-continue. `max_refactors: 1`. A flagged
  change gets one quality-gated refactor and is re-attempted; the re-attempt is **accepted whatever
  its grade** and the chain never stops. Both the FIRST-attempt (direct) and second-attempt
  (post-refactor) impacts are captured, so analyze exposes `ig_impact_first` vs `ig_impact` — the
  measured one-refactor cohesion effect, comparable to the ungated arms. No `stop_reason` ever fires.
- **`block`** — the design-B HARD gate (below). A flagged change is discarded and refactored up to
  `max_refactors` times; still over → `stop_reason=impact`; a refactor that will not come clean →
  `stop_reason=quality`. The stress-test condition; retained, not default. `enforcement` is recorded
  in the `impact_gate` capture block and defaults to `block` when absent (old runs reproduce).

**Design B (2026-09, current).** An earlier design also handed the AI the exact structural-
impact cost function as its objective (in both the implement and refactor prompts). A Spring
run gamed it exactly as Goodhart predicts: it dispersed logic into greenfield classes
(`WMC_other` collapses to 1) and DUPLICATED code (reuse means editing a penalised large class),
holding the score down while the code stopped being idiomatic Spring. The cost function is blind
to duplication, so "minimise it" and "write clean code" came apart. Design B removes the formula
from every prompt the agent sees and, instead, holds each refactor's OWN output to a
deterministic code-quality gate:
- the **implement** turn uses a NEUTRAL prompt (`impact_gate.implement_strategy`, default
  `just-solve` — spec only, no formula), so the AI optimises the real task, not the proxy;
- the **refactor** prompt is symptom-only (`refactor_prompt`: names the concentrated classes via
  `{drivers}` locations, never the cost figures — `_format_drivers` strips CC/WMC/cost);
- each refactor must pass `quality_gate` (jscpd clones + ast-grep smells over the refactor's
  ADDED lines) — this is what forbids the run-1 slop exploit.
ImpactGate still gates the CHANGE (discard → refactor → re-attempt) exactly as before; the AI is
simply never told the metric it is graded on.

**Where it hooks.** In `run_chain`, the single agent turn (lifecycle steps 2–3) is replaced
by `_impact_gated_implement(...)` when the gate is active. Everything downstream (tamper →
COMMIT 1 → measurement suite → correctness gate → COMMIT 2 → capture) is unchanged and runs
on the *accepted* implementation. The helper returns `(ar, attempt_log, ig_block,
base_for_cp, stopped)` with the worktree already mirrored + `git add -A` staged.

**The loop** (`base_for_cp` starts at the previous reset commit):
1. Implement via the existing `_run_agent_turn` (fresh, blind sandbox rebuilt from the wt).
   The prompt is the NEUTRAL `implement_strategy` (design B), selected in `run_chain`.
2. `mirror_source(sandbox→wt)`, `git add -A`, then `impact_gate.score(cmd, wt, ...)` — the CLI
   runs `score --mode staged --curve` on the wt (a real git repo; the sandbox has no `.git`).
3. `is_blocked` keys on `grade.percentile >= block_percentile` directly (NOT the CLI's
   `blocked` flag, which additionally needs `--enforcement block`), so it means exactly
   "grade ≥ block_percentile" and is enforcement-independent.
4. **Pass** → return the accepted turn; downstream proceeds normally.
5. **Fail** → `git reset --hard base_for_cp` + `git clean -fd` (discard the change; ignored
   `target/` survives, tracked `evolve-results/` capture is untouched, the `-capture` sibling
   is outside the wt), then a **refactor turn** via `agent.run_agent` on the clean base with
   the same Landlock `confine` as the implement turn, prompted from the symptom-only
   `refactor_prompt` (concentrated-class LOCATIONS + the change spec; no cost figures).
   Mirror back, `git add -A`. Then the **quality sub-loop** (design B): `quality_gate.review`
   scores the refactor's added lines; while dirty, up to `max_review_turns` code-review turns
   run in the SAME sandbox, each fed the findings as review text, re-mirroring after each. Once
   clean (or the budget is hit), `impact_gate.score` again (recorded, not enforced), optionally
   `_refactor_correctness` (record-only), commit **`cpNN refactorM <id>`**, set
   `base_for_cp = HEAD`.
6. Stop conditions — **only under `enforcement: block`**. Both set `stopped=True` with an
   `ig_block.stop_reason`; `run_chain` records the failing checkpoint then `break`s (and
   `stop_scope: run` raises `ChainStopped`, exit 3):
   - **`impact`** — up to `max_refactors` refactor+re-attempt cycles; still blocked after the
     last → the change stayed too concentrated even after clean refactors.
   - **`quality`** — a refactor could not be made statically clean within `max_review_turns`
     (it could only lower impact with duplication/slop we refuse). The dirty refactor is
     committed for inspection before the stop.
   Under **`enforcement: advisory`** (default) NEITHER fires: the out-of-budget-and-still-blocked
   branch returns `stopped=False` and the dirty-refactor branch is skipped, so the re-attempt is
   accepted and the chain continues. `stopped` is always False; both attempts stay recorded.

**Commit shape & analyze.** A gated checkpoint is `0..N × cpNN refactorM` + `cpNN agent` +
`cpNN reset`. `base_for_cp` advances past each refactor, so COMMIT 1's parent and the log-only
structural-metrics base are the refactored code (the checkpoint's `impact_composite` is thus
the final implement delta; the refactor deltas + `pre_checkpoint_sha` live in the capture
block). `analyze` still enumerates from the capture's `commit_sha` (the agent commit); the
refactor commits are its ancestors, so the materialized checkpoint tree includes them and the
absolute snapshots — decisively **`node_cc_median`** (comprehension load) and
`node_exclusive_share` (cohesion), plus `wmc_handler`/`entry_cc`/`erosion_*` — reflect
refactor+implement with **no grouping rework**. The headline gate result is the `node_cc_median`
slope, `impact_gated` vs `just-solve` per arm (it is relocation-proof, so a refactor that merely
shifts complexity to a later node cannot fake a win); `entry_cc`/`wmc_handler` flatter pipelines
and are corroborating, not decisive (see "What the experiment is").

**Capture.** `checkpoint_record(..., impact_gate=ig_block)` adds an `impact_gate` block:
`{enabled, enforcement, block_percentile, warn_percentile, max_refactors, max_review_turns,
refactors, passed, stopped, stop_reason, pre_checkpoint_sha, attempts:[...]}`. Each attempt is
`{kind: implement|refactor, grade, impact, blocked, files, drivers, sha}`; a refactor attempt
also carries its `agent` envelope (irreproducible cost/tokens — MUST be captured), if enabled
`tests` (record-only), and design B `quality` (`quality_gate.summary`: passed/ran, added-line +
clone/smell finding counts, the findings) plus `quality_turns` (the review turns' envelopes).
The refactor + review event streams land as `cpNN.refactorM.jsonl` and
`cpNN.refactorM.reviewR.jsonl` (staged by the existing `startswith("cpNN.")` copy into
`evolve-results/capture/`). The **manifest** commit's `provenance.json` additionally carries an
`impact_gate` control block (`capture.impact_gate_provenance`): the impact-gate version + git
SHA, the effective policy (incl. `implement_strategy`, `max_review_turns`, and the `quality_gate`
policy + PINNED jscpd/ast-grep versions), and the reference baseline's `sha256` + `n` — so every
gated run is reproducible and each verdict is traceable to a tool version and a distribution.
Only present for the gated strategy.

**analyze columns.** `recompute_rows` reads the block into `ig_enforcement`, `ig_refactors`,
`ig_passed`, `ig_stopped`, `ig_stop_reason`, `ig_grade`/`ig_impact` (last, i.e. ACCEPTED implement
attempt), `ig_grade_first`/`ig_impact_first` (first, i.e. DIRECT attempt before any refactor —
their gap is the one-refactor cohesion effect the advisory condition measures),
`ig_refactor_cost_usd`, `ig_refactor_tokens`, and the design-B quality columns
`ig_quality_review_turns`, `ig_quality_passed`, `ig_quality_clone_lines`, `ig_quality_smell_lines`,
`ig_quality_cost_usd` (all in `CSV_FIELDS`, blank for ungated/old runs). `main` renders an
**ImpactGate pipeline** summary table (enforcement mode, reached-final rate, stops split as
**impact/quality** — always 0/0 under advisory, refactor rate, mean refactors/cp, the median
`direct→accepted impact` over refactored checkpoints, review turns, refactor $, mean accepted
grade), shown only when a group has gate data.

**Calibration — grade against OfficeFloor, not the seed (the experiment).** The prior run
([blog](https://blog.officefloor.net/2026/08/the-same-complexity-one-unit-or-twenty.html))
showed OfficeFloor stays cohesive while Spring erodes. So the gate grades against OfficeFloor's
OWN `impact_composite` distribution, built by `build_impact_baseline` from a completed ungated
OF run into an ImpactGate baseline JSON. `impact_gate.baseline_file` points at it and
`curve_prior_weight: 0` makes the grade the PURE OfficeFloor percentile (seed ignored; verified:
`grade.weight==1.0`, `percentile==project_percentile`). Then `block_percentile` is read against
OfficeFloor: 90 = "more impactful than 90% of OfficeFloor's changes". From `blind-202608100006`,
OF is p90≈3,410 / p95≈5,922 / p98≈14,148 and Spring's *median* (≈4,736) already tops OF p90, so
p90→~61% of Spring changes fire, p95→~45%, p98→~30%. The `--curve-prior-weight` CLI flag was
added to ImpactGate for exactly this (K in `w=n/(n+K)`). Leaving `baseline_file: null` reverts to
the seed curve. The baseline file is passed as an ABSOLUTE path so `impact-gate` reads it from
OUTSIDE the arm worktree — it is never committed to an evolve branch nor visible to the agent.

**One parser, pinned, proven before the run.** The gate's lizard lives in the `impact-gate`
CLI's OWN venv, not this harness's — two installs that drift independently. They must be the
same version, because the gate is graded against a baseline built with the harness's lizard.
`requirements.txt` pins `lizard==1.23.0`, `setup.sh` applies the same pin to the sibling
ImpactGate venv, and `parser_selftest.require` proves both stacks can still see an annotated
class before any agent runs (refusing to start otherwise); `provenance.impact_gate.parser_probe`
records the result and the gate's lizard version alongside the harness's in `tool_versions`.
See the 2026-09 gotcha for what a blind parser cost.

**Two more pinned tools, proven before the run (design B).** The quality gate's verdict is
decided by two external binaries. They are pinned in `tools/package.json` + `package-lock.json`
(`jscpd` and `@ast-grep/cli`, exact versions), installed with `cd tools && npm ci`, and invoked
via `tools/node_modules/.bin/...` (config `tools.jscpd`/`tools.astgrep`, anchored to the config
dir in `main`; bare `sg` also collides with shadow-utils). `quality_selftest.require` — called
beside `parser_selftest.require` in `run_experiment.main`, fail-closed — asserts BOTH the pinned
versions AND a golden fixture (a staged verbatim-duplicate method + a `b == true` in a second
file must fail the gate with ≥1 clone and ≥1 smell finding). A version string alone is not
enough: as with lizard, behaviour is the authoritative check. Note ast-grep 0.45.0 takes `-r` as
a single rule FILE, so `quality_gate` loads the multi-document `astgrep-rules/` via a generated
`sgconfig.yml` (`ruleDirs`) + `scan -c`; only single-AST-node patterns are legal (multi-statement
seeds were dropped, see the rule file's own header). `record_refactor_correctness` and the
recorded `verbosity` metric are unchanged.

**Do not regress.** The refactor turn reuses the *same* isolation as the implement turn
(history-less sandbox, blind agent view, Landlock confine) — its prompt references only the
current change + flagged files, never future tests. The gate scores production Java only (the
acceptance dir is excluded from the mirror-back, non-Java is ignored by lizard). Correctness is
still enforced exactly where it was (the final accepted implementation's gate); refactors are
measured, never enforced. Keep the ungated strategies byte-for-byte unchanged.

## The two design pillars added 2026-08 (do not regress these)

### 1. Blind-agent regression measurement
The agent is given **only the current checkpoint's own test** while it works;
the full cp01..cpK suite is installed **only for the post-commit gate**. Rationale:
if the agent sees every prior test it has a checklist and regressions are ~0 by
construction, which measures the wrong thing. Blind, a change that silently
breaks unseen prior behaviour actually regresses, and that's the architecture
signal. Implemented by `set_agent_view` / `install_measurement_suite` /
`detect_agent_tamper` in `run_experiment.py`. `analyze` re-derives regressions
from the captured raw test map, so this needs no analyze change.

**Test modes (`--test-mode`, required, no default).** The above is the `blind` mode.
A run must pick one of two modes on the CLI, and the choice only changes what the
agent SEES while it works, never how it is scored (the gate always installs and runs
the full authored cp01..cpK suite). `_install_agent_view` branches on `cfg['test_mode']`:
- `blind`: shared infra + this checkpoint's own test, neutralised to `AcceptanceTest.java`
  (no CpNN, no @Tag). The pessimistic condition, measuring resistance to silent breakage.
- `full`: the full authored cp01..cpK suite (real CpNN names, mutative priors winning,
  capped at k so future checkpoints stay hidden). The optimistic condition, measuring
  what it costs to stay correct when the agent can run the accumulated regression suite.
Tamper detection is mode-aware (`_detect_sandbox_tamper`): blind compares the one neutral
test, full compares every visible cp01..cpK file. The mode is printed at each checkpoint
head and stored in `provenance.json` (`test_mode`), so a chain's mode is always recoverable.
If you add a mode, extend `TEST_MODES`, `_install_agent_view` and `_detect_sandbox_tamper`.

### 2. Per-call config/memory isolation
Each `claude -p` runs under a throwaway `CLAUDE_CONFIG_DIR` seeded with **only the
login credentials** (`_seed_clean_config_dir` in `agent.py`). Without this, Claude
Code auto-memory writes project "learnings" into
`~/.claude/projects/<repo>/memory/`, keyed by the git common dir, which for all
of an arm's worktrees is the ONE base repo. That memory would leak across
checkpoints (breaking the no-context condition) and, asymmetrically, between
arms. A fresh login-only config dir per call guarantees a pristine, stateless
Claude; the real `~/.claude` is never read or written. **If you touch `run_agent`,
preserve this.**

### 3. History-less, sequence-blind sandbox (the agent can't tell it's checkpoint N)
The agent does NOT run in the git worktree. Per checkpoint, `run_chain` builds a
fresh **sandbox** at **`sandbox_root`** itself (config default `${HOME}/sandbox`, via
`_prepare_agent_sandbox`). It is a plain project directory with the source mirrored **directly
under it**, on a **separate tree from `work_root`**. So the agent's cwd looks like an
ordinary `sandbox/` project: **nothing in the path** (no run_id/arm/strategy/chain) hints
at a checkpoint sequence, and there is no worktree/`.git`/capture sibling to `cd ..` into.
It is reused across chains (which run sequentially) and rebuilt fresh each turn. It is an
rsync mirror of the worktree source with **`.git`, `target/`, and `evolve-results/` excluded**
(the last is critical: the per-checkpoint capture committed into the worktree, such as `cp01.json` and
`cp02.json`, would otherwise leak the whole sequence to a later agent), plus a fresh
acceptance dir holding ONLY the shared infra and **this checkpoint's own test renamed
to the neutral `AcceptanceTest.java`**. There is no `CpNN` in the filename or class, and no
`@Tag` (`_neutralize_test`, with a leak guard that raises if any `@Tag` or `cp\d+`
survives). The test sources' comments are also kept free of `cpNN`. So the agent sees
one test with no number, no git history (can't `git log` the `cp01 agent …` / `cp02 …`
sequence or `git show` prior tests), and no prior build output.

The worktree carries **only production code + pinned docs**. No acceptance tests. The
9-step per-checkpoint flow: (1-3) agent works in the sandbox; (4) `mirror_source(sandbox,
wt, extra_excludes=(acceptance/,))` copies the PRODUCTION result back and COMMIT 1
records the production-only delta; (5) tamper detection compares the sandbox's
`AcceptanceTest.java` to the regenerated neutral version; (6) the gate is prepared IN
THE SANDBOX: pinned docs restored to base, neutral test swapped for the full authored
cp01..cpK suite (real CpNN names for scoring); (7) `scrub_test_artifacts(sandbox)` runs
`mvnw clean` then `run_tests(sandbox, …)`; (8) COMMIT 2 normalises the worktree (restore
pinned docs) **and commits this checkpoint's raw capture** under `evolve-results/capture/cpNN.*`;
(9) the sandbox is wiped. The probe likewise runs in a fresh history-less mirror. Retries
re-mirror the untouched worktree.

**Why it exists:** at cp60 the agent `cd`-ed out of the worktree into the harness
`acceptance/` suite AND ran `git log` at 27/60 checkpoints, reading the withheld
mutative tests and the whole sequence; and the filename `Cp60Tests`/`@Tag("cp60")`
handed it the number outright. Also keep **both** `sandbox_root` (config default
`${HOME}/sandbox`) and `work_root` (`${HOME}/pe-work`) OUTSIDE the harness repo and
**separate from each other**, so the agent's cwd (the sandbox) has no ancestor or
sibling path to a worktree's `.git` or to `acceptance/`/`checkpoints.yaml`. If you touch
the agent-turn flow, preserve: agent runs in the sandbox under `sandbox_root` (never the
worktree); sandbox has no `.git`; the visible test is the neutral `AcceptanceTest.java`;
the worktree stays production-only.

### 3b. Filesystem confinement of the agent (Landlock): the sandbox is not enough
A clean sandbox does NOT confine the agent: the process can read the whole disk. In a
run this bit hard. At cp01 the agent ran `find /`, reached `~/.local/share/Trash` (a prior run,
moved to Trash not hard-deleted, holding all 60 `CpNN` tests) and grepped generated
sources there; the harness `acceptance/` (124 tests) and `checkpoints.yaml` are equally
reachable by `find /`. The withheld material can't be deleted (it's the source of truth),
so `agent.run_agent` confines the agent PROCESS instead, via **Landlock** (`harness/landlock.py`,
kernel LSM, no root, no bwrap, no user-namespace; bwrap is unusable here because Ubuntu's
`apparmor_restrict_unprivileged_userns=1` blocks unprivileged userns). A `preexec_fn`
allowlists only the sandbox + toolchain (`/usr /etc /opt /bin /lib* /sbin /proc
/run/systemd/resolve`, `~/.local/share/claude`, `~/.local/bin`; rw `~/sandbox ~/.m2 /tmp
/dev` + the throwaway cfg dir) and `landlock_restrict_self`; everything else returns EACCES,
inherited by every child the agent spawns and impossible to lift. Gated by
`isolation.agent_confinement.enabled` and **fail-closed**: `verify_denied` runs the same
confinement over a throwaway `sh` and, if any sentinel (`checkpoints.yaml`, `acceptance/`,
HARNESS_DIR, `work_root`) is still readable, or Landlock is unavailable, the turn is
**refused** (no agent runs) rather than run un-blinded. Check support with
`python harness/landlock_selftest.py` (expect `OVERALL: PASS`). The probe is confined too.
NOTE the sentinel test must read per type (`cat` a file, `ls` a directory) because
Landlock does not restrict `stat()`, so `ls <file>` would false-positive.

## The acceptance suite (`acceptance/`)

Black-box MockMvc tests (`@SpringBootTest`, full app boot) so both arms are judged
identically. One primary `CpNNTests` per checkpoint, `@Tag("cpNN")`, methods
prefixed `core`/`error`/`functionality`. Shared base `AcceptanceBase` +
`AuditLogCapture` (asserts the `AUDIT`/`NOTIFY` loggers via a Logback appender).
Uses `tools.jackson` (Jackson 3), not `com.fasterxml`.

**Deterministic oracle.** Every test asserts an **exact** value (never
`exists`/`isNotEmpty`/a TODO) because it is the regression oracle: an existence
check can't detect a corrupted value. Since the checkpoint's own test is handed to
the agent, the test *can* pin the exact expected value and the agent must match:
- Pure derivations → assert the computed string/number.
- Hashes / Luhn → the test **recomputes** them (`sha256hex`, `shaHex`, `luhn` in
  `AcceptanceBase`) and asserts equality; or asserts a relationship (same inputs →
  same id) where internal normalization is opaque.
- Lookups (region/postcode/timezone/holiday) → **pinned reference tables** in
  `AcceptanceBase` (`CITY_REGION`, `REGION_POSTCODES`, `REGION_TIMEZONE`,
  `HOLIDAYS`) mirrored into the relevant checkpoint specs, so both arms implement
  identical ground truth and the test asserts the exact value.
- Removed-field mutations assert **absence only** (so they survive later
  restructuring without needing to be re-listed).

**Mutative checkpoints and the `mutates` discipline.** A mutative checkpoint
(`type: mutative`) revises prior rules. Its `tests:` manifest ships its own test
PLUS updated copies of exactly the prior tests it changes, under a `cpNN/`
subdir, installed **by basename** so `cp32/Cp14Tests.java` overwrites the running
`Cp14Tests.java`. `_authored_set` resolves the current version of each test by
walking checkpoints 0..k (latest wins). **Invariant that keeps the signal clean:**

> A mutation's `mutates` list must overwrite EXACTLY the set of prior tests whose
> asserted output it changes. No more, no less.

Too few → a prior test asserts a now-changed value and fails as a *false*
regression. Too many → you mask a rule that could have caught a real regression.
Exactly right → any *other* prior test that goes red is a genuine regression.
Auditing `mutates` for completeness is part of authoring any mutation. (Examples
found this session: cp48→[14], cp56 must include 9/14/16/21/31 because it removes
customerCode+membershipNumber, cp60 must include 11/28/41/57 because it moves
identifiers under a nested `identity` object. A later run-driven audit added two
more that only surfaced at run time: **cp40 must include 15** because the points system
makes an email owner level 2, not the old cap-3 level 3; and **cp36 must include
35**. Once the household key becomes `(lastName, postcode)` it collides with the
soft-match key, so the soft-match scenario becomes a household in the cp36-51
window.)

The highest-yield audit is **field removal/relocation**: whenever a mutation
removes a field (cp56 removes customerCode/membershipNumber/checkDigit) or moves
one (cp60 relocates memberId/identityKey/householdId under `identity`), grep the
resolved prior suite for every reader of that field (`jsonPath("$.field")` AND
Java `.get("field")`) and confirm each reader's checkpoint is in `mutates`. The
run itself is the ground-truth audit: if a run is green through checkpoint N, every
mutation up to N has a complete `mutates` list; gaps only ever surface as a prior
test that flips to failing right at a mutative checkpoint (e.g. cp52 removed the
same-name+postcode 409 but forgot Cp10).

**Watch for key-collision between rules.** Two rules keyed on the same tuple will
interfere once a mutation ties them together. The soft-match (cp35, keyed on
lastName+postcode) and the computed household (cp36, keyed on lastName+postcode)
collide, so the soft-match is subsumed by the household-duplicate block until cp52
folds duplicate detection back into the identity key. When you add a rule, check
whether its discriminating tuple equals an existing rule's; if so, order/spec them
so the interaction is intended, and make the affected tests assert the *combined*
observable behaviour, not each rule in isolation.

**Authoring pitfalls (each caused a false regression in run 202608070510).**
- **Never put a digit in a name field.** The base app validates owner names as
  letters only (`^[\p{L}]+...`), so `firstName = "Mem" + i` is rejected with 400 and
  the test's own setup fails. Use `uniqueFirstName()` / `uniqueLastName()` /
  `letters()`.
- **To force a duplicate/identity collision, submit a pure full duplicate**
  (`createOwner(a.deepCopy())`), never a copy-plus-one-tweak. A tweak like adding
  `sharesHousehold` to the second owner only de-syncs the `householdId` that the
  identity key is built from, so the keys differ and no collision fires (this passed
  on one arm and failed on the other, a false signal). "Identical in every field
  collides" is the one invariant that survives all three identity-key mutations
  (cp28, cp36 makes householdId computed, cp52 switches to a soundex key).

**NEVER edit an existing acceptance `.java` file (or `AcceptanceBase`) while a run
is in flight.** The harness re-reads the `.java` tree every checkpoint
(`install_measurement_suite`/`set_agent_view`), so any edit to a file already in
the resolved set takes effect immediately -- for the current chain AND every
remaining chain -- while `checkpoints.yaml` (loaded once at startup) does NOT
update, so the manifest and the files desync. This bit hard once: strengthening the
base `Cp53Tests.java` mid-run to assert `customerCode` (removed at cp56) NPE-d
cp56-60 in every remaining chain, because the running manifest never mutated 53.
Only two things are safe to change mid-run: `checkpoints.yaml` (ignored until the
next launch) and brand-NEW `cpNN/CpMM` files that the running manifest does not yet
reference (never installed). Apply all `.java` edits with the run stopped.

**The generator is superseded.** `acceptance/scaffold_tests.py` originally
generated the whole tree from `checkpoints.yaml`, but the tests were then
hand-authored to be deterministic. **The `.java` tree is now the source of
truth**. Do NOT re-run the generator (it would overwrite authored tests back to
stubs). Edit the `.java` files directly.

## Isolation & fairness (all must hold)

- **No carried context.** Fresh `claude -p` per checkpoint, never
  `--continue`/`--resume`.
- **`CLAUDE.md` pinned** into the arm repo, restored to base after each agent
  turn (can't become cross-checkpoint memory); edits flagged in `pinned_touched`.
- **Per-call `CLAUDE_CONFIG_DIR` isolation** (pillar 2 above).
- **Structural metrics Java-only**, identical tools/thresholds both arms; YAML LOC
  reported separately (`yaml_loc`).

## Resilience (retry classification in `agent.py`)

Terminal agent outcomes are classified against the result text AND the stderr tail
(auth messages land on stderr), gated to failed turns so a healthy build can't
false-match:
- **`_LIMIT_PHRASES`** (quota/session limit) and **`_AUTH_PHRASES`** (OAuth expiry
  / re-login needed) → `limit_reached`: the caller **waits and polls the SAME
  checkpoint** (`wait_for_window`, `poll_seconds` default 30 min) until it
  recovers. A manual `/login` mid-run resumes. **Auth phrases are kept distinctive**
  (not generic `401`/`unauthorized`, which a security-feature checkpoint's own test
  output could emit → endless false wait).
- **`_RETRYABLE_PHRASES`** (network/overload) → short exponential backoff, aborts
  after `max_transient_attempts`.
- Anything else on a failed turn is treated as a completed no-op, which is why the
  auth classification matters: **before the 2026-08 fix, an OAuth expiry was an
  unclassified no-op that silently committed empty deltas and burned whole chains.**

### Invalid gates (`correctness._gate_invalid`) — the same lesson, applied to the gate

An **aborted** gate is not a failed gate. `count_regressions` is
`prior_passing - now_passing`, so a run that produced NO results scores as a
regression on **every prior rule** — the more checkpoints a chain has survived, the
more catastrophic the phantom looks. Two detectors, both narrow:
- **no results while the build compiled.** At checkpoint K the authored suite always
  holds ≥ cp01's test, so an empty map cannot be legitimate. A *failed build* exits
  earlier with `build_ok=False` and stays scored — the agent breaking compilation is
  a real verdict.
- **a Surefire fork-death marker** (`_CRASH_MARKERS`) in the test console, which is
  how a *partial* run announces that the rest of the suite never got a verdict.

Retry is deliberately asymmetric: an abort is retried (`build.test_attempts`,
default 3, `test_retry_seconds` apart), a test **failure never is** — retrying
failures would launder exactly the regressions this experiment exists to measure.
After the last failed try the checkpoint is `gate_invalid`: correctness fields blank,
`prior_passing` **carried forward unchanged** (adopting the empty set would corrupt
the next checkpoint too, then fake a recovery on the one after), chain continues.
`analyze` drops these rows from every correctness aggregate (`scored()`), keeps their
structural metrics, and lists them under **Invalid gates** in `summary.md` so the
exclusion is never silent. Old captures are recognised by signature, so re-analysis
repairs runs recorded before the fix.

### Backfilling a metric that needs new config (`analyze._resolve_run_config`)

`analyze` derives with the run's **committed config snapshot**, so metrics match how
that run was configured. A metric added later needs config the snapshot cannot have,
so keys **absent** from the snapshot are filled from the live `config.yaml` and each
fill is logged (`! arms.<arm>.<key> absent from the run's config snapshot`). Recorded
values always win; only gaps are filled. This exists because the failure mode is
silent, not loud: `node_roots` was added 2026-08-23, and the first backfill of
`node_closure_stats` fell through to the single-`entry_handler` fallback, reporting
OfficeFloor as a 1-node arm at CC 8 instead of a 19-node pipeline. The tell was that
`node_cc_median`, `node_cc_max` and `node_path_cc` were byte-identical — three
statistics that can only coincide when there is exactly one node. **When adding a
metric with new config, check the backfill log for the fill lines and sanity-check one
checkpoint by hand before trusting the trajectory.**

### Rare-event guard (`analyze.MIN_EVENTS`)

A validation statistic resting on one or two checkpoints is not a result, and a
bootstrap CI does not know that. In `full-202608102319` the `true_regressions`
correlation ran on a series that was zero at 598 of 599 scored checkpoints and
still returned ρ = +0.052 with a CI excluding zero, because every resample carried
the same lone event. `spearman_ci` now also returns `k` (`_informative`: values
differing from the series' modal value) and refuses to report below
`MIN_EVENTS`; the same floor gates the `impact_composite`-vs-true-regression
medians. Suppressed rows are printed as **not tested** with their `k`, never
dropped — an absent row is indistinguishable from one nobody computed. Continuous
outcomes (cost, tokens, time) are untied so `k ≈ n` and they are unaffected;
`blind-202608100006` keeps its published ρ values (k = 11 per arm).

## Running it

`--test-mode {blind,full}` is REQUIRED on every run (no default); see the blind-agent
pillar above for what each mode shows the agent. `--model <id>` overrides `config.yaml`'s
`model:` for one run (passed straight to `claude --model`, recorded in `provenance.json`);
it exists so third parties can reproduce the experiment against a different AI without
editing config — see [`docs/RUN_WITH_A_DIFFERENT_MODEL.md`](docs/RUN_WITH_A_DIFFERENT_MODEL.md).

```bash
python -m harness.run_experiment --config config.yaml --test-mode blind --dry-run          # wiring check
python -m harness.run_experiment --config config.yaml --test-mode blind --arm spring --chain 0 --max-checkpoints 12   # smoke
python -m harness.run_experiment --config config.yaml --test-mode blind                     # full run, blind condition (chains × 2 arms)
python -m harness.run_experiment --config config.yaml --test-mode full                      # full run, full-suite condition
python -m harness.run_experiment --config config.yaml --test-mode blind --run-id <id> --arm officefloor --chain 2      # re-run ONE chain into an existing run
python -m harness.analyze --config config.yaml --run-id <id>
```

`make_worktree` is idempotent per run_id (force-removes the worktree, deletes the
branch, recreates from base) so a single-chain re-run into an existing run_id is
safe and leaves completed chains untouched. Loop order is **chain-outer,
arm-inner** (`spring/chain0, officefloor/chain0, spring/chain1, …`) so arms are
time-matched.

**Compile-check the resolved suite at any depth** (how test authoring was verified
this session):
```python
from harness import run_experiment as R          # in a throwaway base worktree
R.install_measurement_suite(wt, cfg, checkpoints, k)   # then ./mvnw -q -B -DskipTests test-compile
```

## Config knobs (`config.yaml`)

- `model`: the fixed coding agent (default `claude-opus-4-8`). Overridable per run
  with `--model` (no config edit needed); the value flows through `cfg["model"]` to
  every agent turn, the probe, and `provenance.json`, so a run is self-describing
  about which AI produced it. This is the seam third parties use to reproduce the
  experiment against a different model — see
  [`docs/RUN_WITH_A_DIFFERENT_MODEL.md`](docs/RUN_WITH_A_DIFFERENT_MODEL.md).
- `chains`: independent runs **per (arm, strategy)**; total = chains × arms. `10`
  for tight CIs, `1` for validation.
- `arms.<arm>.entry_handler`: the ONE create function whose CC trajectory is
  tracked (Spring `OwnerRestControllerV1::addOwner`, OfficeFloor `BuildOwner::service`).
- `arms.<arm>.function_package_glob`: OfficeFloor's wired-function dir (fn_count /
  fn_nloc_max); null for Spring.
- `limits.*`: poll/backoff/cap tuning for the resilience paths.
- `probe.at_checkpoints` (every 10) and `probe.expected` (recall tokens spanning
  cp1..60).
- `isolation.pin_files`: `["CLAUDE.md"]`.
- `impact_gate.*` (the `impact_gated` strategy only): `cmd` (how to invoke the
  `impact-gate` CLI; each element `${HOME}`/`~`/`$VAR`-expanded in `main`), `strategy`
  (the activating strategy name), `enforcement` (`advisory` default / `block` — see the pipeline
  section; advisory records and never stops, block is the hard gate), `block_percentile` /
  `warn_percentile` (fail line vs the reference distribution; **calibrate** — default 95, see the
  pipeline section), `max_refactors` (default **1** — advisory is one clean-up refactor then
  re-attempt), `stop_scope` (`chain` default / `run`; only meaningful under `enforcement: block`),
  `record_refactor_correctness` (record-only full gate on each refactor), `implement_strategy`
  (which `prompt_strategies` entry the implement turn uses — design B: `just-solve`, NEUTRAL, no
  formula), `baseline_file` (ImpactGate baseline JSON to grade against — a reference arm's
  distribution, from `build_impact_baseline`; resolved to an ABSOLUTE path so it stays outside the
  worktree; null → seed) + `curve_prior_weight` (0 → pure baseline percentile), `measure_config`
  (optional impact-gate ignore globs; resolved against the config dir), and the `refactor_prompt`
  template (`{spec}`/`{files}`/`{drivers}`/`{grade}`/`{block}`).
  **The impact formula (`cost = max(WMC_other,1)·CC·max(1,Δlines)`, summed, × files) is NOT in the
  `impact_gated` prompts** (design B): the implement turn is neutral and the `refactor_prompt` is
  symptom-only (locations, no cost figures). The formula appears verbatim as the AI's objective ONLY
  in the separate `metric-in-prompt` strategy (condition 4, kept for reproducibility). It lives in
  three places — the `metric-in-prompt` prompt, the design-A archived prompt, and `impact_stats` in
  `metrics.py` — keep them in sync if the measure ever changes.

## Gotchas / lessons (2026-08, 2026-09)

- **A parser that cannot read a file measures it as perfect (2026-09-01).** lizard **1.24.0**
  regressed its Java state machine: a bare annotation immediately followed by a parenthesised
  one at class level (`@Entity` then `@Table(name = "owners")`) drops the second `@` in
  `_state_post_decorator` and the class declaration is eaten as a method body — the file yields
  **zero functions**, silently. Under it only 213 of Spring's 307 production functions existed:
  `Owner.java`, `Pet.java` and all seven `Jpa*RepositoryImpl.java` vanished. ImpactGate's venv
  had 1.24.0 while this harness had 1.23.0, so `blind-202608312216` scored cp04/cp07 (methods
  accreted onto `Owner.java`) as **impact 0**. Replayed over 178 Spring checkpoints of
  `blind-202608100006`: 11% of Spring's impact mass hidden and **6 of 78 changes that should
  have failed the gate passed** — two of them ~2.5× the block line — while OfficeFloor lost no
  verdicts at all (its changes sit far below the line either way). That asymmetry biases the
  gated arm toward "the gate could not hold Spring", i.e. toward the very conclusion under
  test. The run was killed and restarted. Fixed by the pin + `parser_selftest` above; the tell
  in a capture is `impact_gate.attempts[].impact == 0` with a non-empty `.agent.diff` touching
  a `@Entity` class. Never take "0" from a parser as "no complexity" without proving the parser
  can see the file.
- **A crashed gate used to read as a mass regression.** On `full-202608102319` a
  Surefire fork died (exit 134, `The forked VM terminated without properly saying
  goodbye`) at 3 OfficeFloor checkpoints and 1 Spring one. Each recorded
  `build_ok=True, total_selected=0, results={}`, which scored as the whole prior
  suite regressing: OfficeFloor's true-regression count read **143** when the real
  figure was **0** (Spring: 34 → 4). The tell is `total_selected=0` on a checkpoint
  whose neighbours pass 60+ tests, plus the agent's own turn reporting a green suite.
  Fixed by `_gate_invalid` + retry (above); `analyze` now repairs old captures by
  signature, so re-run it rather than trusting any correctness number produced
  before 2026-08-22.
- **"60 checkpoints captured" ≠ valid.** An auth-dead turn still writes a capture
  record. The dead signature is `agent.ok=False, cost_usd=0, output_tokens=0,
  num_turns=1` and an empty agent commit. Always scan for it before trusting a
  chain (this is how a run that looked "Spring 3/3, OF 2/3" was really "only Spring
  chain0 valid", because auth had died at OF chain0 cp09).
- **Both arm base repos already ship a hard-delete `DELETE /api/owners/{id}`.**
  cp46 (`exclude-deleted`) therefore *converts* it to a soft-delete (flag+retain);
  its test asserts GET-after-DELETE returns 200 + `deleted=true`, which fails if any
  hard-delete remains.
- **Back-half checkpoints are slow.** Threshold tests (cp18 fills a city to 50,
  cp19 creates 100, cp54 to 40) re-run at every later gate, so a full chain
  averaged ~8 min/checkpoint (~4× the shallow published run). Budget a 20-chain
  run at roughly a week and ~$1.5k.
- **Request-contract changes must stay backward-compatible.** New request fields
  (cp29 postcode, cp44 structured address) are additive/optional so the shared
  `ownerNode()` helper stays valid at every later gate in both arms; a strict
  rename would spray false regressions (this is why cp60 avoids renaming request
  fields, see its note in `checkpoints.yaml`).
- **"The tool did not run" must never render as "the tool found nothing."** Three
  instances of this shape were found on 2026-09-05, all silent: `metrics.verbosity()`
  falls back to whichever of jscpd/ast-grep produced output, so a missing binary turned
  Verbosity into a clones-only number with no error (both blind runs measured it that
  way); `metrics._pattern_lines_astgrep` passed a rules DIRECTORY to `scan -r`, which
  takes a rule FILE, so ast-grep errored to stderr, left stdout empty, and that parsed
  as zero matches; and `quality_gate._smell_lines` ignored the exit code, so ONE
  unparseable rule (exit 8 aborts the whole directory) switched the smell half of the
  gate off while it kept reporting passes. Fixed by checking `returncode`, delegating
  metrics to the gate's correct invocation, and recording `clones_ran`/`smells_ran` in
  capture. The general rule when adding a tool-backed metric: distinguish
  ran-and-found-nothing from could-not-run, and make the second one visible in the
  summary — a zero is indistinguishable from a clean result to every reader downstream.

- **A manually fetched branch can silently DOUBLE an arm's sample.** Both arm repos
  share one upstream, and `refs/heads/evolve/<run>/*` is not arm-scoped, so a
  convenience fetch (e.g. restoring a cleaned run's branches to re-analyze it) drops
  BOTH arms' chains into whichever repo you ran it in. `analyze._evolve_branches`
  walks repos, not arms, so the duplicated arm was then measured twice — 11 "spring"
  chains where 10 exist — and the extra rows look exactly like real chains, so the
  chain-cluster bootstrap reports CIs on ~2x the true n. Fixed 2026-09-05: a branch is
  only accepted from a repo `config.yaml` assigns to that branch's arm, and skips are
  printed. When restoring branches by hand, fetch each arm's refspec into its OWN repo
  (`refs/heads/evolve/<run>/<strategy>/<arm>/*`), then check
  `git for-each-ref refs/heads/evolve` in both repos shows only that arm.

- **`work/`, `results/`, `.venv/` are gitignored;** the base branches stay
  pristine. Clearing `work/` deletes capture files, so analyze then needs the pushed
  evolve branches instead.

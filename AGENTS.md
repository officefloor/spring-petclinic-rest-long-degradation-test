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
- **Concentration** — `entry_cc` and `wmc_max` (god-method / god-class), corroborated
  by `erosion_handler` (erosion scoped to the entry handler's own class).
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

## Module map (`harness/`)

| file | responsibility |
|---|---|
| `run_experiment.py` | the driver. `run_chain` walks checkpoints; two commits per checkpoint; the agent-view / measurement-suite / gate / capture flow. Entry point `main`. |
| `agent.py` | wraps headless `claude -p`. `run_agent` streams stream-json events, classifies terminal outcomes (limit / transient / **auth**), and **isolates config per call** (see Isolation). `probe()` is the read-only cold-reader. |
| `correctness.py` | parses Surefire XML → raw `{test_id: passed}` map; `score_results` / `outcome_row` derive Strict/ISO/Core, Normalized Change, `regressions`, `true_regressions` (mutative-aware). |
| `metrics.py` | structural metrics over git commits: `compute_all` is the ONE definition called by both runner and analyze. lizard CC/SLOC, erosion (whole-app + `erosion_scoped` + `handler_scoped_erosion`), hotspot, WMC, blast-radius, change-spread, re-edit coupling, `impact_stats` (structural-impact score); jscpd + ast-grep for verbosity. |
| `capture.py` | assembles the raw, irreproducible per-checkpoint record (`checkpoint_record`) and run `provenance`. |
| `analyze.py` | **always recomputes** from commits + capture (no derived data is read back). Materializes each checkpoint tree, re-runs `compute_all`, re-scores correctness, fits slopes with bootstrap CIs, writes `results/<run_id>/analysis/`. |
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
   REAL: a failure on a prior rule the agent couldn't see is the signal.
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

## Running it

`--test-mode {blind,full}` is REQUIRED on every run (no default); see the blind-agent
pillar above for what each mode shows the agent.

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

## Gotchas / lessons (2026-08)

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
- **`work/`, `results/`, `.venv/` are gitignored;** the base branches stay
  pristine. Clearing `work/` deletes capture files, so analyze then needs the pushed
  evolve branches instead.

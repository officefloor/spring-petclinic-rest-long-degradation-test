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
existing units never grow). Erosion slope is the decisive statistic.

## What it does per checkpoint

1. Runs a **fresh** headless `claude -p` with only the checkpoint spec (no
   carried conversation — the SlopCodeBench condition that makes this a test of
   the code as a self-describing index).
2. Commits, then gates on `build + accumulated acceptance suite cp01..cpK`.
3. Scores correctness (Strict / ISO / Core, Normalized Change, regressions).
4. Computes **Erosion**, **Verbosity**, hotspot / function-package size, and
   blast radius over **Java production source only** (YAML counted separately).
5. At each phase boundary runs a read-only **cold-reader probe**.
6. Appends one row to `results/records.csv`.

## Prerequisites

- Python 3.10+ and `pip install -r requirements.txt`
- The `claude` CLI on PATH, authenticated.
- A JDK + the repo's Maven wrapper (`./mvnw`).
- Optional (for the Verbosity metric; it degrades gracefully if missing):
  - `jscpd` — `npm i -g jscpd`
  - `ast-grep` — provides the `sg` binary.

## One-time repo setup (the experimenter's job)

For **each** arm branch (`spring-compare`, `officefloor-compare`):

1. Create a **base ref** *before* the 20 owner-lifecycle features but *with*
   all acceptance tests already committed:

   ```
   git checkout spring-compare
   # add all Cp01..Cp20 {Core,Error,Functionality}Tests classes (they fail now)
   git commit -am "evolve acceptance suite"
   git tag evolve-base-spring
   ```

   Point `arms.spring.base_ref` (and the OfficeFloor equivalent) at that tag.

2. Acceptance test **contract** (so scoring works without JUnit tags in the
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
   - A ready-made suite is in `acceptance/` — copy its `src/test/java` tree into
     each arm at the base ref.

   **Acceptance-suite assumptions** (adjust to your exact API before running):
   - 56 tests across 20 classes (`AcceptanceBase` boots the app with
     `@SpringBootTest @AutoConfigureMockMvc` and drives the REST API; identical
     for both arms). `AuditLogCapture` asserts the `AUDIT` logger (cp09/cp10)
     via a Logback appender — rename the logger there if yours differs.
   - Endpoints assumed: `POST/PUT/GET /api/owners`, `POST /api/owners/{id}/pets`,
     `PUT /api/pets/{petId}`; `PetType` id 1 exists in seed data.
   - New fields the agent must add: `email` (cp12/13), `postcode` (cp17),
     `registrationDate` (cp11), `displayName` (cp20). Tests read them back over
     GET, so they fail until the field is added AND serialised.
   - **Headroom matters.** Several behaviours (required fields, telephone
     pattern) may already exist in stock PetClinic. For those, the base ref must
     have them *removed* so the checkpoint has work to do; otherwise that
     checkpoint starts green and contributes no degradation signal. Strip them
     when you cut `evolve-base-*`, or drop those checkpoints.
   - Tests use unique phones/emails per created owner, so they are independent
     within a shared-context boot. Keep it that way if you add tests.

3. Set `arms.spring.hotspot.methods` to the actual method names new owner
   behaviour lands in (default `addOwner`/`updateOwner`).

## Run

```
# sanity-check wiring without spending tokens:
python -m harness.run_experiment --config config.yaml --dry-run

# one arm, one chain, first checkpoint only (smoke test the full loop):
python -m harness.run_experiment --config config.yaml --arm spring --chain 0 --max-checkpoints 1

# full default run (all arms, active_strategy, all chains):
python -m harness.run_experiment --config config.yaml

# other prompt-intervention arms:
python -m harness.run_experiment --config config.yaml --strategy anti_slop
python -m harness.run_experiment --config config.yaml --strategy plan_first

# analysis (slopes + CIs, EvoScore, Zero-Regression Rate, plots):
python -m harness.analyze --config config.yaml
```

Results append to `results/records.csv`; analysis writes
`results/analysis/summary.md` and PNGs.

## Reading the result

`summary.md` reports the degradation slope `m` with a 95% bootstrap CI over
chains, per arm/strategy, for `erosion`, `verbosity`, `cost_usd`,
`cache_read_tokens`, `hotspot_cc`.

**Confirms the thesis** if `m_erosion(spring) > 0` (CI excludes 0),
`m_erosion(officefloor) ≈ 0`, and the spring-minus-officefloor slope CI excludes
0 — with the same pattern for verbosity and cache-read tokens, higher OfficeFloor
EvoScore at γ>1, and higher OfficeFloor Zero-Regression Rate in the Late/Final
phases. The strong form: OfficeFloor lowers the **slope** structurally, which
SlopCodeBench found prompting could not do (it only lowered the intercept, at
higher cost).

**Refutes it** if OfficeFloor erosion also climbs (a wiring "god pipeline" or an
accreting shared function) or Spring stays flat because the agent refactors each
time. Report either honestly.

## Notes and honest limitations

- Structural metrics are Java-only and use identical tools/thresholds for both
  arms, so OfficeFloor's file-spreading cannot distort LOC. YAML LOC is logged
  separately (`yaml_loc`).
- `cache_read_tokens` reflects within-session re-reads; it is the comprehension
  proxy here. True "tokens-to-first-edit" needs `--output-format stream-json`
  parsing and is left as an enhancement.
- Probe recall is a crude keyword hit-rate; grade the probe transcripts properly
  (or with an LLM judge) for publication.
- A chain is path-dependent; use ≥5 chains and read the bootstrap CIs, not
  single runs.
- The ast-grep seed ruleset is small (5 rules vs SlopCodeBench's 137). Extend
  `astgrep-rules/` before trusting absolute verbosity values; the *slope* is
  robust to a fixed ruleset because both arms use the same one.
```

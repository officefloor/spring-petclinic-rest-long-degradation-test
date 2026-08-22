# Run it yourself with a different AI model

This experiment deliberately holds the **AI coding agent fixed** and makes
**architecture** the independent variable (see [`README.md`](../README.md) and
[`AGENTS.md`](../AGENTS.md)). The published runs used `claude-opus-4-8`.

A fair question is: *"Won't a better model just refactor the Spring hotspot each
time and erase the effect?"* That is an empirical question, and this harness is
built to answer it **by you, with whatever model you think is better.** Re-run
the exact same experiment against a different AI and see whether the
architecture signal (complexity concentrating in the Spring arm, staying flat in
the OfficeFloor arm) shrinks, holds, or grows.

If you do this, please **share your results back** (see
[Share your results](#share-your-results-back)). That gives the finding
independent replication.

---

## The short version

Everything is already wired for it. Swap the model with one flag:

```bash
python -m harness.run_experiment \
  --config config.yaml \
  --test-mode blind \
  --model claude-opus-5 \        # <-- the only change vs. the baseline run
  --run-id opus5                 # <-- a descriptive id so branches don't collide
```

- `--model` overrides `config.yaml`'s `model:` for this run. The value is passed
  straight through to `claude --model`, so **any id the `claude` CLI accepts
  works**. A full id (`claude-opus-5`) or an alias (`opus`, `sonnet`, `haiku`).
- The model you used is recorded in each run's `provenance.json`, and the
  *resolved* model id is captured on every agent turn, so a run is always
  self-describing about which AI produced it, even if you passed an alias.
- Nothing else about the experiment changes: same checkpoints, same acceptance
  suite, same isolation, same metrics. Only the agent is different, which is the
  whole point.

> **Using a non-Anthropic model?** The harness shells out to the `claude` CLI, so
> it drives Anthropic models directly. To test a model from another provider you
> would point the `claude` CLI at it via that CLI's own configuration (e.g. a
> gateway/proxy the CLI supports); the harness itself only ever calls
> `claude --model <id>`. Keep everything else identical so the *only* variable is the model.

---

## Full walkthrough

### 1. One-time setup

Follow [`README.md` → Prerequisites and One-time repo setup](../README.md#prerequisites).
In brief:

```bash
./setup.sh                      # clones both arm repos + creates the .venv
source .venv/bin/activate
python -m harness.run_experiment --config config.yaml --test-mode blind --dry-run
```

The dry run prints the branch names, the test mode, and now the **model** it will
use. Confirm the model line reads what you expect before spending tokens.

### 2. Smoke test (one cell, one checkpoint — a few dollars)

Prove the loop works with your model before committing to a full run:

```bash
python -m harness.run_experiment \
  --config config.yaml --test-mode blind \
  --model <your-model> --run-id <your-model>-smoke \
  --arm spring --chain 0 --max-checkpoints 1
```

### 3. A cheap real trial (1 chain per arm)

A single chain per arm already shows the shape of the two slopes (just without
tight confidence intervals. One chain is path-dependent, see the caveat below):

```bash
python -m harness.run_experiment \
  --config config.yaml --test-mode blind \
  --model <your-model> --run-id <your-model> \
  --chain 0
```

To keep a first trial cheaper still, add `--max-checkpoints 5`. You lose the 
checkpoints (where the arms diverge most, so it *understates*
the effect) but the run finishes in a fraction of the time.

### 4. The full run (for publishable CIs)

```bash
python -m harness.run_experiment \
  --config config.yaml --test-mode blind \
  --model <your-model> --run-id <your-model>
```

This runs all `chains` (default 10) for both arms. **Budget realistically:** the
back-half checkpoints re-run growing threshold tests at every later gate, so a
full chain averages several minutes per checkpoint. The maintainer's 20-chain
`claude-opus-4-8` run was roughly a week of wall-clock and on the order of
~US$1.5k in tokens (see [`AGENTS.md` → Gotchas](../AGENTS.md#gotchas--lessons-2026-08));
scale `chains` in `config.yaml` down for a cheaper run and report the CIs you got.

Optionally also run the optimistic condition (`--test-mode full`, where the agent
can see the accumulated regression suite while it works) to compare. A stronger
model is exactly where the two test modes might diverge.

### 5. Analyze

```bash
python -m harness.analyze --config config.yaml --run-id blind-<your-model>
```

> Note the `blind-` (or `full-`) prefix: the harness prepends the test mode to
> your `--run-id`, so `--run-id opus5` becomes run `blind-opus5`. The
> `run_id = ...` line printed at the start of the run tells you the exact id.

`analyze` recomputes every metric from the branches and writes
`results/<run_id>/analysis/` (a `summary.md`, tables, and PNG plots). Nothing is
read back from derived data. It is all rebuilt from the raw capture, so your
numbers are directly comparable to the maintainer's.

---

## What to compare

The thesis is about **where complexity lands**, not raw correctness (both arms
tend to stay similarly correct). Look at the **slopes** (`m`) with their 95%
bootstrap CIs for the decisive structural metrics:

| Metric | Thesis prediction | Your question |
|---|---|---|
| `impact_composite`, `impact_mutation` | Spring slope ≫ OfficeFloor, CIs disjoint | Do they stay disjoint with your model? |
| `entry_cc` | Spring handler climbs; OfficeFloor flat (~0) | Does your model keep the Spring front door thin? |
| `wmc_max` | Spring god-class accumulates | Does your model distribute instead? |
| `erosion_handler` | Spring handler erodes; OfficeFloor doesn't | Does the concentration signal survive? |

The headline result **holds** if the Spring−OfficeFloor structural slopes stay
positive with disjoint CIs; it **weakens** if a stronger model flattens the
Spring slope (e.g. by refactoring the controller each checkpoint). Either outcome
is a real, publishable finding. Report what you got, including CIs, not a single
chain.

**Keep it comparable:** change *only* `--model`. Leave `checkpoints.yaml`, the
acceptance suite, `config.yaml` (other than the model), and `--test-mode` as they
are, so the model is the sole difference between your run and the baseline.

---

## Share your results back

The branches are the single source of truth and carry raw data only, so sharing a
run means sharing its branches:

```bash
# push every branch this run created (one per arm × chain)
git -C <spring-repo>      push origin --all
git -C <officefloor-repo> push origin --all
```

Then open an issue on the
[experiment repository](https://github.com/officefloor/spring-petclinic-rest-long-degradation-test)
with:

- the **model id** you used (as recorded in `provenance.json`),
- your `results/<run_id>/analysis/summary.md`,
- how many `chains` you ran and any config you changed.

Anyone can re-derive every number from your pushed branches with
`python -m harness.analyze`, so the result is independently checkable. That is
the point.

---

## Caveats (read before drawing conclusions)

- **One chain is path-dependent.** A single chain is one random walk; use several
  chains and read the bootstrap CIs, not a single trajectory (see
  [`README.md` → Notes and honest limitations](../README.md#notes-and-honest-limitations)).
- **Only the model should vary.** If you also change checkpoints, prompts, or the
  suite, you are no longer measuring the model.
- **Watch for the auth-dead signature.** A turn that dies on an expired login can
  still write a capture record (`cost_usd=0`, 1 turn, empty commit). The harness
  waits and retries on a *classified* auth/limit stall, but scan your run for that
  signature before trusting a chain (see [`AGENTS.md` → Gotchas](../AGENTS.md#gotchas--lessons-2026-08)).
- **Cost/time scale with `chains` and depth.** Start small (smoke → 1 chain →
  full) so a misconfiguration is cheap to catch.

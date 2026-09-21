"""Analysis: phase-binned curves, degradation slopes with bootstrap CIs,
EvoScore, and Zero-Regression Rate. Emits PNG plots and a summary.md.

Headline statistic (SlopCodeBench): the degradation slope m = OLS slope of a
metric on checkpoint index, per arm. The thesis is confirmed if
  m_erosion(Spring) > 0 (CI excludes 0), m_erosion(OfficeFloor) ~ 0, and
  the Spring-minus-OfficeFloor slope CI excludes 0.

EvoScore (SWE-CI): gamma-weighted mean of a per-checkpoint success signal,
gamma >= 1 rewarding staying maintainable late.
"""

from __future__ import annotations

import argparse
import csv
import json
import bisect
import math
import os
import re
import shutil
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from typing import Optional

import numpy as np
import yaml

from . import class_shape, correctness, cumulative_impact, expand_path, git_out, metrics, parser_selftest
from .run_experiment import CSV_FIELDS, phase_for

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def _b(x):
    return str(x).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Re-derivation: the dataset is ALWAYS rebuilt from the checkpoint COMMITS plus
# the raw capture (the run persists nothing derived). This is what lets a metric
# added to metrics.compute_all be computed over OLD runs without re-invoking the
# agent — the expensive part (the commits + capture) is reused.
# ---------------------------------------------------------------------------

_BRANCH_RE = re.compile(r"^evolve/([^/]+)/([^/]+)/([^/]+)/chain(\d+)$")

# Fewest distinct events a validation statistic may rest on before it is reported
# as a number. Below this the correlation/median is one or two checkpoints wearing
# a confidence interval — the summary says so explicitly instead of printing it or
# silently dropping the row. Bites the rare-event outcomes (true_regressions) only.
MIN_EVENTS = 5


def _evolve_branches(cfg: dict, run_id: str | None = None):
    """Yield (repo, branch, arm, strategy, chain) across the arm repos.

    A branch is only accepted from a repo that `config.yaml` actually assigns to
    that branch's arm. The runner always writes an arm's chains into its own repo,
    so this changes nothing for a normal run — it guards the case where the arm
    repos share an upstream and a manual `git fetch` lands BOTH arms' branches in
    one of them (easy to do: `refs/heads/evolve/<run>/*` is not arm-scoped). Without
    the check every metric for the duplicated arm is computed twice, once per repo,
    and the extra rows are indistinguishable from real chains — the chain-cluster
    bootstrap then reports CIs on ~2x the true sample. Skips are announced, because
    a silently ignored branch and a silently duplicated one are both wrong.
    """
    arms_by_repo: dict[str, set[str]] = defaultdict(set)
    for arm_name, arm_cfg in cfg["arms"].items():
        arms_by_repo[arm_cfg["repo"]].add(arm_name)

    out, skipped = [], []
    for repo in sorted(arms_by_repo):
        refs = git_out(repo, ["for-each-ref", "--format=%(refname:short)",
                              "refs/heads/evolve"]).splitlines()
        for br in (r.strip() for r in refs if r.strip()):
            m = _BRANCH_RE.match(br)
            if not m:
                continue
            rid, strat, arm, chain = m.groups()
            if run_id and rid != run_id:
                continue
            if arm not in arms_by_repo[repo]:
                skipped.append((repo, br))
                continue
            out.append((repo, br, arm, strat, int(chain)))
    if skipped:
        print(f"  ({len(skipped)} evolve branch(es) skipped: arm does not match the "
              f"repo config.yaml assigns it — e.g. {skipped[0][1]} in {skipped[0][0]})")
    return out


def _latest_run_id(cfg: dict) -> str | None:
    ids = {_BRANCH_RE.match(br).group(1) for _, br, *_ in _evolve_branches(cfg)}
    return max(ids) if ids else None


def _read_blob(repo: str, ref: str, path: str) -> str | None:
    """Content of ``<ref>:<path>``, or None if the path is absent at that ref."""
    p = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def _read_json_blob(repo: str, ref: str, path: str) -> dict | None:
    """Parse ``<ref>:<path>`` as JSON, or None if absent/unparseable."""
    txt = _read_blob(repo, ref, path)
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


def _cp_commits(repo: str, branch: str) -> dict[int, str]:
    """checkpoint number -> AGENT commit sha, parsed from commit messages (fallback
    for runs without provenance). Prefers the two-commit format's 'cpNN agent ...'
    commit; falls back to the legacy single 'cpNN <id>' commit."""
    out = git_out(repo, ["log", "--format=%H %s", branch])
    agent_m: dict[int, str] = {}
    legacy_m: dict[int, str] = {}
    for line in out.splitlines():
        sha, _, subj = line.partition(" ")
        ma = re.match(r"cp0*(\d+) agent\b", subj)
        if ma:
            agent_m.setdefault(int(ma.group(1)), sha)
            continue
        ml = re.match(r"cp0*(\d+)\b", subj)
        if ml and " reset " not in f" {subj} ":
            legacy_m.setdefault(int(ml.group(1)), sha)
    return agent_m or legacy_m


def _read_captures(repo: str, branch: str) -> dict[int, dict]:
    """checkpoint -> capture record, from evolve-results/capture/cpNN.json on the
    branch (empty for pre-capture runs)."""
    caps: dict[int, dict] = {}
    ls = git_out(repo, ["ls-tree", "-r", "--name-only", branch, "evolve-results/capture/"])
    for path in ls.splitlines():
        mt = re.search(r"cp0*(\d+)\.json$", path)
        if not mt:
            continue
        rec = _read_json_blob(repo, branch, path)
        if rec is not None:
            caps[int(mt.group(1))] = rec
    return caps


def _read_provenance(repo: str, branch: str) -> dict:
    """The chain's provenance.json (base_commit + tool/agent versions), written up
    front in the manifest commit. The checkpoint->sha map is NOT here; it is derived
    from the per-checkpoint capture records. Empty for pre-provenance runs."""
    return _read_json_blob(repo, branch, "evolve-results/provenance.json") or {}


def _resolve_run_config(live_cfg: dict, run_id: str, tmp_dir: str) -> dict:
    """Config to DERIVE with: prefer the per-run snapshot committed at run time (so
    metrics match how the run was configured), falling back to the live config for
    runs recorded before snapshots existed. Repo filesystem paths always come from
    the live environment; only the metric-shaping fields (globs, thresholds,
    entry-handler regex, ast-grep rules) are taken from the snapshot."""
    branches = _evolve_branches(live_cfg, run_id)
    if not branches:
        return live_cfg
    repo, branch = branches[0][0], branches[0][1]
    snap = _read_blob(repo, branch, "evolve-results/config/config.yaml")
    if snap is None:
        print("  (no per-run config snapshot; deriving with the live config.yaml)")
        return live_cfg
    run_cfg = yaml.safe_load(snap)
    # Repos are filesystem locations — take them from the live environment (matched
    # by arm name), not from the snapshot.
    for name, arm in run_cfg.get("arms", {}).items():
        live_arm = live_cfg.get("arms", {}).get(name)
        arm["repo"] = live_arm["repo"] if live_arm else expand_path(arm.get("repo"), f"arms.{name}.repo")
        # A metric added AFTER a run needs config that run never recorded. Snapshot
        # values always win, but keys ABSENT from the snapshot are filled from the live
        # config so a new metric can still backfill — the harness's "adding a metric
        # applies it to every past run" promise. Each fill is logged, because the
        # failure mode is silent: `node_roots` was added 2026-08-23 and without this
        # OfficeFloor's node closure collapsed to its single entry node, reporting CC 8
        # instead of a 19-node pipeline — a number that looks perfectly valid.
        for key, value in (live_arm or {}).items():
            if key not in arm:
                arm[key] = value
                print(f"  ! arms.{name}.{key} absent from the run's config snapshot "
                      f"(metric added after the run); using the live value")
    # Extract the snapshotted ast-grep rules so Verbosity's pattern component
    # matches the run; if none were snapshotted, fall back to the live rules path.
    rel = "evolve-results/config/astgrep-rules"
    listing = git_out(repo, ["ls-tree", branch, rel]).strip()
    run_cfg.setdefault("tools", {})
    if listing:
        arch = subprocess.run(["git", "-C", repo, "archive", branch, rel], capture_output=True)
        if arch.returncode == 0:
            subprocess.run(["tar", "-x", "-C", tmp_dir], input=arch.stdout)
            run_cfg["tools"]["astgrep_rules"] = os.path.join(tmp_dir, rel)
    else:
        run_cfg["tools"]["astgrep_rules"] = live_cfg.get("tools", {}).get("astgrep_rules", "")

    # Same for the PMD ruleset, except it is a FILE (config/pmd-rules/<basename>) rather
    # than a directory. Three cases, in priority order:
    #   1. the run snapshotted a ruleset -> use it (it decided that run's verdicts);
    #   2. the snapshot names one but did not carry it (every run before the ruleset
    #      travelled) -> the recorded value is a CONFIG-RELATIVE string, and PMD runs
    #      with cwd=<arm worktree>, so using it verbatim makes PMD exit 1 with "Cannot
    #      resolve rule/ruleset reference" and smell detection not run at all;
    #   3. the snapshot predates PMD entirely -> fill from live, so a detector added
    #      after a run still backfills onto it (see the `pmd` note below).
    # 2 and 3 both resolve to the live, config-anchored path, so one fallback covers both.
    prel = "evolve-results/config/pmd-rules"
    plisting = git_out(repo, ["ls-tree", branch, prel]).strip()
    pmd_snap = ""
    if plisting:
        parch = subprocess.run(["git", "-C", repo, "archive", branch, prel], capture_output=True)
        if parch.returncode == 0:
            subprocess.run(["tar", "-x", "-C", tmp_dir], input=parch.stdout)
            pdir = os.path.join(tmp_dir, prel)
            files = sorted(f for f in os.listdir(pdir)) if os.path.isdir(pdir) else []
            if files:
                pmd_snap = os.path.join(pdir, files[0])
    if pmd_snap:
        run_cfg["tools"]["pmd_rules"] = pmd_snap
    else:
        live_pmd_rules = live_cfg.get("tools", {}).get("pmd_rules", "")
        if live_pmd_rules and live_pmd_rules != run_cfg["tools"].get("pmd_rules"):
            print(f"  tools.pmd_rules: snapshot "
                  f"{run_cfg['tools'].get('pmd_rules')!r} -> live {live_pmd_rules!r} "
                  f"(ruleset not carried by this run)")
        run_cfg["tools"]["pmd_rules"] = live_pmd_rules

    # Tool BINARIES are filesystem locations, like the arm repos above — where a
    # machine keeps jscpd/ast-grep says nothing about how the run was measured, and a
    # snapshot naming a binary this machine does not have makes the metric vanish
    # rather than fail: metrics.verbosity() falls back to whichever stack produced
    # output, so a missing ast-grep silently turns Verbosity into a clones-only
    # number. That is exactly what blind-202608100006 and blind-202609010045 did —
    # both snapshots pin `astgrep: "sg"`, absent here, so `verbosity_pattern_lines`
    # is empty for all 2400 rows. Take the LOCATIONS from live config; everything
    # that decides a verdict (astgrep_rules above, the jscpd_min_* thresholds) still
    # comes from the snapshot.
    #
    # `pmd` is filled from live the same way, and that DELIBERATELY changes the detector
    # for a pre-PMD run, because `tools.pmd` being truthy is what selects PMD over
    # ast-grep (quality_gate.review and metrics._pattern_lines branch on it together, so
    # gate and metric never disagree). Pinning each run to the detector it recorded was
    # tried and is WRONG here, for a reason only the archive shows: 6 of the 7 recorded
    # runs predate PMD, and 5 of those snapshot an `astgrep-rules/java-wasteful.yml` that
    # the PINNED ast-grep can no longer parse — it still contains `catch ($TYPE $E) { }`
    # and `$T $V = $E; return $V;`, multi-node patterns that were later deleted from the
    # live rules (see the header of that file). One unparseable rule aborts the whole
    # directory (exit 8), so pinning does not reproduce those runs' numbers; it yields NO
    # smell half at all, which is the silent-zero failure this function exists to avoid.
    # The 6th parses but matches 5 lines, all in unchanged upstream code. Backfilling
    # gives every run a detector that actually fires on Java (23 lines on spring, 14 on
    # officefloor) and makes the runs mutually comparable. Re-check this if the ast-grep
    # rules are ever repaired retroactively.
    for key in ("jscpd", "astgrep", "pmd"):
        live_val = live_cfg.get("tools", {}).get(key)
        if live_val and run_cfg["tools"].get(key) != live_val:
            print(f"  tools.{key}: snapshot {run_cfg['tools'].get(key)!r} -> "
                  f"live {live_val!r} (binary location, not measurement config)")
            run_cfg["tools"][key] = live_val

    # A tool key ABSENT from the snapshot is filled from live, exactly as `arms.*`
    # keys are above and for the same reason: a metric added after a run needs config
    # that run could never have recorded, and the harness's promise is that adding a
    # metric backfills onto every past run. Without this the placement suite's
    # `pmd_metrics_rules` and `ck` were missing from every snapshot, both readers
    # returned None, and ALL the PMD/CK columns came back blank on re-analysis --
    # the silent-zero failure this function exists to prevent, one level up.
    # Recorded values still win; only gaps are filled, and every fill is logged.
    for key, live_val in (live_cfg.get("tools", {}) or {}).items():
        if key not in run_cfg["tools"] and live_val not in (None, ""):
            run_cfg["tools"][key] = live_val
            print(f"  ! tools.{key} absent from the run's config snapshot "
                  f"(metric added after the run); using the live value")

    print(f"  using per-run config snapshot from {branch}")
    return run_cfg


def _heartbeat_val(row: dict, field: str) -> str:
    """One metric as the progress heartbeat shows it.

    `-` means the field is BLANK (the metric did not run), never a real 0 -- the
    "did not run reads as found nothing" confusion this harness has hit before.
    Display only; nothing is derived from this.
    """
    v = row.get(field, "")
    return "-" if v is None or v == "" else str(v)


def recompute_rows(cfg: dict, run_id: str, work_root: str,
                   exclude: str | None = None,
                   chains: set[int] | None = None) -> list[dict]:
    """Rebuild every checkpoint row for `run_id` from its commits + capture.

    Structural metrics come from metrics.compute_all over a detached worktree at
    each checkpoint commit; correctness + agent/probe ephemera come from the raw
    capture. Emits rows keyed identically to run_experiment's CSV_FIELDS, so the
    rest of this module (slopes, plots, EvoScore, ...) is unchanged."""
    rows: list[dict] = []
    rc_root = os.path.join(work_root, "recompute")
    os.makedirs(rc_root, exist_ok=True)
    for repo, branch, arm, strat, chain in _evolve_branches(cfg, run_id):
        arm_cfg = cfg["arms"].get(arm)
        if not arm_cfg:
            continue
        if chains is not None and int(chain) not in chains:
            continue
        caps = _read_captures(repo, branch)
        prov = _read_provenance(repo, branch)

        # Checkpoint list + per-checkpoint commit SHA. Prefer the per-checkpoint
        # capture records: each carries its OWN `commit_sha` ("" for a no-op turn
        # where the agent changed nothing -> no cpNN commit), so the map lists EVERY
        # checkpoint including no-ops, which parsing commit messages would silently
        # drop. Fall back to the legacy provenance map (older runs stored it there),
        # then to commit messages for pre-capture runs.
        if caps:
            shas = {k: (rec.get("commit_sha") or "") for k, rec in caps.items()}
        elif prov.get("checkpoint_shas"):
            shas = {int(k): (v or "") for k, v in prov["checkpoint_shas"].items()}
        else:
            shas = _cp_commits(repo, branch)
        base_commit = prov.get("base_commit") or ""
        if not shas:
            continue
        ks = sorted(shas)
        n = len(ks)
        if not base_commit:
            first_real = next((shas[k] for k in ks if shas[k]), "")
            base_commit = git_out(repo, ["rev-parse", f"{first_real}~1"]).strip() if first_real else ""
        if not base_commit:
            print(f"    ! {branch}: cannot determine base commit; skipping")
            continue

        prior_passing: set[str] = set()
        prev_tree = base_commit   # tree of the previous checkpoint (base before cp01)
        n_noop = 0
        n_invalid = 0             # gates that aborted -> correctness is missing, not failed
        pending_mutated: list[int] = []   # `mutates` of skipped checkpoints, owed to the next scored one
        subprocess.run(["git", "-C", repo, "worktree", "prune"], capture_output=True, text=True)
        t_chain = time.time()
        for i_cp, k in enumerate(ks, 1):
            real = shas.get(k) or ""     # AGENT commit sha; "" => no-op checkpoint
            tree = real or prev_tree     # a no-op reuses the previous checkpoint's tree
            # The agent commit's parent IS the previous reset commit, so diffing the
            # agent commit against its own parent yields the pure agent delta. A
            # no-op diffs the previous tree against itself (zero change).
            prev = f"{real}~1" if real else prev_tree
            if not real:
                n_noop += 1
            cap = caps.get(k) or {}
            row = {f: "" for f in CSV_FIELDS}
            row.update({
                "run_id": run_id, "branch": branch, "arm": arm, "strategy": strat,
                "chain": chain, "checkpoint": k,
                "checkpoint_id": cap.get("checkpoint_id", ""),
                "phase": cap.get("phase") or phase_for(k, n),
            })

            # DERIVE: structural metrics from the checkpoint tree (materialised in a
            # throwaway detached worktree — cheap; no build/agent involved). A no-op
            # reuses the previous tree, so its blast radius vs the previous
            # checkpoint is zero — exactly right.
            wt = os.path.join(rc_root, f"{arm}_{strat}_c{chain}_cp{k:02d}")
            shutil.rmtree(wt, ignore_errors=True)
            add = subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", wt, tree],
                                 capture_output=True, text=True)
            try:
                if add.returncode == 0:
                    mrow, _ = metrics.compute_all(wt, arm_cfg, cfg["tools"],
                                                  base_commit, prev, "HEAD", exclude=exclude)
                    row.update(mrow)
                else:
                    print(f"    ! worktree add failed for {branch} cp{k:02d}: "
                          f"{add.stderr.strip()[:120]}")
            finally:
                subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", wt],
                               capture_output=True, text=True)
                shutil.rmtree(wt, ignore_errors=True)
            prev_tree = tree

            # Heartbeat, one line per CHECKPOINT (~5s). Deliberately not per-metric:
            # ~93% of a checkpoint is three external tool launches (PMD x2, CK), so a
            # per-metric line would be ~20x the volume while idling on exactly the
            # three steps that take the time.
            el = time.time() - t_chain
            eta = (el / i_cp) * (n - i_cp)
            print(f"      cp{k:02d} {i_cp:>3}/{n}  {el / i_cp:4.1f}s/cp"
                  f"  eta {eta / 60:4.1f}m"
                  f"  erosion={_heartbeat_val(row, 'erosion')}"
                  f"  loc={_heartbeat_val(row, 'java_loc')}", flush=True)

            # DERIVE: correctness from the RAW captured test-result map, via the
            # same outcome->row mapping the runner uses. build_ok comes from the
            # capture (a build failure leaves results empty, which score_results
            # can't otherwise distinguish).
            tests = cap.get("tests") or {}
            results = tests.get("results")
            if results is not None:
                outcome = correctness.score_results(results, k)
                outcome.build_ok = tests.get("build_ok", True)
                # An ABORTED gate carries no verdict. Runs recorded after the 2026-08
                # fix say so outright; older captures are recognised by the signature
                # the crash leaves behind — the build compiled, yet not one test
                # reported. Scoring that would read the missing results as "every
                # prior rule broke" (this is exactly how a Surefire fork crash once
                # showed up as 143 regressions on full-202608102319). A build FAILURE
                # is not this case: it leaves build_ok False and stays scored, because
                # the agent breaking compilation is a real verdict.
                outcome.gate_invalid = bool(tests.get("gate_invalid")) or (
                    outcome.build_ok and not results)
                outcome.gate_attempts = tests.get("gate_attempts") or 0
                row["checkpoint_type"] = cap.get("type", "additive")
                # Across a hole, `prior_passing` is the set measured BEFORE the invalid
                # checkpoint(s), so the next scored diff spans them — and it must inherit
                # their `mutates` exemptions too. Without this a MUTATIVE checkpoint whose
                # gate crashed launders its intended rule changes into the next
                # checkpoint's true-regression count (officefloor chain4 cp52 crashed →
                # cp53 read 7 phantom "true" regressions that were cp52's mandated
                # mutation). Empty in the normal case, so scoring is unchanged.
                mutated = [int(m) for m in (cap.get("mutates") or [])] + pending_mutated
                row.update(correctness.outcome_row(outcome, prior_passing, mutated))
                if outcome.gate_invalid:
                    n_invalid += 1
                    row["notes"] = (tests.get("error") or "gate produced no results")[:200]
                    pending_mutated = mutated          # carried with prior_passing
                else:
                    prior_passing = outcome.passing    # carried forward across a hole
                    pending_mutated = []

            # Ephemera straight from capture (irreproducible; never recomputed).
            ag = cap.get("agent") or {}
            if ag:
                row.update({
                    "agent_ok": ag.get("ok"), "cost_usd": ag.get("cost_usd"),
                    "input_tokens": ag.get("input_tokens"),
                    "cache_read_tokens": ag.get("cache_read_tokens"),
                    "output_tokens": ag.get("output_tokens"),
                    "num_turns": ag.get("num_turns"),
                    "duration_ms": ag.get("duration_ms"),
                    "duration_api_ms": ag.get("duration_api_ms"),
                })
            probe = cap.get("probe")
            if probe:
                pr_recall = probe.get("probe_recall")
                row.update({
                    "probe_cost_usd": probe.get("probe_cost_usd"),
                    "probe_input_tokens": probe.get("probe_input_tokens"),
                    "probe_cache_read_tokens": probe.get("probe_cache_read_tokens"),
                    "probe_recall": ("" if pr_recall is None else round(pr_recall, 3)),
                })
            row["pinned_touched"] = ",".join(cap.get("pinned_touched") or [])
            row["acceptance_touched"] = ",".join(cap.get("acceptance_touched") or [])

            # impact_gated pipeline ephemera (irreproducible: the refactor agent turns).
            # The accepted change's grade is the LAST 'implement' attempt's grade; refactor
            # cost/tokens sum every 'refactor' attempt. Blank for ungated strategies.
            ig = cap.get("impact_gate")
            if ig:
                impls = [a for a in ig.get("attempts", []) if a.get("kind") == "implement"]
                refs = [a for a in ig.get("attempts", []) if a.get("kind") == "refactor"]
                r_cost = sum((a.get("agent") or {}).get("cost_usd") or 0 for a in refs)
                r_tok = sum(((a.get("agent") or {}).get("input_tokens") or 0)
                            + ((a.get("agent") or {}).get("output_tokens") or 0) for a in refs)
                # design-B quality gate: review turns + cost across ALL refactors; the pass/
                # finding counts are the LAST refactor's (the one that decided the checkpoint).
                q_turns = [t for a in refs for t in (a.get("quality_turns") or [])]
                q_cost = sum((t.get("cost_usd") or 0) for t in q_turns)
                last_q = (refs[-1].get("quality") if refs else None) or {}
                row.update({
                    "ig_enforcement": ig.get("enforcement"),
                    "ig_refactors": ig.get("refactors", len(refs)),
                    "ig_passed": ig.get("passed"),
                    "ig_stopped": ig.get("stopped"),
                    "ig_stop_reason": ig.get("stop_reason"),
                    # accepted (last implement) vs direct (first implement, pre-refactor). Their
                    # gap is the one-refactor cohesion effect the advisory condition measures.
                    "ig_grade": (impls[-1].get("grade") if impls else None),
                    "ig_impact": (impls[-1].get("impact") if impls else None),
                    "ig_grade_first": (impls[0].get("grade") if impls else None),
                    "ig_impact_first": (impls[0].get("impact") if impls else None),
                    "ig_refactor_cost_usd": round(r_cost, 4),
                    "ig_refactor_tokens": r_tok,
                    "ig_quality_review_turns": len(q_turns),
                    "ig_quality_passed": last_q.get("passed"),
                    "ig_quality_clone_lines": last_q.get("clone_finding_lines"),
                    "ig_quality_smell_lines": last_q.get("smell_finding_lines"),
                    "ig_quality_cost_usd": round(q_cost, 4),
                })
            rows.append(row)
        print(f"  recomputed {branch}: {n} checkpoints"
              + (f" ({n_noop} no-op)" if n_noop else "")
              + (f"  ! {n_invalid} INVALID GATE(S) — correctness excluded" if n_invalid else "")
              + ("" if caps else "  (no capture — structural metrics only)"))
    return rows


def group_key(r: dict) -> tuple[str, str]:
    return (r["arm"], r["strategy"])


def series_by_chain(rows: list[dict], field: str) -> dict[int, list[tuple[int, float]]]:
    """chain -> [(checkpoint, value)] sorted, dropping NaNs.

    Uses .get, not [], on purpose. A checkpoint whose `git worktree add` failed keeps
    its correctness fields but carries NO structural columns at all, and indexing died
    on the first such row — throwing away the whole recompute (~15 min) over one bad
    checkpoint in 1200, at the very end, after all the expensive work. A missing column
    is the same thing as an unmeasurable one: drop that point and fit the slope on the
    rest, exactly as a NaN is dropped. `metrics_missing` in the summary counts them, so
    a run that lost many checkpoints this way cannot look like a clean one.
    """
    out: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for r in rows:
        v = _f(r.get(field))
        if not math.isnan(v):
            out[int(r["chain"])].append((int(r["checkpoint"]), v))
    for c in out:
        out[c].sort()
    return out


def ols_slope(xs: np.ndarray, ys: np.ndarray) -> float:
    if len(xs) < 2:
        return math.nan
    return float(np.polyfit(xs, ys, 1)[0])


def _bucket_by_checkpoint(chain_series: dict[int, list[tuple[int, float]]],
                          sample: list[int] | None = None) -> dict[int, list[float]]:
    """checkpoint -> [value across the selected chains]. `sample` (chain keys, with
    repeats allowed for a bootstrap replicate) selects/weights which chains; default
    = each chain once. The shared aggregation for the mean curve and the plots."""
    keys = list(chain_series) if sample is None else sample
    acc: dict[int, list[float]] = defaultdict(list)
    for c in keys:
        for k, v in chain_series[c]:
            acc[k].append(v)
    return acc


def bootstrap_slope(chain_series: dict[int, list[tuple[int, float]]],
                    n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Mean-curve slope with a bootstrap CI over chains.

    Each replicate resamples chains with replacement, averages the value at each
    checkpoint across the resampled chains, and fits a slope to that mean curve.
    Returns (point_estimate, ci_lo, ci_hi) at 95%.
    """
    chains = list(chain_series.keys())
    if not chains:
        return (math.nan, math.nan, math.nan)

    def mean_curve(sample: list[int]) -> tuple[np.ndarray, np.ndarray]:
        acc = _bucket_by_checkpoint(chain_series, sample)
        ks = sorted(acc)
        return np.array(ks, dtype=float), np.array([np.mean(acc[k]) for k in ks])

    xs, ys = mean_curve(chains)
    point = ols_slope(xs, ys)

    rng = np.random.default_rng(seed)
    slopes = []
    for _ in range(n_boot):
        sample = list(rng.choice(chains, size=len(chains), replace=True))
        bx, by = mean_curve(sample)
        s = ols_slope(bx, by)
        if not math.isnan(s):
            slopes.append(s)
    if not slopes:
        return (point, math.nan, math.nan)
    lo, hi = np.percentile(slopes, [2.5, 97.5])
    return (point, float(lo), float(hi))


def _mean_curve_slope(chain_series: dict[int, list[tuple[int, float]]],
                      sample: list[int]) -> float:
    """Slope of the checkpoint-averaged curve over the given (possibly resampled) chains."""
    acc = _bucket_by_checkpoint(chain_series, sample)
    ks = sorted(acc)
    if len(ks) < 2:
        return math.nan
    return ols_slope(np.array(ks, dtype=float), np.array([np.mean(acc[k]) for k in ks]))


def bootstrap_diff_slope(rows_a: list[dict], rows_b: list[dict], field: str,
                         n_boot: int = 2000, seed: int = 0
                         ) -> tuple[float, float, float, list[float]]:
    """Bootstrap CI for slope(A) − slope(B): the PAIRED test the thesis needs.

    Comparing each arm's slope CI to zero separately is not the same as testing that
    the two arms differ; this resamples chains within each arm independently and takes
    the slope difference per replicate. A returned CI that excludes 0 means the two
    arms genuinely degrade at different rates on this metric.
    """
    sa, sb = series_by_chain(rows_a, field), series_by_chain(rows_b, field)
    if not sa or not sb:
        return (math.nan, math.nan, math.nan, [])
    ka, kb = list(sa), list(sb)
    point = _mean_curve_slope(sa, ka) - _mean_curve_slope(sb, kb)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        da = _mean_curve_slope(sa, list(rng.choice(ka, len(ka), replace=True)))
        db = _mean_curve_slope(sb, list(rng.choice(kb, len(kb), replace=True)))
        if not (math.isnan(da) or math.isnan(db)):
            diffs.append(da - db)
    if not diffs:
        return (point, math.nan, math.nan, [])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return (point, float(lo), float(hi), diffs)


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Tie-averaged ranks (scipy-free, for Spearman)."""
    a = np.asarray(a, dtype=float)
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1)
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, ranks)
    return (sums / cnt)[inv]


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return math.nan
    rx, ry = _rankdata(x), _rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return math.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def _informative(vals: list[float]) -> int:
    """Observations that differ from the series' most common value.

    A near-constant series (e.g. `true_regressions`, zero at all but one of 599
    checkpoints once the crashed gates are excluded) can still yield a ρ with a
    bootstrap CI that excludes zero, because every resample carries the same lone
    event. The number reads as a construct-validity result and is an artefact of
    one point. Continuous outcomes (cost, tokens, time) are untied, so this counts
    ~n for them and only bites the degenerate case."""
    if not vals:
        return 0
    counts = Counter(vals)
    return len(vals) - counts.most_common(1)[0][1]


def spearman_ci(rows: list[dict], xf: str, yf: str,
                n_boot: int = 1000, seed: int = 0) -> tuple[float, float, float, int, int]:
    """Spearman ρ(xf, yf) over checkpoints with a chain-cluster bootstrap CI.

    Chains are the resampling unit (checkpoints within a chain are not independent).
    Returns (rho, ci_lo, ci_hi, n, k) where k is `_informative` on the y series —
    the caller must refuse to report a ρ built on too few distinct events rather
    than dropping the row silently."""
    by_chain: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        xv, yv = _f(r.get(xf, "")), _f(r.get(yf, ""))
        if not (math.isnan(xv) or math.isnan(yv)):
            by_chain[int(r["chain"])].append((xv, yv))
    chains = [c for c in by_chain if by_chain[c]]
    pts = [p for c in chains for p in by_chain[c]]
    n = len(pts)
    k = _informative([p[1] for p in pts])
    if n < 5 or k < MIN_EVENTS:
        return (math.nan, math.nan, math.nan, n, k)
    rho = _spearman(np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        sample = rng.choice(chains, len(chains), replace=True)
        pp = [p for c in sample for p in by_chain[c]]
        if len(pp) >= 5:
            b = _spearman(np.array([p[0] for p in pp]), np.array([p[1] for p in pp]))
            if not math.isnan(b):
                boots.append(b)
    if not boots:
        return (rho, math.nan, math.nan, n, k)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (rho, float(lo), float(hi), n, k)


def phase_means(rows: list[dict], field: str):
    order = ["Start", "Early", "Mid", "Late", "Final"]
    acc = defaultdict(list)
    for r in rows:
        v = _f(r.get(field))   # .get: see series_by_chain — a checkpoint whose
                               # worktree failed has no structural columns at all
        if not math.isnan(v):
            acc[r["phase"]].append(v)
    return order, [float(np.mean(acc[p])) if acc[p] else math.nan for p in order]


def evoscore(rows: list[dict], gamma: float) -> float:
    """gamma-weighted mean of the 0/1 strict-pass signal over a chain, averaged
    across chains (later checkpoints discounted by gamma**i)."""
    per_chain = defaultdict(list)
    for r in scored(rows):
        val = 1.0 if _b(r["strict_pass"]) else 0.0
        per_chain[int(r["chain"])].append((int(r["checkpoint"]), val))
    scores = []
    for c, pairs in per_chain.items():
        pairs.sort()
        num = sum(gamma ** i * v for i, (_, v) in enumerate(pairs))
        den = sum(gamma ** i for i, _ in enumerate(pairs))
        if den > 0:
            scores.append(num / den)
    return float(np.mean(scores)) if scores else math.nan


def scored(rows: list[dict]) -> list[dict]:
    """Rows whose gate returned an actual verdict. A checkpoint whose gate ABORTED
    (`gate_invalid`, e.g. a Surefire fork crash) has blank correctness fields, and a
    blank read as a number is 0 and as a boolean is False — i.e. silently a perfect
    score on regressions and a failure on strict_pass. Every correctness aggregate
    therefore drops these rows outright; their STRUCTURAL metrics are untouched by
    the crash and stay in the slope/plot machinery."""
    return [r for r in rows if not _b(r.get("gate_invalid"))]


def zero_regression_rate(rows: list[dict], field: str = "regressions") -> float:
    per_chain = defaultdict(int)
    seen = set()
    for r in scored(rows):
        c = int(r["chain"])
        seen.add(c)
        per_chain[c] += int(_f(r.get(field)) or 0)
    if not seen:
        return math.nan
    clean = sum(1 for c in seen if per_chain[c] == 0)
    return clean / len(seen)


def regression_summary(rows: list[dict]) -> dict:
    """Totals for the intended-vs-true regression split, plus the count of mutative
    checkpoints (so a reader can see how much cross-cutting pressure the run had)."""
    graded = scored(rows)
    total = sum(int(_f(r.get("regressions")) or 0) for r in graded)
    true = sum(int(_f(r.get("true_regressions")) or 0) for r in graded)
    n_mut = sum(1 for r in graded if str(r.get("checkpoint_type", "")).strip() == "mutative")
    return {"total": total, "true": true, "intended": total - true, "mutative_cps": n_mut,
            "invalid_gates": len(rows) - len(graded)}


METRICS_TO_PLOT = [
    ("erosion", "Structural erosion — whole app (SlopCodeBench Eq.3)"),
    ("erosion_scoped", "Structural erosion — touched-file subsystem"),
    ("erosion_handler", "Structural erosion — entry-handler class only (concentration signal)"),
    ("verbosity", "Verbosity (SlopCodeBench Eq.4)"),
    ("cost_usd", "Cost per checkpoint (USD)"),
    ("duration_api_ms", "API time per checkpoint (ms, model inference)"),
    ("cache_read_tokens", "Cache-read tokens (comprehension proxy)"),
    ("hotspot_cc", "Hotspot cyclomatic complexity"),
    ("fn_nloc_max", "Max composed-function size (OfficeFloor)"),
    ("existing_fns_modified", "Blast radius — pre-existing functions modified per rule"),
    ("files_created", "New production files created per rule"),
    ("wmc_max", "God-class — max Weighted Methods per Class (WMC)"),
    ("wmc_handler", "God-class, handler class only — WMC of the same ROLE in both arms"),
    ("node_cc_median", "Per-node comprehension load — CC reachable from a typical handling node"),
    ("node_cc_max", "Per-node comprehension load — worst node"),
    ("node_path_cc", "Whole handling path — CC reachable from ALL nodes (relocation-proof total)"),
    ("entry_cc", "Entry-handler cyclomatic complexity (does the front door bloat)"),
    ("packages_touched", "Change spread — packages touched per rule"),
    ("reedit_rate", "Temporal coupling — share of rewritten lines from prior rules"),
    ("impact_mutation", "Impact — context-weighted mutation of existing functions"),
    ("impact_godclass", "Impact — context-weighted new-function additions"),
    ("impact_composite", "Impact — max(WMC_other,1)·CC·max(1,Δlines)·files per rule"),
]

# The three impact sub-scores, each reported in three slices: all checkpoints (the
# base field), additive-only (`_add`), and mutative-only (`_mut`). The derived view
# columns are synthesised in main() off the base fields (blank on the other type).
IMPACT_BASE_FIELDS = ["impact_mutation", "impact_godclass", "impact_composite"]
_IMPACT_LABEL = {"impact_mutation": "mutation of existing functions",
                 "impact_godclass": "new-function additions",
                 "impact_composite": "composite (max(WMC_other,1)·CC·max(1,Δlines)·files)"}
for _fld in IMPACT_BASE_FIELDS:
    METRICS_TO_PLOT.append((_fld + "_add", f"Impact ({_IMPACT_LABEL[_fld]}) — ADDITIVE checkpoints only"))
    METRICS_TO_PLOT.append((_fld + "_mut", f"Impact ({_IMPACT_LABEL[_fld]}) — MUTATIVE checkpoints only"))

# ---------------------------------------------------------------------------
# PLACEMENT metrics (harness/placement.py). Grouped by the CLAIM each one tests,
# because the three groups have OPPOSITE predictions and a table that mixes them
# reads as noise:
#
#   AMOUNT     - Tesler's conservation. Prediction: NO arm difference. Four
#                independent operationalisations (cyclomatic, cognitive, NPath,
#                Halstead volume); if they all agree the arms carry the same
#                complexity, the conservation claim does not rest on McCabe alone.
#   TAX        - Brooks' accidental complexity. Prediction: the DISTRIBUTED arm is
#                WORSE. These are expected counter-signals, listed so the cost of
#                distribution is published rather than discovered by a referee.
#   PLACEMENT  - the actual thesis. Prediction: the concentrated arm is worse.
#
# `analysis_expectation` (below) records the predicted direction per metric so the
# summary can flag every measure that comes out AGAINST the hypothesis.
PLACEMENT_METRICS = [
    # --- AMOUNT: expected to show NO between-arm difference -------------------
    ("total_cc", "Total cyclomatic complexity, whole app (Tesler conservation)"),
    ("pmd_cognitive_total", "Total cognitive complexity (Campbell/SonarSource)"),
    ("pmd_npath_total", "Total NPath complexity (Nejmeh 1988)"),
    ("halstead_volume", "Total Halstead volume (Halstead 1977)"),
    ("halstead_effort", "Total Halstead effort"),
    ("ck_wmc_total", "Total WMC across classes (CK — independent parser cross-check)"),
    ("total_fns", "Function count"),
    ("total_files", "File count"),
    ("total_packages", "Package count"),
    ("mi_mean", "Maintainability Index, mean over files (Coleman 1994)"),
    ("mi_min", "Maintainability Index, worst file"),
    # --- TAX: expected to favour the CONCENTRATED arm ------------------------
    ("indirection_median", "Indirection — median call hops from a handling node"),
    ("indirection_max", "Indirection — deepest call chain"),
    ("indirection_deep_share", "Indirection — share of reached methods >2 hops away"),
    ("ck_cbo_mean", "Coupling between objects, mean (C&K)"),
    ("ck_cbo_max", "Coupling between objects, worst class"),
    ("ck_fanout_mean", "Fan-out, mean"),
    ("pmd_demeter_violations", "Law of Demeter violations (Lieberherr 1989)"),
    # --- PLACEMENT: the thesis -----------------------------------------------
    ("ccdist_file_hhi", "CC concentration across files (HHI)"),
    ("ccdist_file_top1", "Share of all CC in the heaviest file"),
    ("ccdist_file_top5", "Share of all CC in the heaviest five files"),
    ("ccdist_file_gini", "CC inequality across files (Gini — scale-free)"),
    ("ccdist_file_hnorm", "CC spread across files (normalised entropy)"),
    ("ccdist_fn_gini", "CC inequality across functions (Gini)"),
    ("ccdist_fn_hhi", "CC concentration across functions (HHI)"),
    ("ccdist_pkg_hhi", "CC concentration across packages (HHI)"),
    ("wmcdist_class_hhi", "WMC concentration across classes (HHI)"),
    ("cogdist_fn_hhi", "Cognitive-complexity concentration across functions (HHI)"),
    ("voldist_file_hhi", "Halstead-volume concentration across files (HHI)"),
    ("change_entropy_norm", "Change spread THIS rule (Hassan 2009, normalised)"),
    ("change_top1", "Share of this rule's changed lines in one file"),
    ("cum_change_entropy_norm", "Change spread base→here, cumulative (Hassan 2009)"),
    ("cum_change_top1", "Share of ALL change so far in one file"),
    ("cum_change_top5", "Share of ALL change so far in five files"),
    ("cum_change_hhi", "Cumulative change concentration (HHI)"),
    ("cum_change_files", "Files carrying the change so far"),
    ("propagation_cost", "Propagation cost (MacCormack 2006) — n² normalised, see caveat"),
    ("propagation_fanout_median", "Files reachable from a typical file (NOT normalised)"),
    ("ck_lcom_mean", "Lack of cohesion LCOM, mean (C&K 1994) — low is cohesive"),
    ("ck_lcom_max", "LCOM, worst class"),
    ("ck_lcom_star_mean", "LCOM* mean (Henderson-Sellers 1996)"),
    ("ck_tcc_mean", "Tight class cohesion, mean (Bieman & Kang 1995) — HIGH is cohesive"),
    ("ck_lcc_mean", "Loose class cohesion, mean"),
    ("ck_rfc_mean", "Response for a class, mean (C&K)"),
    ("ck_rfc_max", "Response for a class, worst"),
    ("ck_dit_mean", "Depth of inheritance tree, mean (C&K)"),
    ("ck_handler_lcom", "LCOM of the HANDLER class (like-for-like role)"),
    ("ck_handler_tcc", "TCC of the handler class"),
    ("ck_handler_rfc", "RFC of the handler class"),
    ("ck_handler_cbo", "CBO of the handler class"),
    ("ck_handler_wmc", "WMC of the handler class (CK cross-check on wmc_handler)"),
    # --- published DETECTOR verdicts (binary, externally defined thresholds) ---
    ("pmd_god_classes", "God classes detected (Lanza & Marinescu thresholds, via PMD)"),
    ("pmd_handler_is_god_class", "Handler class trips the published God-Class detector"),
    ("pmd_data_classes", "Data classes detected"),
    # --- VALIDITY: does the call graph still see the code? --------------------
    ("container_total", "Framework-dispatched classes (call-graph escape counter)"),
]
METRICS_TO_PLOT += PLACEMENT_METRICS

# Which CLAIM each metric belongs to, for the outcome-correlation summary. The whole
# point of that analysis is that the three groups should behave DIFFERENTLY against
# maintenance outcomes: if amount predicts nothing and placement predicts cost and
# breakage, Tesler and Brooks are tested rather than assumed.
METRIC_GROUP = {}
for _f2, _lab in PLACEMENT_METRICS:
    METRIC_GROUP[_f2] = "amount"
for _f2 in ("total_files", "total_packages", "indirection_median", "indirection_max",
            "indirection_deep_share", "ck_cbo_mean", "ck_cbo_max", "ck_fanout_mean",
            "pmd_demeter_violations", "files_created", "cum_change_files"):
    METRIC_GROUP[_f2] = "tax"
for _f2 in [k for k in METRIC_GROUP if k.startswith(
        ("ccdist_", "wmcdist_", "cogdist_", "voldist_", "change_", "cum_change_",
         "propagation_", "ck_lcom", "ck_tcc", "ck_lcc", "ck_rfc", "ck_handler_",
         "pmd_god", "pmd_data", "pmd_handler"))]:
    METRIC_GROUP[_f2] = "placement"
for _f2 in ("wmc_handler", "wmc_max", "entry_cc", "node_cc_median", "node_cc_max",
            "erosion_handler", "impact_composite", "impact_mutation", "reedit_rate",
            "existing_fns_modified", "packages_touched"):
    METRIC_GROUP[_f2] = "placement"
for _f2 in ("total_cc", "pmd_cognitive_total", "pmd_npath_total", "halstead_volume",
            "halstead_effort", "ck_wmc_total", "total_fns", "node_path_cc", "erosion",
            "java_loc", "mi_mean"):
    METRIC_GROUP[_f2] = "amount"


# ---------------------------------------------------------------------------
# Pre-declared expectations, so a metric that contradicts the thesis is REPORTED
# rather than found by a referee.
# ---------------------------------------------------------------------------
#
# Value = the sign of (concentrated arm - distributed arm) that would SUPPORT the
# hypothesis, where the hypothesis is: both arms carry the same complexity (amount),
# the distributed arm pays a navigational tax (tax), and the concentrated arm packs
# that complexity into fewer, larger, less cohesive units (placement).
#
#   +1  supporting if the CONCENTRATED arm scores HIGHER
#   -1  supporting if the DISTRIBUTED arm scores HIGHER  (includes the expected tax)
#    0  supporting if the arms DO NOT DIFFER             (the conservation claim)
#   omitted entirely = no prediction on record; never flagged either way
#
# The second element is WHICH DIMENSION the prediction is about, and getting it wrong
# manufactures false counter-signals: `files_created` is a LEVEL claim (the pipeline arm
# creates 63 files per chain against 10) whose SLOPE runs the other way, because the
# pipeline arm front-loads its files and its per-rule rate then declines faster. A
# state claim must be tested on the final-phase level, a degradation claim on the slope.
#   "level" - the end state of the codebase (default; most structural descriptions)
#   "slope" - the RATE of change per checkpoint (degradation claims)
#   "both"  - must hold on both (conservation: same total AND not diverging)
#
# Declaring these BEFORE reading the run is what makes the counter-signal section
# meaningful. Do not edit an entry to match an observed result -- add a note to
# AGENTS.md and leave the prediction wrong on the record.
METRIC_EXPECTATION = {
    # --- AMOUNT: conservation (Tesler). Same total AND not diverging. ---
    "total_cc": (0, "both"), "pmd_cognitive_total": (0, "both"),
    "pmd_npath_total": (0, "both"), "halstead_volume": (0, "both"),
    "halstead_effort": (0, "both"), "ck_wmc_total": (0, "both"),
    "total_fns": (0, "level"),
    # --- the distribution tax (Brooks' accidental complexity): STATE claims ---
    "total_files": (-1, "level"), "total_packages": (-1, "level"),
    "indirection_median": (-1, "level"), "indirection_max": (-1, "level"),
    "indirection_deep_share": (-1, "level"),
    "ck_cbo_mean": (-1, "level"), "ck_cbo_max": (-1, "level"),
    "ck_fanout_mean": (-1, "level"), "pmd_demeter_violations": (-1, "level"),
    "files_created": (-1, "level"), "cum_change_files": (-1, "level"),
    "mi_mean": (-1, "level"), "mi_min": (-1, "level"),
    # --- PLACEMENT: concentration. Higher in the end state AND growing faster. ---
    "ccdist_file_hhi": (+1, "both"), "ccdist_file_top1": (+1, "both"),
    "ccdist_file_top5": (+1, "both"), "ccdist_file_gini": (+1, "level"),
    "ccdist_file_hnorm": (-1, "both"),
    "ccdist_pkg_hhi": (+1, "level"), "wmcdist_class_hhi": (+1, "both"),
    "cogdist_fn_hhi": (+1, "level"), "voldist_file_hhi": (+1, "level"),
    # the god class is many ORDINARY methods packed together, not giant methods,
    # so no per-FUNCTION difference is predicted on either dimension
    "ccdist_fn_gini": (0, "both"), "ccdist_fn_hhi": (0, "both"),
    "change_entropy_norm": (-1, "level"), "change_top1": (+1, "level"),
    "cum_change_entropy_norm": (-1, "both"), "cum_change_top1": (+1, "both"),
    "cum_change_top5": (+1, "both"), "cum_change_hhi": (+1, "both"),
    "propagation_cost": (+1, "level"), "propagation_fanout_median": (0, "level"),
    # cohesion: LCOM low = cohesive, TCC/LCC high = cohesive -- opposite signs
    "ck_lcom_mean": (+1, "level"), "ck_lcom_max": (+1, "both"),
    "ck_lcom_star_mean": (+1, "level"),
    "ck_tcc_mean": (-1, "level"), "ck_lcc_mean": (-1, "level"),
    "ck_rfc_mean": (+1, "level"), "ck_rfc_max": (+1, "both"),
    "ck_dit_mean": (0, "level"),
    "ck_handler_lcom": (+1, "both"), "ck_handler_rfc": (+1, "both"),
    "ck_handler_cbo": (+1, "level"), "ck_handler_wmc": (+1, "both"),
    "ck_handler_tcc": (-1, "level"),
    # published detectors (external thresholds)
    "pmd_god_classes": (+1, "level"), "pmd_handler_is_god_class": (+1, "level"),
    "pmd_data_classes": (0, "level"),
    # --- pre-existing metrics with a documented prediction ---
    "wmc_handler": (+1, "both"), "wmc_max": (+1, "both"), "entry_cc": (+1, "both"),
    "node_cc_median": (+1, "both"), "node_cc_max": (+1, "both"),
    "node_path_cc": (0, "level"),
    "erosion_handler": (+1, "slope"), "impact_composite": (+1, "slope"),
    "impact_mutation": (+1, "slope"),
    # whole-app erosion is location-blind and documented as NOT a thesis test
    "erosion": (0, "slope"),
    # container_total is a VALIDITY column, not a quality claim: no prediction.
}


def bootstrap_diff_level(rows_a: list[dict], rows_b: list[dict], field: str,
                         tail_frac: float = 0.2, n_boot: int = 2000, seed: int = 0
                         ) -> tuple[float, float, float, list[float]]:
    """Bootstrap CI for the END-STATE difference: mean(A) - mean(B) over the final
    phase, resampling CHAINS within each arm independently.

    The slope test answers 'do they degrade at different rates'; most structural
    descriptions ("this arm ends with a god class", "this arm spreads over more
    files") are claims about where the codebase ENDS UP, and testing those on a
    slope is a category error that produces false counter-signals.
    """
    sa, sb = series_by_chain(rows_a, field), series_by_chain(rows_b, field)
    if not sa or not sb:
        return (math.nan, math.nan, math.nan, [])

    def tail_means(cs: dict) -> dict[int, float]:
        out = {}
        for c, pts in cs.items():
            if not pts:
                continue
            last = max(k for k, _ in pts)
            cut = last - max(1.0, last * tail_frac)
            vals = [v for k, v in pts if k >= cut]
            if vals:
                out[c] = float(np.mean(vals))
        return out

    ta, tb = tail_means(sa), tail_means(sb)
    if not ta or not tb:
        return (math.nan, math.nan, math.nan, [])
    ka, kb = list(ta), list(tb)
    point = float(np.mean([ta[c] for c in ka]) - np.mean([tb[c] for c in kb]))
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        da = np.mean([ta[c] for c in rng.choice(ka, len(ka), replace=True)])
        db = np.mean([tb[c] for c in rng.choice(kb, len(kb), replace=True)])
        diffs.append(float(da - db))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return (point, float(lo), float(hi), diffs)


def cliffs_delta(a: list[float], b: list[float]) -> Optional[float]:
    """Cliff's delta: P(a>b) - P(a<b). Non-parametric EFFECT SIZE.

    A bootstrap CI says a difference is not zero; it does not say it is large. These
    distributions are heavily skewed and ordinal comparisons are the honest summary,
    so delta accompanies every between-arm comparison. Conventional reading:
    |d| < 0.147 negligible, < 0.33 small, < 0.474 medium, else large.
    """
    if not a or not b:
        return None
    a_s = sorted(a)
    gt = lt = 0
    for y in b:
        lo = bisect.bisect_left(a_s, y)
        hi = bisect.bisect_right(a_s, y)
        lt += lo               # a values strictly below y
        gt += len(a_s) - hi    # a values strictly above y
    n = len(a) * len(b)
    return round((gt - lt) / n, 4) if n else None


def benjamini_hochberg(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg FDR control; returns the reject/keep mask.

    WHY THIS IS NOT OPTIONAL HERE. The suite tests 80+ metrics per run. At a 95% CI,
    roughly one in twenty null comparisons excludes zero by chance, so a table this
    wide manufactures several 'significant' results per run from noise alone. Adding
    metrics without FDR control makes the analysis weaker, not stronger -- which is
    the direct cost of measuring everything, and is paid here rather than denied.
    """
    m = len(pvals)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    keep = [False] * m
    thresh = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= alpha * rank / m:
            thresh = rank
    for rank, i in enumerate(order, 1):
        keep[i] = rank <= thresh
    return keep


def _boot_p(diffs: list[float]) -> float:
    """Two-sided bootstrap p-value: the mass of the replicate distribution on the
    other side of zero, doubled. Floored at 1/n_boot -- a bootstrap cannot report a
    p smaller than its own resolution, and pretending otherwise inflates the FDR."""
    if not diffs:
        return 1.0
    n = len(diffs)
    below = sum(1 for d in diffs if d <= 0)
    p = 2.0 * min(below, n - below) / n
    return max(p, 1.0 / n)


def plot_metric(groups: dict, field: str, title: str, out_path: str) -> None:
    if not HAVE_MPL:
        return
    plt.figure(figsize=(7, 4.2))
    any_line = False
    for (arm, strat), rows in sorted(groups.items()):
        cs = series_by_chain(rows, field)
        if not cs:
            continue
        acc = _bucket_by_checkpoint(cs)
        ks = sorted(acc)
        if not ks:
            continue
        mean = [np.mean(acc[k]) for k in ks]
        sd = [np.std(acc[k]) for k in ks]
        line, = plt.plot(ks, mean, marker="o", label=f"{arm}/{strat}")
        plt.fill_between(ks, np.array(mean) - np.array(sd), np.array(mean) + np.array(sd),
                         alpha=0.15, color=line.get_color())
        any_line = True
    if not any_line:
        plt.close()
        return
    plt.title(title)
    plt.xlabel("checkpoint")
    plt.ylabel(field)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(out_path, dpi=130)
    plt.close()


# Validated two-series categorical palette (dataviz reference instance, light mode:
# slot 1 blue / slot 2 orange). Checked with the palette validator -- adjacent CVD
# ΔE 24.7 (protan), normal-vision ΔE 33.6, both arms >= 3:1 on the chart surface.
# Colour follows the ARM, never its rank, so an arm keeps its hue in every figure.
ARM_COLORS = {"spring": "#eb6834", "officefloor": "#2a78d6"}
_ARM_FALLBACK = ["#1baf7a", "#eda100", "#e87ba4"]


def _arm_color(arm: str, seen: dict) -> str:
    if arm in ARM_COLORS:
        return ARM_COLORS[arm]
    return seen.setdefault(arm, _ARM_FALLBACK[len(seen) % len(_ARM_FALLBACK)])


def _mean_series(rows: list[dict], field: str):
    cs = series_by_chain(rows, field)
    if not cs:
        return None, None
    acc = _bucket_by_checkpoint(cs)
    ks = sorted(acc)
    return ks, [float(np.mean(acc[k])) for k in ks]


def plot_conservation(groups: dict, out_path: str) -> None:
    """THE figure for the Tesler/Brooks claim: amount conserved, placement diverging.

    Two STACKED PANELS sharing the x-axis, never a dual-axis chart. Total complexity
    and a concentration ratio have different units, and putting two y-scales on one
    frame lets the reader's eye infer a relationship from whatever scaling was
    chosen -- the single most misleading thing a chart of this kind can do.
    Small multiples say the same thing and cannot lie about it.
    """
    if not HAVE_MPL:
        return
    # The LABEL must travel with the field, not be hardcoded beside a fallback: a
    # panel captioned "total cyclomatic complexity" while plotting java_loc is a
    # mislabelled chart, which is worse than no chart.
    top_choices = [("total_cc", "AMOUNT — total cyclomatic complexity"),
                   ("halstead_volume", "AMOUNT — total Halstead volume"),
                   ("java_loc", "AMOUNT — Java lines of code (fallback: total_cc absent)")]
    bottom_choices = [("ccdist_file_top5", "PLACEMENT — share of all CC in the heaviest 5 files"),
                      ("cum_change_top5", "PLACEMENT — share of all change in 5 files"),
                      ("wmc_handler", "PLACEMENT — WMC of the handler class (fallback)")]
    def _pick(choices):
        for field, label in choices:
            if any(series_by_chain(r, field) for r in groups.values()):
                return field, label
        return None, None
    top, top_label = _pick(top_choices)
    bottom, bottom_label = _pick(bottom_choices)
    if not top or not bottom:
        return
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 6.4), sharex=True)
    seen: dict = {}
    for ax, field, label in ((axes[0], top, top_label), (axes[1], bottom, bottom_label)):
        for (arm, strat), rows in sorted(groups.items()):
            ks, mean = _mean_series(rows, field)
            if not ks:
                continue
            ax.plot(ks, mean, linewidth=2, color=_arm_color(arm, seen),
                    label=f"{arm}/{strat}")
            if len(ks) > 1:                      # selective direct label, last point only
                ax.annotate(f"{mean[-1]:.4g}", (ks[-1], mean[-1]), textcoords="offset points",
                            xytext=(4, 0), fontsize=8, color="#52514e", va="center")
        ax.set_title(label, fontsize=10, loc="left")
        ax.set_ylabel(field, fontsize=9)
        ax.grid(True, alpha=0.18, linewidth=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[1].set_xlabel("checkpoint")
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Complexity is conserved; its placement is not", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_lorenz(groups: dict, out_path: str) -> None:
    """Lorenz curves of CC across files at the chain tips — how to SHOW a Gini.

    Each arm's curve is the mean over its chains of the per-chain Lorenz points.
    The diagonal is perfect equality. Two curves of SIMILAR SHAPE drawn over very
    different file counts is the honest picture: the inequality is comparable, the
    number of units it is spread over is not -- which is exactly why Gini and HHI
    disagree here and why both are reported.
    """
    if not HAVE_MPL:
        return
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    seen: dict = {}
    drew = False
    for (arm, strat), rows in sorted(groups.items()):
        curves, nfiles = [], []
        by_chain: dict[int, dict] = {}
        for r in rows:
            if r.get("ccdist_file_lorenz"):
                by_chain.setdefault(int(r["chain"]), {})[int(r["checkpoint"])] = r
        for chain, cps in by_chain.items():
            tip = cps[max(cps)]
            try:
                pts = [float(x) for x in tip["ccdist_file_lorenz"].split(",")]
            except (ValueError, AttributeError):
                continue
            curves.append(pts)
            nf = _f(tip.get("total_files"))
            if not math.isnan(nf):
                nfiles.append(nf)
        if not curves:
            continue
        width = min(len(c) for c in curves)
        mean = [float(np.mean([c[i] for c in curves])) for i in range(width)]
        xs = [i / (width - 1) for i in range(width)]
        lbl = f"{arm}/{strat}"
        if nfiles:
            lbl += f" ({np.mean(nfiles):.0f} files)"
        ax.plot(xs, mean, linewidth=2, marker="o", markersize=4,
                color=_arm_color(arm, seen), label=lbl)
        drew = True
    if not drew:
        plt.close(fig)
        return
    ax.plot([0, 1], [0, 1], linewidth=1, linestyle="--", color="#9b9a93",
            label="perfect equality")
    ax.set_xlabel("cumulative share of files (least complex first)")
    ax.set_ylabel("cumulative share of total cyclomatic complexity")
    ax.set_title("Lorenz curve of complexity across files (chain tips)", fontsize=11)
    ax.grid(True, alpha=0.18, linewidth=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_chain_strip(groups: dict, fields: list[str], out_path: str) -> None:
    """Per-chain tip values for the headline placement metrics.

    A mean curve hides the SPREAD between chains, and the spread is itself a finding
    in this experiment (one prompt, ten chains, several genuinely different
    architectures). One dot per chain, so a reader sees whether an effect is
    consistent or driven by two outliers.
    """
    if not HAVE_MPL:
        return
    fields = [f for f in fields if any(series_by_chain(r, f) for r in groups.values())]
    if not fields:
        return
    fig, axes = plt.subplots(1, len(fields), figsize=(2.6 * len(fields) + 1.4, 4.0))
    if len(fields) == 1:
        axes = [axes]
    seen: dict = {}
    for ax, field in zip(axes, fields):
        labels = []
        for i, ((arm, strat), rows) in enumerate(sorted(groups.items())):
            cs = series_by_chain(rows, field)
            tips = [pts[-1][1] for pts in cs.values() if pts]
            if not tips:
                continue
            jitter = (np.random.default_rng(0).random(len(tips)) - 0.5) * 0.18
            ax.scatter([i + j for j in jitter], tips, s=34, alpha=0.85,
                       color=_arm_color(arm, seen), edgecolors="#fcfcfb", linewidths=0.8)
            ax.hlines(float(np.mean(tips)), i - 0.28, i + 0.28,
                      color=_arm_color(arm, seen), linewidth=2)
            labels.append((i, arm))
        ax.set_xticks([i for i, _ in labels])
        ax.set_xticklabels([a for _, a in labels], fontsize=8, rotation=20)
        ax.set_title(field, fontsize=9)
        ax.grid(True, axis="y", alpha=0.18, linewidth=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle("Per-chain values at the chain tip (bar = arm mean)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", help="which run to analyze (default: latest)")
    ap.add_argument("--gammas", default="1,1.5,2")
    ap.add_argument("--chains", default="",
                    help="comma-separated chain indices to recompute (default: all). "
                         "For VALIDATING an analysis change in minutes instead of hours "
                         "— a one-chain pass exercises every derive and summary code path. "
                         "Results from a subset are NOT publishable: the chain-cluster "
                         "bootstrap needs the full set, and the summary says so.")
    args = ap.parse_args()
    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    # Every structural metric below is function-based, so a Java file this lizard
    # cannot parse silently recomputes as zero complexity and zero change rather
    # than erroring. Refuse to analyze with a parser that is blind to annotated
    # classes (see harness/parser_selftest.py).
    harness_parser = parser_selftest.check_lizard()
    if not harness_parser["ok"]:
        raise SystemExit(f"lizard {harness_parser['version']} cannot see methods in an "
                         f"@Entity/@Table class — every structural metric would be wrong. "
                         f"Run: python -m harness.parser_selftest --config <config.yaml>")

    # Everything derived is recomputed here from the commits + capture (see module
    # header); nothing derived is read from the branches.
    for name, arm_cfg in cfg["arms"].items():
        arm_cfg["repo"] = expand_path(arm_cfg["repo"], f"arms.{name}.repo")

    # Anchor tool paths exactly as run_experiment.main does. metrics/quality_gate run
    # these binaries with cwd=<arm worktree>, so a config-relative path like
    # tools/node_modules/.bin/ast-grep resolves against the WORKTREE and vanishes —
    # and verbosity() answers a missing binary with a silent fallback, not an error.
    # Bare names (jscpd, sg) are left alone so PATH still works.
    _cfg_dir = os.path.dirname(os.path.abspath(args.config))
    def _anchor(value: str) -> str:
        v = expand_path(value, "tools")
        return v if os.path.isabs(v) else os.path.join(_cfg_dir, v)
    for _tk in ("jscpd", "astgrep", "astgrep_rules", "pmd", "pmd_rules",
                "pmd_metrics_rules", "ck"):
        _tv = cfg.get("tools", {}).get(_tk)
        if _tv and (os.sep in _tv or (os.altsep and os.altsep in _tv)):
            cfg["tools"][_tk] = _anchor(_tv)

    work_root = expand_path(cfg["paths"]["work_root"], "paths.work_root")
    if not os.path.isabs(work_root):
        work_root = os.path.join(os.path.dirname(os.path.abspath(args.config)), work_root)

    run_id = args.run_id or _latest_run_id(cfg)
    if not run_id:
        raise SystemExit("no evolve branches found; run the experiment first")
    # Derive with the run's OWN config snapshot (globs/thresholds/entry-handler/
    # ast-grep rules), so metrics match how that run was configured.
    snap_tmp = os.path.join(work_root, "recompute-config", str(run_id))
    shutil.rmtree(snap_tmp, ignore_errors=True)
    os.makedirs(snap_tmp, exist_ok=True)
    eff_cfg = _resolve_run_config(cfg, run_id, snap_tmp)
    chain_filter = ({int(c) for c in args.chains.split(",") if c.strip()}
                    if args.chains else None)
    if chain_filter:
        print(f"  ! VALIDATION MODE: chains {sorted(chain_filter)} only — "
              f"results are NOT publishable (the chain-cluster bootstrap needs all chains)")
    rows = recompute_rows(eff_cfg, run_id, work_root,
                          exclude=eff_cfg.get("acceptance", {}).get("dest_subpath"),
                          chains=chain_filter)
    if not rows:
        raise SystemExit(f"no checkpoint commits found for run_id {run_id!r}")
    print(f"run_id {run_id}: recomputed {len(rows)} rows from checkpoint commits")

    # Analysis outputs are local, derived, and gitignored (never committed to the
    # harness repo). A concatenated CSV is written for transparency.
    results_csv = expand_path(cfg["paths"]["results_csv"], "paths.results_csv")
    if not os.path.isabs(results_csv):
        results_csv = os.path.join(os.path.dirname(os.path.abspath(args.config)), results_csv)
    out_root = os.path.join(os.path.dirname(results_csv), str(run_id))
    out_dir = os.path.join(out_root, "analysis")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_root, "records.concat.csv"), "w", newline="") as fh:
        fieldnames = list(dict.fromkeys(k for r in rows for k in r))  # union, order-preserving
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Impact is reported in three slices — ALL checkpoints, ADDITIVE-only, MUTATIVE-only
    # — so the split can be read directly. The per-checkpoint impact value is the same
    # regardless of slice; the slices are just filtered VIEWS (a mutative checkpoint is a
    # mandated rule revision, and the context weight makes it genuine architectural signal
    # — the arm that isolated the concern pays less: Spring ~36k/mutative-cp vs OfficeFloor
    # ~4.8k on blind-202608100006). Synthesise `_add`/`_mut` view columns off the raw
    # (all-checkpoint) impact fields — blank on the other type, so the generic NaN-dropping
    # slope/plot machinery yields the filtered curve with no special casing. Done after the
    # raw CSV is written, so these derived views never bloat the CSV.
    for r in rows:
        is_mut = str(r.get("checkpoint_type", "")).strip() == "mutative"
        for f in IMPACT_BASE_FIELDS:
            v = r.get(f, "")
            r[f + "_add"] = "" if is_mut else v   # additive-only view
            r[f + "_mut"] = v if is_mut else ""    # mutative-only view

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)

    gammas = [float(g) for g in args.gammas.split(",")]
    lines = ["# PetClinic-Evolve results\n"]

    # Degradation slopes (headline)
    lines.append("## Degradation slopes m (OLS of metric on checkpoint; 95% bootstrap CI)\n")
    lines.append("| arm/strategy | metric | slope m | CI low | CI high |")
    lines.append("|---|---|---:|---:|---:|")
    # DERIVED from METRICS_TO_PLOT, never written out again: the two lists were
    # maintained separately and a metric added to one but not the other silently got
    # a plot with no slope, or a slope with no plot.
    slope_fields = [f for f, _ in METRICS_TO_PLOT]
    for gk, grp in sorted(groups.items()):
        for field in slope_fields:
            cs = series_by_chain(grp, field)
            if not cs:
                continue
            m, lo, hi = bootstrap_slope(cs)
            if math.isnan(m):
                continue
            lines.append(f"| {gk[0]}/{gk[1]} | {field} | {m:.4g} | {lo:.4g} | {hi:.4g} |")
    lines.append("")

    # ImpactGate pipeline (impact_gated strategy only) — did the architecture absorb the
    # change stream under the gate, and at what refactor cost? Rendered only when a group
    # carries gate data (rows with a non-blank ig_refactors), so ungated runs are unaffected.
    def _has_gate(grp):
        return any(str(r.get("ig_refactors", "")) != "" for r in grp)
    gate_groups = {gk: grp for gk, grp in groups.items() if _has_gate(grp)}
    if gate_groups:
        n_cp = max((int(r["checkpoint"]) for grp in gate_groups.values() for r in grp), default=0)
        lines.append("## ImpactGate pipeline (impact_gated)\n")
        lines.append("Per (arm, chain-pooled): the enforcement mode, whether the gated chains "
                     f"reached the final checkpoint (cp{n_cp:02d}), how often a checkpoint needed a "
                     "refactor, the mean refactors/checkpoint, the refactor cost, and the accepted "
                     "change's mean seed grade. `enforcement=block` is the HARD gate and can STOP a "
                     "chain: `impact` = the change stayed over the block percentile even after clean "
                     "refactors (the architecture could not absorb it); `quality` = a refactor could "
                     "not be made statically clean within max_review_turns (it could only lower "
                     "impact with slop). `enforcement=advisory` never stops — it runs one "
                     "quality-gated refactor on a flagged change and RECORDS the impact; the "
                     "`direct→accepted impact` column is the median first-attempt vs accepted "
                     "(post-refactor) impact over the refactored checkpoints, i.e. the measured "
                     "effect of one cohesion refactor. `review turns` counts the code-review turns "
                     "the quality gate forced.\n")
        lines.append("| arm/strategy | enforce | chains reached final | stops (impact/quality) | "
                     "checkpoints w/ refactor | mean refactors/cp | direct→accepted impact (median) | "
                     "review turns (sum) | refactor $ (sum) | accepted grade (mean) |")
        lines.append("|---|:--:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for gk, grp in sorted(gate_groups.items()):
            gated = [r for r in grp if str(r.get("ig_refactors", "")) != ""]
            chains = sorted({int(r["chain"]) for r in gated})
            reached = sum(1 for ch in chains
                          if max(int(r["checkpoint"]) for r in gated if int(r["chain"]) == ch) >= n_cp)
            enforce = next((str(r.get("ig_enforcement")) for r in gated
                            if str(r.get("ig_enforcement", "")) not in ("", "None")), "block")
            stop_impact = sum(1 for r in gated if str(r.get("ig_stop_reason", "")) == "impact")
            stop_quality = sum(1 for r in gated if str(r.get("ig_stop_reason", "")) == "quality")
            nref = [int(_f(r.get("ig_refactors", "")) or 0) for r in gated]
            with_ref = sum(1 for v in nref if v > 0)
            qturns = sum(int(_f(r.get("ig_quality_review_turns", "")) or 0) for r in gated)
            grades = [_f(r.get("ig_grade", "")) for r in gated]
            grades = [g for g in grades if not math.isnan(g)]
            rcost = sum(_f(r.get("ig_refactor_cost_usd", "")) or 0 for r in gated
                        if not math.isnan(_f(r.get("ig_refactor_cost_usd", ""))))
            mean_ref = (sum(nref) / len(nref)) if nref else 0.0
            mean_grade = (sum(grades) / len(grades)) if grades else float("nan")
            # one-refactor cohesion effect: first-attempt vs accepted impact, only on cps that
            # actually ran a refactor (others have first==accepted by construction).
            ref_rows = [r for r in gated if int(_f(r.get("ig_refactors", "")) or 0) > 0]
            firsts = [_f(r.get("ig_impact_first", "")) for r in ref_rows]
            accs = [_f(r.get("ig_impact", "")) for r in ref_rows]
            firsts = [v for v in firsts if not math.isnan(v)]
            accs = [v for v in accs if not math.isnan(v)]
            med_first = statistics.median(firsts) if firsts else float("nan")
            med_acc = statistics.median(accs) if accs else float("nan")
            impact_cell = ("—" if math.isnan(med_first)
                           else f"{med_first:.0f}→{med_acc:.0f}")
            lines.append(f"| {gk[0]}/{gk[1]} | {enforce} | {reached}/{len(chains)} | "
                         f"{stop_impact}/{stop_quality} | {with_ref}/{len(gated)} | "
                         f"{mean_ref:.2f} | {impact_cell} | {qturns} | ${rcost:.2f} | "
                         f"{'—' if math.isnan(mean_grade) else f'p{mean_grade:.1f}'} |")
        lines.append("")

    # Difference of slopes — the PAIRED test (per-arm CIs vs zero are not a between-arm test)
    lines.append("## Difference of slopes (arm A − arm B; 95% bootstrap CI over chains)\n")
    lines.append("A CI that excludes 0 means the two arms degrade at genuinely different rates on "
                 "that metric — the actual between-arm test, not eyeballing two separate CIs.\n")
    lines.append("`q` is the Benjamini-Hochberg FDR-adjusted verdict over ALL metrics in this "
                 "family: with 80+ metrics a 95% CI alone manufactures several false positives per "
                 "run, so `excludes 0` is the raw test and `FDR` is the one to quote. `delta` is "
                 "Cliff's delta (effect SIZE: |d|<0.147 negligible, <0.33 small, <0.474 medium, "
                 "else large) — a CI says a difference is not zero, not that it matters. `exp` is "
                 "the PRE-DECLARED expected direction (`METRIC_EXPECTATION`); `!` marks a result "
                 "that contradicts it and is collected in the counter-signals section below.\n")
    lines.append("| strategy | A − B | metric | slope diff | CI low | CI high | excludes 0 | FDR | delta | level diff | level FDR | exp |")
    lines.append("|---|---|---|---:|---:|---:|:--:|:--:|---:|---:|:--:|:--:|")
    counter_signals: list[tuple] = []
    for strat in sorted({s for (_, s) in groups}):
        arms = [a for (a, s) in groups if s == strat]
        if len(arms) != 2:
            continue
        a1, a2 = (("spring", "officefloor") if {"spring", "officefloor"} <= set(arms)
                  else tuple(sorted(arms, reverse=True)))
        ra, rb = groups[(a1, strat)], groups[(a2, strat)]
        # A bootstrap over fewer than 3 chains is degenerate: every replicate is the
        # same resample, the CI collapses to a point and EVERY comparison "survives"
        # FDR. That would fill the counter-signal section with spurious
        # contradictions, which is worse than reporting nothing -- so predictions are
        # not judged at all below that floor.
        n_chains = min(len({int(r["chain"]) for r in ra}),
                       len({int(r["chain"]) for r in rb}))
        judge = n_chains >= 3
        if not judge:
            lines.append(f"| {strat} | {a1}−{a2} | _expectations not judged_ | | | | | | | | | "
                         f"only {n_chains} chain(s) — bootstrap degenerate |")
        rows_out = []
        for field in slope_fields:
            d, lo, hi, reps = bootstrap_diff_slope(ra, rb, field)
            if math.isnan(d):
                continue
            ld, llo, lhi, lreps = bootstrap_diff_level(ra, rb, field)
            va = [_f(r.get(field)) for r in ra]
            vb = [_f(r.get(field)) for r in rb]
            delta = cliffs_delta([x for x in va if not math.isnan(x)],
                                 [x for x in vb if not math.isnan(x)])
            rows_out.append([field, d, lo, hi, _boot_p(reps), delta,
                             ld, llo, lhi, (_boot_p(lreps) if lreps else 1.0)])
        # FDR is applied ACROSS the whole family, separately per dimension: the slope
        # tests and the level tests are two families of 80+, not one of 160.
        keep_s = benjamini_hochberg([r[4] for r in rows_out])
        keep_l = benjamini_hochberg([r[9] for r in rows_out])
        for (field, d, lo, hi, pv, delta, ld, llo, lhi, lpv), sig, lsig in zip(
                rows_out, keep_s, keep_l):
            excl = "yes" if (lo > 0 or hi < 0) else "no"
            spec = METRIC_EXPECTATION.get(field)
            mark = ""
            if spec is not None and judge:
                exp, dim = spec
                # `d > 0 else -1` sent an exact 0 to -1, reporting a zero difference
                # as a direction -- which happens for real (erosion_handler is 0 in
                # both arms on several runs), not just in degenerate samples.
                obs_slope = 0 if (not sig or d == 0) else (1 if d > 0 else -1)
                obs_level = (0 if (not lsig or math.isnan(ld) or ld == 0)
                             else (1 if ld > 0 else -1))
                checks = ([("slope", obs_slope)] if dim == "slope"
                          else [("level", obs_level)] if dim == "level"
                          else [("slope", obs_slope), ("level", obs_level)])
                for dim_name, obs in checks:
                    m = ""
                    if exp == 0 and obs != 0:
                        m = "!"
                    elif exp != 0 and obs == -exp:
                        m = "!"
                    elif exp != 0 and obs == 0:
                        m = "~"
                    if m:
                        mark = "!" if (m == "!" or mark == "!") else "~"
                        shown = (d, lo, hi) if dim_name == "slope" else (ld, llo, lhi)
                        counter_signals.append((strat, f"{a1}−{a2}", field, dim_name,
                                                *shown, exp, obs, delta, m))
            exps = {1: "+", -1: "−", 0: "0"}.get(spec[0] if spec else None, "")
            lines.append(f"| {strat} | {a1}−{a2} | {field} | {d:.4g} | {lo:.4g} | {hi:.4g} | "
                         f"{excl} | {'yes' if sig else 'no'} | "
                         f"{'' if delta is None else f'{delta:+.3f}'} | "
                         f"{'' if math.isnan(ld) else f'{ld:.4g}'} | "
                         f"{'yes' if lsig else 'no'} | {exps}{mark} |")
    lines.append("")

    # ---- Counter-signals: every measure that does NOT support the hypothesis -----
    lines.append("## Counter-signals — measures that do NOT support the hypothesis\n")
    lines.append("Every metric whose FDR-surviving result contradicts its pre-declared expectation "
                 "(`!`), or where a predicted difference did not appear (`~`). This section exists so "
                 "a disagreeing measure is published by the harness rather than found by a reader: the "
                 "suite is deliberately wider than the argument, and a wide suite is only honest if "
                 "the misses are as visible as the hits. `~` is the weaker note — an absent effect is "
                 "not a contrary one, and with FDR control over 80+ metrics some real effects will "
                 "fail to survive.\n")
    if not counter_signals:
        lines.append("_None: every metric with a recorded expectation matched it "
                     "(or expectations were not judged — see the note in the table above "
                     "if a comparison had fewer than 3 chains)._\n")
    else:
        lines.append("| strategy | A − B | metric | on | diff | CI | expected | observed | delta | |")
        lines.append("|---|---|---|:--:|---:|---|:--:|:--:|---:|:--:|")
        for (strat, pair, field, dim_name, d, lo, hi, exp, obs, delta, mark) in counter_signals:
            nm = {1: "A higher", -1: "B higher", 0: "no difference"}
            lines.append(f"| {strat} | {pair} | {field} | {dim_name} | {d:.4g} | [{lo:.3g}, {hi:.3g}] | "
                         f"{nm[exp]} | {nm[obs]} | {'' if delta is None else f'{delta:+.3f}'} | {mark} |")
        lines.append("")
        n_bang = sum(1 for c in counter_signals if c[10] == "!")
        lines.append(f"**{n_bang} contradicted, {len(counter_signals) - n_bang} predicted-but-absent.**\n")

    # Impact-metric external validation — does per-checkpoint impact predict independent pain?
    lines.append("## Impact-metric validation (Spearman ρ of `impact_composite` vs independent outcomes)\n")
    lines.append("Within-arm correlation with signals measured *independently* of the git-diff impact "
                 "computation (agent cost/time, comprehension, unintended breakage); 95% CI by chain-cluster "
                 "bootstrap. A construct-validity check: does a change the metric scores as high-impact "
                 "actually cost more and break more?\n")
    lines.append("| arm/strategy | outcome | Spearman ρ | CI low | CI high | n |")
    lines.append("|---|---|---:|---:|---:|---:|")
    # Outcomes that come from the GATE: computed only over checkpoints that
    # returned a verdict (an aborted gate has no breakage count to correlate).
    CORRECTNESS_OUTCOMES = {"true_regressions"}
    OUTCOMES = [("cost_usd", "agent $ (independent)"),
                ("cache_read_tokens", "comprehension (independent)"),
                ("duration_api_ms", "model time (independent)"),
                ("true_regressions", "broke untouched rule (independent)"),
                ("reedit_rate", "temporal coupling (git-derived)")]
    for gk, grp in sorted(groups.items()):
        for field, note in OUTCOMES:
            rho, lo, hi, n, k = spearman_ci(scored(grp) if field in CORRECTNESS_OUTCOMES else grp,
                                            "impact_composite", field)
            if math.isnan(rho):
                # Reported, not dropped: "we could not test this" is itself a result,
                # and a silently missing row looks the same as a row nobody ran.
                lines.append(f"| {gk[0]}/{gk[1]} | {note} | not tested | | | "
                             f"{k} event(s) < {MIN_EVENTS} of {n} |")
                continue
            lines.append(f"| {gk[0]}/{gk[1]} | {note} | {rho:+.3f} | {lo:+.3f} | {hi:+.3f} | {n} |")
    lines.append("")

    # ---- Does structure predict MAINTENANCE OUTCOMES? ------------------------
    lines.append("## Outcome-prediction matrix (Spearman ρ of each structural metric "
                 "vs independent outcomes)\n")
    lines.append("The thesis is not that the arms differ structurally — it is that PLACEMENT drives "
                 "maintainability. That is only tested by regressing the structural measures against "
                 "outcomes measured independently of them: what the agent paid ($, time, cache reads) "
                 "and what it broke. ρ is computed WITHIN each arm/strategy (so the between-arm "
                 "difference cannot manufacture a correlation) and then averaged over groups via "
                 "Fisher z; `sig` counts the groups whose chain-cluster CI excluded 0.\n")
    lines.append("If the `amount` rows are flat and the `placement` rows are not, Tesler and Brooks "
                 "are supported by prediction and not merely by description — and if the `amount` "
                 "rows predict just as well, that is the single most important negative result in "
                 "this suite and belongs in the abstract.\n")
    lines.append("| group | metric | " + " | ".join(n for _, n in OUTCOMES) + " |")
    lines.append("|---|---|" + "---:|" * len(OUTCOMES))
    _summary: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for field, _lab in METRICS_TO_PLOT:
        grp_name = METRIC_GROUP.get(field)
        if grp_name is None:
            continue
        cells = []
        for ofield, _note in OUTCOMES:
            zs, nsig = [], 0
            for gk, grp in sorted(groups.items()):
                src = scored(grp) if ofield in CORRECTNESS_OUTCOMES else grp
                rho, lo, hi, n, k = spearman_ci(src, field, ofield, n_boot=400)
                if math.isnan(rho):
                    continue
                zs.append(np.arctanh(max(min(rho, 0.999999), -0.999999)))
                if lo > 0 or hi < 0:
                    nsig += 1
            if not zs:
                cells.append("—")
                continue
            rho_bar = float(np.tanh(np.mean(zs)))
            _summary[grp_name][ofield].append(abs(rho_bar))
            cells.append(f"{rho_bar:+.3f} ({nsig}/{len(groups)})")
        lines.append(f"| {grp_name} | `{field}` | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("### Mean |ρ| by claim group — the headline of this section\n")
    lines.append("| group | " + " | ".join(n for _, n in OUTCOMES) + " |")
    lines.append("|---|" + "---:|" * len(OUTCOMES))
    for grp_name in ("amount", "tax", "placement"):
        cells = []
        for ofield, _note in OUTCOMES:
            vals = _summary.get(grp_name, {}).get(ofield, [])
            cells.append(f"{np.mean(vals):.3f} (n={len(vals)})" if vals else "—")
        lines.append(f"| {grp_name} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("### `impact_composite` on checkpoints that caused a true regression vs not\n")
    lines.append("| arm/strategy | median (true regression) | median (none) | n true-regr |")
    lines.append("|---|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        wtr = [_f(r.get("impact_composite", "")) for r in scored(grp)
               if (_f(r.get("true_regressions", "")) or 0) > 0 and not math.isnan(_f(r.get("impact_composite", "")))]
        ntr = [_f(r.get("impact_composite", "")) for r in scored(grp)
               if (_f(r.get("true_regressions", "")) or 0) == 0 and not math.isnan(_f(r.get("impact_composite", "")))]
        base = f"{np.median(ntr):.0f}" if ntr else ""
        if len(wtr) >= MIN_EVENTS and ntr:
            lines.append(f"| {gk[0]}/{gk[1]} | {np.median(wtr):.0f} | {base} | {len(wtr)} |")
        else:
            # A median of one or two checkpoints is not a median. Say so rather than
            # printing it, and rather than omitting the arm without explanation.
            lines.append(f"| {gk[0]}/{gk[1]} | not reported (< {MIN_EVENTS} true regressions) | "
                         f"{base} | {len(wtr)} |")
    lines.append("")

    # Phase means
    lines.append("## Phase-binned means\n")
    for field in ["erosion", "erosion_handler", "impact_mutation", "impact_godclass",
                  "verbosity", "cost_usd", "strict_pass"]:
        lines.append(f"### {field}")
        lines.append("| arm/strategy | Start | Early | Mid | Late | Final |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for gk, grp in sorted(groups.items()):
            if field == "strict_pass":
                order = ["Start", "Early", "Mid", "Late", "Final"]
                acc = defaultdict(list)
                for r in scored(grp):
                    acc[r["phase"]].append(1.0 if _b(r["strict_pass"]) else 0.0)
                vals = [np.mean(acc[p]) if acc[p] else math.nan for p in order]
            else:
                _, vals = phase_means(grp, field)
            cells = " | ".join("" if math.isnan(v) else f"{v:.3g}" for v in vals)
            lines.append(f"| {gk[0]}/{gk[1]} | {cells} |")
        lines.append("")

    # EvoScore + Zero-Regression Rate
    lines.append("## EvoScore (strict_pass) and Zero-Regression Rate\n")
    header = "| arm/strategy | " + " | ".join(f"EvoScore γ={g}" for g in gammas) + " | Zero-Regr Rate |"
    lines.append(header)
    lines.append("|---" * (len(gammas) + 2) + "|")
    for gk, grp in sorted(groups.items()):
        evs = " | ".join(f"{evoscore(grp, g):.3f}" for g in gammas)
        zrr = zero_regression_rate(grp)
        lines.append(f"| {gk[0]}/{gk[1]} | {evs} | {zrr:.3f} |")
    lines.append("")

    # Regression split: a mutative checkpoint's changes to prior rules are INTENDED,
    # so its regressions there do not count as faults. true_regressions counts only
    # breakage on the surface the checkpoint was not asked to touch. The true
    # Zero-Regression Rate is the safety signal a purely additive run cannot give.
    lines.append("## Regressions: intended vs. true (un-mutated surface)\n")
    lines.append("| arm/strategy | mutative cps | total regr | intended | true regr | true Zero-Regr Rate | invalid gates |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        rs = regression_summary(grp)
        tzrr = zero_regression_rate(grp, "true_regressions")
        lines.append(f"| {gk[0]}/{gk[1]} | {rs['mutative_cps']} | {rs['total']} | "
                     f"{rs['intended']} | {rs['true']} | {tzrr:.3f} | {rs['invalid_gates']} |")
    lines.append("")
    # Checkpoints whose structural metrics are MISSING (the worktree could not be
    # created, so compute_all never ran). Their correctness fields are still valid, so
    # they stay in the correctness aggregates; every structural slope/mean simply has
    # one fewer point. Counted here because the alternative — the old behaviour — was
    # a KeyError that discarded the entire recompute, and the alternative to THAT is a
    # silent hole in the data.
    missing = [r for r in rows if "wmc_max" not in r]
    if missing:
        lines.append("## Checkpoints missing structural metrics\n")
        lines.append(f"`git worktree add` failed for **{len(missing)} of {len(rows)}** "
                     f"checkpoints, so `metrics.compute_all` never ran there. Correctness "
                     f"for those checkpoints is unaffected and still counted; every "
                     f"structural curve below is fitted on the remaining points.\n")
        by_grp = Counter(f"{r['arm']}/{r['strategy']} chain{r['chain']}" for r in missing)
        lines.append("| arm/strategy chain | checkpoints |")
        lines.append("|---|---:|")
        for k, v in sorted(by_grp.items()):
            lines.append(f"| {k} | {v} |")
        lines.append("")
        print(f"  ! {len(missing)} checkpoint(s) have no structural metrics "
              f"(worktree add failed); slopes fitted on the rest")

    # Test-family pass rates. `strict_pass` is all-or-nothing and CONFLATES the two
    # failure modes: not implementing the checkpoint's new rule, and breaking a rule
    # that already worked. They mean opposite things — the first is capability, the
    # second is retention — and only the split says which one a prompt/architecture
    # cost you. Pooled over every checkpoint's raw test counts (not a mean of per-
    # checkpoint rates), so a checkpoint with more tests weighs more.
    #   core  - the app's own untouched behaviour
    #   error - error/validation surface
    #   func  - THIS checkpoint's new rule (capability)
    #   regr  - previously-passing rules (retention)
    lines.append("## Pass rate by test family (pooled over checkpoints)\n")
    lines.append("`strict_pass` conflates two different failures. `func` is whether the "
                 "checkpoint's OWN new rule was implemented; `regr` is whether previously "
                 "passing rules still pass. A run can hold `func` at 1.000 — every rule "
                 "delivered — while `regr` erodes, which is degradation in the precise "
                 "sense this experiment is about, and is invisible in `strict_pass` alone.\n")
    FAMILIES = [("core", "core"), ("error", "error"), ("func", "func"), ("regr", "regr")]
    lines.append("| arm/strategy | " + " | ".join(f"{lbl}" for _, lbl in FAMILIES) + " |")
    lines.append("|---|" + "---:|" * len(FAMILIES))
    for gk, grp in sorted(groups.items()):
        cells = []
        for fam, _lbl in FAMILIES:
            num = den = 0.0
            for r in grp:
                p_, t_ = _f(r.get(f"{fam}_p")), _f(r.get(f"{fam}_t"))
                if math.isnan(p_) or math.isnan(t_):
                    continue
                num += p_
                den += t_
            cells.append("" if den <= 0 else f"{num / den:.3f}")
        lines.append(f"| {gk[0]}/{gk[1]} | " + " | ".join(cells) + " |")
    lines.append("")

    # "final" columns are the last checkpoint's value averaged across chains; the
    # slope table above shows whether each climbs over the chain.
    def _final_mean(grp, field):
        by_chain = {}
        for r in grp:
            by_chain[int(r["chain"])] = r  # rows arrive in checkpoint order; keep last
        vals = [_f(r.get(field)) for r in by_chain.values()]
        vals = [v for v in vals if not math.isnan(v)]
        return float(np.mean(vals)) if vals else math.nan

    # Verbosity decomposition. `verbosity` is (clone ∪ smell lines) / LOC, so it moves
    # when EITHER end moves and the ratio alone cannot say which. Both readings occur in
    # practice: on blind-202609010045 OfficeFloor's ratio rose with clone lines FLAT and
    # LOC falling (same duplication, less code), while Spring's rose with clone lines
    # genuinely up. Opposite meanings, same direction on the headline number — so the
    # numerator and denominator are reported beside it.
    lines.append("## Verbosity decomposition (final phase)\n")
    lines.append("`verbosity` = (clone ∪ smell lines) / LOC. The ratio rises either because "
                 "duplication grew or because the codebase shrank around it — opposite "
                 "findings. Numerator and denominator are shown so the ratio is never read "
                 "on its own.\n")
    lines.append("| arm/strategy | verbosity | clone lines | smell lines | java LOC |")
    lines.append("|---|---:|---:|---:|---:|")
    cell = lambda v: "—" if math.isnan(v) else f"{v:.3g}"
    for gk, grp in sorted(groups.items()):
        lines.append(f"| {gk[0]}/{gk[1]} | {cell(_final_mean(grp, 'verbosity'))} | "
                     f"{cell(_final_mean(grp, 'verbosity_clone_lines'))} | "
                     f"{cell(_final_mean(grp, 'verbosity_pattern_lines'))} | "
                     f"{cell(_final_mean(grp, 'java_loc'))} |")
    lines.append("")
    # metrics.verbosity() degrades gracefully: if ONE of the two stacks produces no
    # output it silently uses the other, so a missing/mismatched smell detector turns
    # verbosity into a clones-only measure with no error anywhere. That is the same
    # silent-zero failure the lizard pin exists to prevent, so say it out loud here.
    if all(math.isnan(_final_mean(grp, "verbosity_pattern_lines"))
           for grp in groups.values()):
        # verbosity_pattern_lines is RECOMPUTED live here (recompute_rows ->
        # metrics.compute_all with the resolved tools), not read from the capture, so an
        # empty column is a CURRENT-environment failure of the configured detector and is
        # fixable by re-analysis once the detector works — no re-run needed. Name the
        # detector the resolved config actually uses (PMD when tools.pmd is set, else the
        # legacy ast-grep), not a hard-coded guess.
        _tools = eff_cfg.get("tools", {})
        if _tools.get("pmd"):
            _detector = (f"PMD (`{_tools['pmd']}`, ruleset "
                         f"`{_tools.get('pmd_rules', '')}`)")
        else:
            _detector = (f"ast-grep (`{_tools.get('astgrep', 'unset')}`, rules "
                         f"`{_tools.get('astgrep_rules', '')}`)")
        lines.append(
            "> **The smell half did not run.** `verbosity_pattern_lines` is empty for every "
            "checkpoint, so `verbosity` above is CLONE DETECTION ONLY. This column is "
            "recomputed at analyze time from the resolved tools, so it means the configured "
            f"smell detector — {_detector} — returned no output and `verbosity()` silently "
            "fell back to clones. Check that the binary runs and its ruleset matches the arm's "
            "language (the legacy ast-grep set was `language: python` and never matches Java), "
            "then RE-ANALYZE — this column backfills without a re-run. NOTE: the same stack "
            "backs the refactor quality gate, but `ig_quality_smell_lines` is read from the "
            "run's OWN capture, not recomputed; if that column is also empty the gate itself "
            "ran clone-only during the run, and only a re-run fixes that.\n")

    # Invalid gates are MISSING correctness, not failed correctness (a Surefire fork
    # crash, not the agent's code). They are excluded from every correctness aggregate
    # above and listed here so the exclusion is never silent — a run with many of them
    # is a run whose safety numbers rest on fewer checkpoints than it appears to.
    invalid = [r for r in rows if _b(r.get("gate_invalid"))]
    if invalid:
        lines.append("## Invalid gates (aborted test runs — excluded from correctness)\n")
        lines.append("The gate produced no usable verdict at these checkpoints (e.g. the Surefire "
                     "fork crashed). Their structural metrics are unaffected and still counted; "
                     "their correctness fields are blank rather than scored, because an empty "
                     "result set would otherwise read as a regression on every prior rule.\n")
        lines.append("| arm/strategy | chain | checkpoint | id | note |")
        lines.append("|---|---:|---:|---|---|")
        for r in sorted(invalid, key=lambda r: (r["arm"], int(r["chain"]), int(r["checkpoint"]))):
            lines.append(f"| {r['arm']}/{r['strategy']} | {r['chain']} | {r['checkpoint']} | "
                         f"{r.get('checkpoint_id', '')} | {str(r.get('notes', ''))[:80]} |")
        lines.append("")

    # Pinned-doc (CLAUDE.md) touch rate: fraction of checkpoints where the agent
    # tried to edit a pinned leveling doc (its edit was reverted). A behavioural
    # signal, e.g. does one arm lean on CLAUDE.md as memory more than the other.
    lines.append("## Pinned-doc touch rate (share of checkpoints the agent edited a pinned file)\n")
    lines.append("| arm/strategy | touch rate | checkpoints |")
    lines.append("|---|---:|---:|")
    for gk, grp in sorted(groups.items()):
        touched = sum(1 for r in grp if str(r.get("pinned_touched", "")).strip())
        rate = touched / len(grp) if grp else float("nan")
        lines.append(f"| {gk[0]}/{gk[1]} | {rate:.3f} | {touched}/{len(grp)} |")
    lines.append("")

    # Acceptance-tamper rate: share of checkpoints where the agent edited an
    # experimenter-owned acceptance test (restored before scoring). Non-zero means
    # the agent tried to change the tests rather than satisfy them.
    lines.append("## Acceptance-tamper rate (share of checkpoints the agent edited a test)\n")
    lines.append("| arm/strategy | tamper rate | checkpoints |")
    lines.append("|---|---:|---:|")
    for gk, grp in sorted(groups.items()):
        t = sum(1 for r in grp if str(r.get("acceptance_touched", "")).strip())
        rate = t / len(grp) if grp else float("nan")
        lines.append(f"| {gk[0]}/{gk[1]} | {rate:.3f} | {t}/{len(grp)} |")
    lines.append("")

    # Blast radius: how much PRE-EXISTING code each new rule disturbs. The
    # isolation signal. Low existing-fns-modified with rules landing as new files
    # means a requirement is added by ADDITION, not by editing working code. A
    # "zero-blast" checkpoint touched no existing function at all.
    def _num(r, f):
        v = _f(r.get(f))
        return 0.0 if math.isnan(v) else v

    lines.append("## Blast radius (pre-existing code disturbed per rule)\n")
    lines.append("| arm/strategy | existing-fns-modified /chain | zero-blast cps | new-files /chain | churn +/- /chain |")
    lines.append("|---|---:|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        nch = len({int(r["chain"]) for r in grp}) or 1
        fns = sum(_num(r, "existing_fns_modified") for r in grp)
        newf = sum(_num(r, "files_created") for r in grp)
        add = sum(_num(r, "churn_added") for r in grp)
        rem = sum(_num(r, "churn_removed") for r in grp)
        zero = sum(1 for r in grp
                   if str(r.get("existing_fns_modified", "")).strip() != ""
                   and _num(r, "existing_fns_modified") == 0)
        lines.append(f"| {gk[0]}/{gk[1]} | {fns / nch:.1f} | {zero}/{len(grp)} | "
                     f"{newf / nch:.1f} | +{add / nch:.0f}/-{rem / nch:.0f} |")
    lines.append("")

    # God-class, entry-handler bloat, package reach, and temporal coupling. The
    lines.append("## God-class, entry-handler, spread, temporal coupling\n")
    lines.append("`WMC_max` is the heaviest class whatever its role, so the arms can answer with "
                 "different KINDS of class (an entity of accessors vs a controller of decisions). "
                 "`WMC_handler` pins the measurement to the class the endpoint routes through in "
                 "both arms, and is the like-for-like god-class number.\n")
    lines.append("| arm/strategy | final WMC_max | final WMC_handler | handler class | final entry CC | mean pkgs/rule | mean re-edit rate |")
    lines.append("|---|---:|---:|---|---:|---:|---:|")
    for gk, grp in sorted(groups.items()):
        wmc_f = _final_mean(grp, "wmc_max")
        wmch_f = _final_mean(grp, "wmc_handler")
        hcls = Counter(str(r.get("wmc_handler_class") or "") for r in grp
                       if str(r.get("wmc_handler_class") or "").strip())
        hcls_s = hcls.most_common(1)[0][0] if hcls else ""
        ecc_f = _final_mean(grp, "entry_cc")
        pk = [_f(r.get("packages_touched")) for r in grp]
        pk = [v for v in pk if not math.isnan(v)]
        rr = [_f(r.get("reedit_rate")) for r in grp]
        rr = [v for v in rr if not math.isnan(v)]
        cell = lambda v: "" if math.isnan(v) else f"{v:.3g}"
        pk_m = f"{np.mean(pk):.2f}" if pk else ""
        rr_m = f"{np.mean(rr):.3f}" if rr else ""
        lines.append(f"| {gk[0]}/{gk[1]} | {cell(wmc_f)} | {cell(wmch_f)} | {hcls_s} | "
                     f"{cell(ecc_f)} | {pk_m} | {rr_m} |")
    lines.append("")

    # Cumulative change audit. Every metric above is SCOPED (source_globs, hotspot
    # subsystem, node closure) — necessary for arm-to-arm comparability, but it means
    # none of them can see work placed outside that scope. This recomputes the whole
    # run unscoped, base_ref -> tip over every changed file, and reports the two
    # buckets a CC sum structurally cannot contain (orphan / opaque). Failing it must
    # not lose the analysis that already succeeded, so it is best-effort: the summary
    # says the audit is missing rather than silently omitting the section.
    try:
        audit = cumulative_impact.run_audit(eff_cfg, run_id)
        lines += cumulative_impact.markdown_section(audit)
        audit_json = os.path.join(out_dir, "cumulative_impact.json")
        with open(audit_json, "w") as fh:
            json.dump({"run_id": run_id, "arms": audit}, fh, indent=2)
        print(f"Wrote {audit_json}")
    except Exception as exc:                       # noqa: BLE001 - reported, not raised
        print(f"  (cumulative change audit failed: {exc})")
        lines.append("## Cumulative change audit (base_ref -> chain tip)\n")
        lines.append(f"NOT AVAILABLE — the audit failed with: `{exc}`\n")

    # Class shape. The impact formula rewards small classes with little surrounding
    # complexity, and a `static` method in a tiny class is the cheapest way to satisfy
    # it — so a run can lower its score by trading container-managed beans for
    # procedural utilities without the code getting better. Nothing above would show
    # that; this counts what KIND of class each new rule landed in. Best-effort for
    # the same reason as the cumulative audit.
    try:
        shape = class_shape.run_audit(eff_cfg, run_id)
        lines += class_shape.markdown_section(shape)
        shape_json = os.path.join(out_dir, "class_shape.json")
        with open(shape_json, "w") as fh:
            json.dump({"run_id": run_id, "arms": shape}, fh, indent=2)
        print(f"Wrote {shape_json}")
    except Exception as exc:                       # noqa: BLE001 - reported, not raised
        print(f"  (class-shape audit failed: {exc})")
        lines.append("## Class shape (what kind of class holds a new rule)\n")
        lines.append(f"NOT AVAILABLE — the audit failed with: `{exc}`\n")

    # Plots
    for field, title in METRICS_TO_PLOT:
        out_png = os.path.join(out_dir, f"{field}.png")
        plot_metric(groups, field, title, out_png)
    # Purpose-built figures. The per-metric trajectory plot renders ONE field at a
    # time, so the conservation argument (two quantities, different units) and the
    # Lorenz display (a distribution, not a time series) need their own figures.
    custom = []
    for name, fn in (("conservation", plot_conservation), ("lorenz", plot_lorenz)):
        path = os.path.join(out_dir, f"{name}.png")
        try:
            fn(groups, path)
            if os.path.isfile(path):
                custom.append(name)
        except Exception as exc:                   # noqa: BLE001 - reported, not raised
            print(f"  ({name} figure failed: {exc})")
    strip_fields = ["ccdist_file_top5", "cum_change_top5", "ck_handler_lcom", "wmc_handler"]
    strip_path = os.path.join(out_dir, "chain_strip.png")
    try:
        plot_chain_strip(groups, strip_fields, strip_path)
        if os.path.isfile(strip_path):
            custom.append("chain_strip")
    except Exception as exc:                       # noqa: BLE001
        print(f"  (chain_strip figure failed: {exc})")
    if HAVE_MPL:
        lines.append("## Plots\n")
        for name in custom:
            lines.append(f"- `analysis/{name}.png`  **(purpose-built figure)**")
        for field, _ in METRICS_TO_PLOT:
            lines.append(f"- `analysis/{field}.png`")

    if chain_filter:
        lines.insert(1, f"\n> **PARTIAL RUN — NOT PUBLISHABLE.** Recomputed from chains "
                        f"{sorted(chain_filter)} only (`--chains`). Every CI here is built on a "
                        f"fraction of the chain-cluster sample. Re-run without `--chains` before "
                        f"quoting any number.\n")
    summary = os.path.join(out_dir, "summary.md")
    with open(summary, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Wrote {summary}" + ("" if HAVE_MPL else "  (matplotlib missing: no PNGs)"))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

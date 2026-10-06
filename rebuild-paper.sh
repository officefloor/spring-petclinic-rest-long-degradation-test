#!/usr/bin/env bash
# Full paper rebuild from the analysed runs. Pure-derive: no agent, no tokens,
# CPU and wall-clock only. Run AFTER reanalyze-all.sh has refreshed every
# results/<run>/records.concat.csv -- everything here reads those five files.
#
# Three stages, in order:
#   1. figures   paper/figures.sh re-renders all three PNGs from ../results and
#                copies them into paper/figures/. Refuses, naming the run, if any
#                required run has not been analysed.
#   2. stats     the three seeded stats scripts (Table 3, Table 7 + floor-effect,
#                Figure 2 per-family counts). main.tex has NO \input, so these
#                rows are HAND-PASTED into the paper and this script CANNOT edit
#                it. They are written to paper/generated-stats.txt for you to
#                reconcile. A changed number there means edit main.tex, then the
#                build below is what picks the change up.
#   3. build     paper/build.sh -> main.pdf + arxiv.tar.gz + abstract.txt, and
#                runs figures.sh --check so a stale figure surfaces as a warning.
#
# The build in stage 3 compiles whatever is CURRENTLY in main.tex. If stage 2
# emitted a number you had to paste in, re-run `cd paper && ./build.sh` after.
set -uo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
STATS="$ROOT/paper/generated-stats.txt"

echo "=== 1/3 figures  $(date -Is)"
( cd paper && ./figures.sh ) || { echo "    ! figures.sh FAILED"; exit 1; }

echo "=== 2/3 stats  $(date -Is)  (hand-pasted into main.tex; written here to reconcile)"
: > "$STATS"
{
  echo "# Generated $(date -Is) by rebuild-paper.sh from the five analysed runs."
  echo "#"
  echo "# NOTE TO CLAUDE updating paper/main.tex. The values below are authoritative."
  echo "# main.tex has no \\input, so every statistic lives in its prose and tables by"
  echo "# hand and can drift. Review the paper against this file. For each value here"
  echo "# (each ratio, spread, CI, correlation and per-family count) find where main.tex"
  echo "# reports it and confirm the number, the interval and the sign all agree. Where"
  echo "# they differ the paper is stale and this file is right, so update main.tex to"
  echo "# match. Do not invent a number that is not below, and do not alter a paper value"
  echo "# that has no counterpart here. Flag any main.tex figure that reads as derived"
  echo "# from these runs but appears nowhere in this file, so a human can check it."
} >> "$STATS"
run_stat() {  # $1 = label, rest = module + args
  local label="$1"; shift
  { echo; echo "## $label  ( $* )"; } >> "$STATS"
  if "$PY" -m "$@" >> "$STATS" 2>&1; then echo "    ok   $label"
  else echo "    ! FAIL $label  (traceback in $STATS)"; fi
}
run_stat "Table 3"                    tools.gallery.bootstrap_ratio --latex
run_stat "Table 7 + floor-effect"     tools.gallery.floor_effect --latex
run_stat "Figure 2 per-family counts" tools.gallery.plasticity_dist
echo "    wrote $STATS"

echo "=== 3/3 build  $(date -Is)"
( cd paper && ./build.sh ) || { echo "    ! build.sh FAILED"; exit 1; }

echo
echo "=== done $(date -Is)"
echo "  PDF    paper/main.pdf"
echo "  arXiv  paper/arxiv.tar.gz   abstract  paper/abstract.txt"
echo "  stats  $STATS"
echo "         ^ hand this file to Claude with paper/main.tex. Its header asks Claude to"
echo "           review the paper against these values and update any stale number, then"
echo "           re-run the build: cd paper && ./build.sh"

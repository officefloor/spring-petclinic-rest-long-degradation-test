#!/usr/bin/env bash
# Full blog metric-gallery rebuild from the analysed runs. Pure-derive: no agent,
# no tokens. Run AFTER reanalyze-all.sh. Reads each run's records.concat.csv and
# re-renders blog/metric-gallery/ : one PNG per metric (all five series, final
# phase shaded), a five-phase table under each, metrics.csv, and index.html.
#
# Default is the FULL gallery, which includes --stats (metrics.csv with the
# chain-bootstrap CIs, ~7 min). Set FAST=1 for an image-only refresh: every
# figure and the page, but no bootstrap stats (~25s).
#
#   ./rebuild-blog.sh          full gallery, with stats
#   FAST=1 ./rebuild-blog.sh   figures + page only, no stats
set -uo pipefail
cd "$(dirname "$0")"
PY="$PWD/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
LOG="results/blog-gallery.log"

if [ "${FAST:-0}" = 1 ]; then
  echo "=== blog gallery  FAST (figures + page, no stats)  $(date -Is)"
  "$PY" -m tools.gallery.metric_gallery 2>&1 | tee "$LOG"
else
  echo "=== blog gallery  full (figures + page + metrics.csv, ~7 min)  $(date -Is)"
  "$PY" -m tools.gallery.metric_gallery --stats 2>&1 | tee "$LOG"
fi
code=${PIPESTATUS[0]}
echo "=== done (exit $code)  $(date -Is)"
if [ "$code" -ne 0 ]; then
  echo "    ! metric_gallery FAILED - see $LOG"
  exit "$code"
fi
echo "  gallery  blog/metric-gallery/index.html"

#!/usr/bin/env bash
# Re-analyse every run with the placement suite. Pure-derive: no agent, no tokens,
# CPU and wall-clock only. Back up results/<run>/analysis first -- it is overwritten.
set -u
cd "$(dirname "$0")"
RUNS="${*:-blind-202608100006 blind-202609160027 blind-202609031757 blind-202609010045}"
for run in $RUNS; do
  echo "=== $run  $(date -Is)"
  # tee, not >: progress goes to the console AND the log. Each run is hours long and
  # emits one line per chain, so a bare redirect leaves the terminal silent throughout.
  # PIPESTATUS[0] is the analyzer's status -- $? would be tee's.
  ./.venv/bin/python -u -m harness.analyze --config config.yaml --run-id "$run" \
      2>&1 | tee "results/analyze-${run}.log"
  code=${PIPESTATUS[0]}
  echo "    exit=$code  $(date -Is)"
  [ $code -ne 0 ] && echo "    ! FAILED - see results/analyze-${run}.log"
done
echo "=== all done $(date -Is)"

#!/usr/bin/env bash
# Re-analyse every run with the placement suite. Pure-derive: no agent, no tokens,
# CPU and wall-clock only. Back up results/<run>/analysis first -- it is overwritten.
set -u
cd "$(dirname "$0")"
RUNS="${*:-blind-202608100006 blind-202609160027 blind-202609031757 blind-202609010045}"
for run in $RUNS; do
  echo "=== $run  $(date -Is)"
  ./.venv/bin/python -u -m harness.analyze --config config.yaml --run-id "$run" \
      > "results/analyze-${run}.log" 2>&1
  code=$?
  echo "    exit=$code  $(date -Is)"
  [ $code -ne 0 ] && echo "    ! FAILED - see results/analyze-${run}.log"
done
echo "=== all done $(date -Is)"

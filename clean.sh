#!/usr/bin/env bash
#
# Wipe all PetClinic-Evolve state so `./setup.sh` can rebuild from a clean slate.
#
# Removes:
#   - the arm repos and every evolve/<run_id>/... branch + worktree registration
#         ${COMPARE_DIR:-${HOME}/compare}              (mirrors setup.sh)
#   - the live working area: per-chain worktrees, <wt>-capture, and analyze's
#     recompute*/ scratch
#         work_root from config.yaml paths.work_root    (default ${HOME}/pe-work)
#   - the agent's history-less sandbox project dir (separate from work_root)
#         sandbox_root from config.yaml paths.sandbox_root  (default ${HOME}/sandbox)
#
# Does NOT touch this harness repo's tracked files. `.venv` is kept (setup.sh reuses
# it) unless you pass --venv; analyze output in results/ is kept unless you pass
# --results.
#
# Usage:  ./clean.sh [-y|--yes] [--venv] [--results]
#           -y/--yes   skip the confirmation prompt
#           --venv     also remove ${HARNESS_DIR}/.venv
#           --results  also remove ${HARNESS_DIR}/results (analyze output)
#
# Overrides:  COMPARE_DIR=<path>   WORK_ROOT=<path>   SANDBOX_ROOT=<path>
#
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${COMPARE_DIR:-${HOME}/compare}"

ASSUME_YES=0 REMOVE_VENV=0 REMOVE_RESULTS=0
for a in "$@"; do
  case "$a" in
    -y|--yes)   ASSUME_YES=1 ;;
    --venv)     REMOVE_VENV=1 ;;
    --results)  REMOVE_RESULTS=1 ;;
    -h|--help)  sed -n '2,23p' "$0"; exit 0 ;;
    *) echo "unknown option: $a (see --help)" >&2; exit 2 ;;
  esac
done

# work_root / sandbox_root: read from config.yaml paths.* so this stays in sync with
# the runner. Fall back to the documented defaults; WORK_ROOT= / SANDBOX_ROOT= override.
read_path() {  # $1 = key under `paths:` in config.yaml
  local py="$HARNESS_DIR/.venv/bin/python"
  [ -x "$py" ] || py="$(command -v python3 || true)"
  [ -n "$py" ] || return 0
  "$py" - "$HARNESS_DIR/config.yaml" "$1" <<'PY' 2>/dev/null || true
import os, sys
try:
    import yaml
    p = yaml.safe_load(open(sys.argv[1]))["paths"][sys.argv[2]]
    print(os.path.expandvars(os.path.expanduser(p)))
except Exception:
    pass
PY
}
WORK_ROOT="${WORK_ROOT:-$(read_path work_root)}";       WORK_ROOT="${WORK_ROOT:-${HOME}/pe-work}"
SANDBOX_ROOT="${SANDBOX_ROOT:-$(read_path sandbox_root)}"; SANDBOX_ROOT="${SANDBOX_ROOT:-${HOME}/sandbox}"

# Never rm -rf an empty string, "/", or a home/root directory.
safe_rm() {
  local t="$1"
  case "$t" in
    ""|"/"|"$HOME"|"$HOME/") echo "  refusing unsafe path: '$t'" >&2; exit 1 ;;
  esac
  rm -rf -- "$t"
}

echo "Harness:   $HARNESS_DIR"
echo "Compare:   $BASE"
echo "Work root: $WORK_ROOT"
echo "Sandbox:   $SANDBOX_ROOT"
[ "$REMOVE_VENV" = 1 ]    && echo "Also:      $HARNESS_DIR/.venv"
[ "$REMOVE_RESULTS" = 1 ] && echo "Also:      $HARNESS_DIR/results"
echo

if [ "$ASSUME_YES" != 1 ]; then
  read -r -p "Delete the above? This cannot be undone. [y/N] " reply
  case "$reply" in y|Y|yes|YES) ;; *) echo "aborted."; exit 0 ;; esac
fi

# 1. Prune worktree registrations in the arm repos first (best-effort; removing the
#    repos below drops their .git/worktrees registrations anyway).
for arm in spring officefloor; do
  repo="$BASE/$arm"
  [ -d "$repo/.git" ] && git -C "$repo" worktree prune 2>/dev/null || true
done

# 2. Live working area: worktrees + capture staging + analyze recompute*/ scratch.
if [ -d "$WORK_ROOT" ]; then echo "== removing work root  $WORK_ROOT"; safe_rm "$WORK_ROOT"; fi

# 2b. The agent's history-less sandbox project dir (separate from work_root).
if [ -d "$SANDBOX_ROOT" ]; then echo "== removing sandbox    $SANDBOX_ROOT"; safe_rm "$SANDBOX_ROOT"; fi

# 3. Arm repos (and every evolve/<run_id>/... branch + worktree registration).
if [ -d "$BASE" ]; then echo "== removing compare    $BASE"; safe_rm "$BASE"; fi

# 4. Optional extras.
if [ "$REMOVE_RESULTS" = 1 ] && [ -d "$HARNESS_DIR/results" ]; then
  echo "== removing results    $HARNESS_DIR/results"; safe_rm "$HARNESS_DIR/results"
fi
if [ "$REMOVE_VENV" = 1 ] && [ -d "$HARNESS_DIR/.venv" ]; then
  echo "== removing venv       $HARNESS_DIR/.venv"; safe_rm "$HARNESS_DIR/.venv"
fi

echo
echo "Clean complete. Rebuild with:  ./setup.sh"

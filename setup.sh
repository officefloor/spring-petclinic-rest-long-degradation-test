#!/usr/bin/env bash
#
# One-shot setup for PetClinic-Evolve. Creates the two arm repos under
# ${HOME}/compare and installs the Python deps into a local venv.
#
#   ${HOME}/compare/spring       -> branch spring-compare
#   ${HOME}/compare/officefloor  -> branch officefloor-compare
#
# Override the source fork with:  PETCLINIC_FORK=<git-url> ./setup.sh
#
set -euo pipefail

FORK="${PETCLINIC_FORK:-https://github.com/officefloor/spring-petclinic-rest.git}"
BASE="${COMPARE_DIR:-${HOME}/compare}"
HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Fork:    $FORK"
echo "Repos:   $BASE/{spring,officefloor}"
echo "Harness: $HARNESS_DIR"
echo

mkdir -p "$BASE"

clone_arm() {
  local dir="$1" branch="$2" path="$BASE/$1"
  if [ -d "$path/.git" ]; then
    echo "== $dir already present; fetching =="
    git -C "$path" fetch --all --quiet
  else
    echo "== cloning $dir ($branch) =="
    git clone --branch "$branch" "$FORK" "$path"
  fi
  git -C "$path" checkout "$branch"
  git -C "$path" rev-parse --abbrev-ref HEAD | sed "s/^/   on branch /"
}

clone_arm spring spring-compare
clone_arm officefloor officefloor-compare

echo
echo "== Python venv + deps =="
cd "$HARNESS_DIR"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "   venv ready at $HARNESS_DIR/.venv"

echo
echo "Setup complete."
echo
echo "IMPORTANT (headroom): spring-compare / officefloor-compare are the finished"
echo "comparison apps, so some of the 20 checkpoints may already be implemented and"
echo "will start green (no degradation signal). Strip those behaviours on the base"
echo "branches, or drop those checkpoints, before a real run."
echo
echo "Next:"
echo "  cd $HARNESS_DIR"
echo "  source .venv/bin/activate"
echo "  python -m harness.run_experiment --config config.yaml --dry-run"
echo "  python -m harness.run_experiment --config config.yaml --arm spring --chain 0 --max-checkpoints 1"

#!/usr/bin/env bash
#
# One-shot setup for PetClinic-Evolve. Creates the two arm repos under
# ${HOME}/compare and installs the Python deps into a local venv.
#
#   ${HOME}/compare/spring       -> branch spring-compare-no-tests
#   ${HOME}/compare/officefloor  -> branch officefloor-compare-no-tests
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

# Base branches MUST match config.yaml arms.*.base_ref. The *-no-tests branches carry
# the app plus its test dependencies but no pre-existing test suite, so the only tests in
# play are the harness-injected acceptance suite (see README "One-time repo setup").
clone_arm spring spring-compare-no-tests
clone_arm officefloor officefloor-compare-no-tests

echo
echo "== Python venv + deps =="
cd "$HARNESS_DIR"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "   venv ready at $HARNESS_DIR/.venv"

# ImpactGate (the impact_gated strategy's structural-impact gate). Optional: only the
# impact_gated strategy needs it. Installed editable from a sibling checkout if present,
# so `impact-gate` is on PATH inside this venv; otherwise the run uses config.yaml's
# impact_gate.cmd (default: the sibling ImpactGate venv binary). Override with IMPACT_GATE_SRC.
IG_SRC="${IMPACT_GATE_SRC:-${HOME}/ImpactGate}"
if [ -f "$IG_SRC/pyproject.toml" ]; then
  echo "== installing ImpactGate (editable) from $IG_SRC =="
  ./.venv/bin/pip install --quiet -e "$IG_SRC" && \
    echo "   impact-gate on PATH in venv (set impact_gate.cmd: [\"impact-gate\"] in config.yaml to use it)"
else
  echo "== ImpactGate source not found at $IG_SRC (only needed for --strategy impact_gated) =="
  echo "   set config.yaml impact_gate.cmd to your impact-gate binary, or IMPACT_GATE_SRC=<path> ./setup.sh"
fi

echo
echo "Setup complete."
echo
echo "IMPORTANT (headroom): the *-no-tests base branches are the finished"
echo "comparison apps, so some checkpoints may already be implemented and"
echo "will start green (no degradation signal). Strip those behaviours on the base"
echo "branches, or drop those checkpoints, before a real run."
echo
echo "Next:"
echo "  cd $HARNESS_DIR"
echo "  source .venv/bin/activate"
echo "  python -m harness.run_experiment --config config.yaml --test-mode blind --dry-run"
echo "  python -m harness.run_experiment --config config.yaml --test-mode blind --arm spring --chain 0 --max-checkpoints 1"

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

# Pinned clone/smell binaries for the Verbosity metric and the impact_gated quality gate.
# Neither was installed here before, which is how both runs measured Verbosity with the
# smell half silently switched off (see AGENTS.md gotchas). harness/quality_selftest.py
# asserts these exact versions and refuses to start a gated run on drift.
echo
echo "== quality tooling (jscpd + PMD) =="
if command -v npm >/dev/null 2>&1; then
  (cd "$HARNESS_DIR/tools" && npm ci --silent) && echo "   jscpd + ast-grep installed (tools/node_modules)"
else
  echo "   ! npm not found — jscpd will be unavailable and Verbosity's clone half will not run"
fi

# PMD supplies the Java smell rules (pmd-rules/java-wasteful.xml). SlopCodeBench's own 137
# Verbosity rules are language: python and cannot match these Java arms, so PMD replaced
# ast-grep as the smell detector. ~140MB unpacked, gitignored; the RULESET is committed.
PMD_VERSION="$(cat "$HARNESS_DIR/tools/pmd-version.txt" 2>/dev/null || echo '')"
if [ -z "$PMD_VERSION" ]; then
  echo "   ! tools/pmd-version.txt missing — skipping PMD"
elif [ -x "$HARNESS_DIR/tools/pmd/bin/pmd" ] \
     && "$HARNESS_DIR/tools/pmd/bin/pmd" --version 2>/dev/null | grep -q "PMD $PMD_VERSION"; then
  echo "   PMD $PMD_VERSION already installed (tools/pmd)"
else
  PMD_ZIP="$HARNESS_DIR/tools/pmd-dist.zip"
  PMD_URL="https://github.com/pmd/pmd/releases/download/pmd_releases/${PMD_VERSION}/pmd-dist-${PMD_VERSION}-bin.zip"
  echo "   downloading PMD $PMD_VERSION ..."
  if curl -sfL -o "$PMD_ZIP" "$PMD_URL"; then
    rm -rf "$HARNESS_DIR/tools/pmd"
    (cd "$HARNESS_DIR/tools" && unzip -q pmd-dist.zip && mv "pmd-bin-$PMD_VERSION" pmd)
    rm -f "$PMD_ZIP"
    echo "   PMD $PMD_VERSION installed (tools/pmd)"
  else
    echo "   ! PMD download failed — the smell half of Verbosity will not run"
  fi
fi

# CK supplies the Chidamber & Kemerer suite (lcom, lcom*, tcc, lcc, cbo, rfc, dit, noc,
# fanin/fanout) for harness/placement.py. Source-only via Eclipse JDT -- no compilation,
# so it runs over a materialised checkpoint tree exactly like lizard and PMD do. ~16MB,
# gitignored and pinned by tools/ck-version.txt + tools/ck-sha256.txt.
CK_VERSION="$(cat "$HARNESS_DIR/tools/ck-version.txt" 2>/dev/null || echo '')"
if [ -z "$CK_VERSION" ]; then
  echo "   ! tools/ck-version.txt missing — skipping CK (ck_* metrics will be BLANK, not zero)"
elif [ -f "$HARNESS_DIR/tools/ck/ck.jar" ] \
     && [ "$(sha256sum "$HARNESS_DIR/tools/ck/ck.jar" | cut -d' ' -f1)" \
          = "$(cut -d' ' -f1 < "$HARNESS_DIR/tools/ck-sha256.txt" 2>/dev/null)" ]; then
  echo "   CK $CK_VERSION already installed (tools/ck/ck.jar)"
else
  CK_URL="https://repo1.maven.org/maven2/com/github/mauricioaniche/ck/${CK_VERSION}/ck-${CK_VERSION}-jar-with-dependencies.jar"
  echo "   downloading CK $CK_VERSION ..."
  mkdir -p "$HARNESS_DIR/tools/ck"
  if curl -sfL -o "$HARNESS_DIR/tools/ck/ck.jar" "$CK_URL"; then
    # FAIL CLOSED on a hash mismatch, like the lizard/jscpd pins: a metric computed by
    # a different build of the tool is not comparable with the runs already recorded.
    if [ -f "$HARNESS_DIR/tools/ck-sha256.txt" ] \
       && [ "$(sha256sum "$HARNESS_DIR/tools/ck/ck.jar" | cut -d' ' -f1)" \
            != "$(cut -d' ' -f1 < "$HARNESS_DIR/tools/ck-sha256.txt")" ]; then
      echo "   ! CK sha256 MISMATCH — removing; ck_* metrics will not run"
      rm -f "$HARNESS_DIR/tools/ck/ck.jar"
    else
      echo "   CK $CK_VERSION installed (tools/ck/ck.jar)"
    fi
  else
    echo "   ! CK download failed — the ck_* cohesion/coupling metrics will not run"
  fi
fi

# ImpactGate (the impact_gated strategy's structural-impact gate). Optional: only the
# impact_gated strategy needs it. Installed editable from a sibling checkout if present,
# so `impact-gate` is on PATH inside this venv; otherwise the run uses config.yaml's
# impact_gate.cmd (default: the sibling ImpactGate venv binary). Override with IMPACT_GATE_SRC.
IG_SRC="${IMPACT_GATE_SRC:-${HOME}/ImpactGate}"
if [ -f "$IG_SRC/pyproject.toml" ]; then
  echo "== installing ImpactGate (editable) from $IG_SRC =="
  ./.venv/bin/pip install --quiet -e "$IG_SRC" && \
    echo "   impact-gate on PATH in venv (set impact_gate.cmd: [\"impact-gate\"] in config.yaml to use it)"
  # The gate CLI usually runs from ImpactGate's OWN venv (config.yaml impact_gate.cmd),
  # which pip never sees from here — so pin the same lizard there. A gate measured by a
  # different parser than metrics.py is not comparing like with like, and lizard 1.24.0
  # in particular scores any change to an @Entity/@Table class as 0 (see
  # requirements.txt / harness/parser_selftest.py).
  LIZARD_PIN="$(grep -iE '^lizard[=<>~]' "$HARNESS_DIR/requirements.txt" || echo lizard)"
  if [ -x "$IG_SRC/.venv/bin/pip" ]; then
    echo "== pinning $LIZARD_PIN in the impact-gate venv ($IG_SRC/.venv) =="
    "$IG_SRC/.venv/bin/pip" install --quiet "$LIZARD_PIN" && echo "   pinned"
  fi
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
echo "  python -m harness.parser_selftest --config config.yaml   # expect OVERALL: PASS"
echo "  python -m harness.run_experiment --config config.yaml --test-mode blind --dry-run"
echo "  python -m harness.run_experiment --config config.yaml --test-mode blind --arm spring --chain 0 --max-checkpoints 1"

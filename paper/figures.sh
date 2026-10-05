#!/usr/bin/env bash
#
# Regenerate the paper's figures from the analysis output and copy them in.
#
# Why this exists. `main.tex` and `figures/` are tracked, so the paper builds on
# a fresh clone with no harness, no venv and no `results/`. The figures are
# DERIVED from `results/<run>/records.concat.csv`, which is local and gitignored.
# That split is deliberate. It used to be bridged by two lines in README.md that
# covered Figure 1 only, so where Figures 2 and 3 came from was folklore. A copy
# step documented in a README is a copy step that drifts, so it lives here.
#
# This is NOT part of build.sh. build.sh must keep working for a reviewer who has
# the paper and nothing else, and regenerating a figure needs the whole harness
# toolchain plus five analysed runs. build.sh calls this with --check instead,
# which costs nothing and only warns.
#
# Usage:
#   ./figures.sh                 regenerate every figure and copy it in
#   ./figures.sh --only FIG      just one: plasticity | plasticity_dist | strict_pass
#   ./figures.sh --check         no render. Compare the tracked figures against
#                                the last gallery render and report drift. Exit 1
#                                if any differ or are missing.
#   ./figures.sh --dry-run       render, then report what WOULD be copied
#
# Overrides:
#   RESULTS=<dir>   analysis output to read   (default: ../results)
#   DEST=<dir>      where to copy the figures (default: ./figures)
#   PYTHON=<path>   interpreter               (default: ../.venv/bin/python, else python3)
#
set -euo pipefail
cd "$(dirname "$0")"

REPO_ROOT="$(cd .. && pwd)"
RESULTS="${RESULTS:-$REPO_ROOT/results}"
DEST="${DEST:-$PWD/figures}"
GALLERY_FIGS="$REPO_ROOT/blog/metric-gallery/figs"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then PYTHON="$REPO_ROOT/.venv/bin/python"
  else PYTHON="python3"; fi
fi

ONLY="" CHECK=0 DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --only)    ONLY="$2"; shift 2 ;;
    --check)   CHECK=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

# Every figure the paper includes, as: <file> <producing module> <extra args>.
# Driven off \includegraphics in main.tex below, so a figure added to the paper
# without an entry here is reported rather than silently skipped.
#
# metric_gallery renders one figure per metric and `--only` restricts it to the
# one the paper uses, which takes seconds instead of rendering the whole
# catalogue. All three tools write into blog/metric-gallery/figs by default.
FIG_TOOL_plasticity="tools.gallery.plasticity_fig"
FIG_TOOL_plasticity_dist="tools.gallery.plasticity_dist"
FIG_TOOL_strict_pass="tools.gallery.metric_gallery"
FIG_ARGS_strict_pass="--only strict_pass"
FIG_RFLAG_strict_pass="--results-dir"

figures_in_paper() {
  sed -n 's/.*\\includegraphics\[[^]]*\]{figures\/\([^}]*\)\.png}.*/\1/p' main.tex
}

mapfile -t FIGS < <(figures_in_paper | sort -u)
[ "${#FIGS[@]}" -gt 0 ] || { echo "No \\includegraphics{figures/*.png} in main.tex" >&2; exit 1; }

if [ -n "$ONLY" ]; then
  printf '%s\n' "${FIGS[@]}" | grep -qx -- "$ONLY" \
    || { echo "--only $ONLY: main.tex includes no figures/$ONLY.png" >&2; exit 2; }
  FIGS=("$ONLY")
fi

# ---------------------------------------------------------------------------
# --check: compare what is tracked against the last render. No work, no venv.
# ---------------------------------------------------------------------------
if [ "$CHECK" = 1 ]; then
  if [ ! -d "$GALLERY_FIGS" ]; then
    echo "   no gallery render at $GALLERY_FIGS, nothing to compare"
    exit 0
  fi
  stale=0
  for f in "${FIGS[@]}"; do
    a="$DEST/$f.png" b="$GALLERY_FIGS/$f.png"
    if   [ ! -f "$b" ]; then echo "   $f.png: not in the gallery render, skipped"
    elif [ ! -f "$a" ]; then echo "   $f.png: MISSING from $DEST"; stale=1
    elif cmp -s "$a" "$b";  then echo "   $f.png: up to date"
    else echo "   $f.png: STALE. $DEST holds an older render"; stale=1
    fi
  done
  [ "$stale" = 0 ] || {
    echo "   run ./figures.sh to refresh them" >&2
    exit 1
  }
  exit 0
fi

# ---------------------------------------------------------------------------
# Render. Every run the gallery tools read must be analysed first, so say which
# one is missing rather than letting a FileNotFoundError out of a tool.
# ---------------------------------------------------------------------------
# The run ids come from the tools themselves. Hardcoding them here would be a
# fourth copy of the condition list, and the one nobody updates.
missing=0
while read -r run; do
  [ -n "$run" ] || continue
  if [ ! -f "$RESULTS/$run/records.concat.csv" ]; then
    echo "   ! no $RESULTS/$run/records.concat.csv" >&2
    missing=1
  fi
done < <(cd "$REPO_ROOT" && "$PYTHON" -c "
from tools.gallery.metric_gallery import RUNS
print('\n'.join(r[1] for r in RUNS))
" 2>/dev/null)

if [ "$missing" = 1 ]; then
  echo "   Analyse the runs first:  ./reanalyze-all.sh" >&2
  exit 1
fi

copied=0 unchanged=0
for f in "${FIGS[@]}"; do
  key="${f//[^A-Za-z0-9_]/_}"
  tool_var="FIG_TOOL_$key" args_var="FIG_ARGS_$key" rflag_var="FIG_RFLAG_$key"
  tool="${!tool_var:-}" args="${!args_var:-}" rflag="${!rflag_var:---results}"
  if [ -z "$tool" ]; then
    echo "   ! figures/$f.png is in main.tex but no tool is mapped for it here" >&2
    echo "     add FIG_TOOL_$key at the top of this script" >&2
    exit 1
  fi

  echo "== $f.png  ($tool)"
  # shellcheck disable=SC2086
  (cd "$REPO_ROOT" && "$PYTHON" -m "$tool" "$rflag" "$RESULTS" $args) \
    || { echo "   ! $tool failed" >&2; exit 1; }

  src="$GALLERY_FIGS/$f.png"
  [ -f "$src" ] || { echo "   ! $tool wrote no $src" >&2; exit 1; }

  if cmp -s "$src" "$DEST/$f.png" 2>/dev/null; then
    echo "   unchanged"
    unchanged=$((unchanged + 1))
  elif [ "$DRY_RUN" = 1 ]; then
    echo "   [dry-run] would copy $src -> $DEST/$f.png"
  else
    mkdir -p "$DEST"
    cp "$src" "$DEST/$f.png"
    echo "   copied to $DEST/$f.png"
    copied=$((copied + 1))
  fi
done

echo
prefix=""; [ "$DRY_RUN" = 1 ] && prefix="[dry-run] "
echo "${prefix}${copied} figure(s) copied, ${unchanged} already current."
[ "$copied" = 0 ] || echo "Rebuild the PDF:  ./build.sh"

#!/usr/bin/env bash
#
# Build the paper.
#
# arXiv compiles with pdflatex, and `\pdfoutput=1` on line 1 is what tells it to
# do so. That line matters because every figure here is a PNG: without it arXiv
# may route the submission through latex + dvips, which cannot read PNG at all.
#
# The side effect is local. With `\pdfoutput=1` set, hyperref loads its pdfTeX
# driver (hpdftex.def), so the file no longer builds under a XeTeX engine such
# as tectonic. That is not a defect in the file. It means the file is targeted
# at the engine arXiv actually runs.
#
# So: use pdflatex when one is present, which builds the file exactly as
# submitted. Fall back to tectonic with that one line stripped, which verifies
# everything else (structure, tables, floats, references, figure paths) but is
# NOT a test of the submitted file.
#
set -euo pipefail
cd "$(dirname "$0")"

# The arXiv submission bundle. Packed on every build so it cannot drift from
# main.tex, which is exactly what happened when it was packed by hand. It is
# gitignored, because it is derived: main.tex and figures/ are tracked here, and
# the results CSVs are tracked in the run-data repository.
#
# The bundle also carries the RAW METRICS, the per-checkpoint records the whole
# paper is computed from, one CSV per run under anc/results/<run>/, plus the run
# key anc/results/README. The paper deliberately does NOT print the opaque run
# ids (blind-YYYYMMDDHHMM); that mapping belongs with the data, not in the prose,
# so it is kept here. Its source is the tracked, human-editable file
# paper/results-README.txt, packed into the bundle under the name
# anc/results/README (staged through a temp dir so the archive path is clean and
# results/ is never written to). Edit that file to change what ships, the same as
# editing main.tex.
#
# A reader who downloads the arXiv source therefore gets the data behind every
# table and figure AND the key to it, not only the typeset numbers. The CSVs, the
# README and the correctness-exclusions audit are included, but not the 31 MB of
# per-metric PNGs or the analysis
# logs under results/<run>/analysis/: those are DERIVED from the CSVs by the
# harness, and shipping them would bloat the source package toward arXiv's size
# limit with figures a reader can regenerate. These data files are packed under a
# top-level anc/ directory, which is exactly where arXiv looks for ancillary
# files: it ignores them for the build and lists them as named downloads on the
# abstract page, rather than leaving them loose beside main.tex.
pack() {
  local here; here="$(pwd)"
  local repo; repo="$(cd .. && pwd)"
  local csvs=()
  mapfile -t csvs < <(cd "$repo" && ls results/*/records.concat.csv 2>/dev/null)

  # Stage the tracked README under the name it ships as: results/README.
  local stage; stage="$(mktemp -d)"
  trap 'rm -rf "$stage"' RETURN
  local readme_member=()
  if [ -f "$here/results-README.txt" ]; then
    mkdir -p "$stage/results"
    cp "$here/results-README.txt" "$stage/results/README"
    readme_member=(-C "$stage" results/README)
  else
    echo "   ! paper/results-README.txt missing; bundle will have no run key" >&2
  fi

  # The correctness-exclusions audit, carried under anc/ with the rest of the data
  # (see the --transform rules below). It is the basis for the strict (adj) column
  # and the fairness figure.
  local doc_member=()
  if [ -f "$repo/docs/CORRECTNESS_EXCLUSIONS.md" ]; then
    doc_member=(-C "$repo/docs" CORRECTNESS_EXCLUSIONS.md)
  else
    echo "   ! docs/CORRECTNESS_EXCLUSIONS.md missing; bundle will omit the audit" >&2
  fi

  # The regeneration map: the command behind every table, figure and inline
  # number, so a reader can recompute all of it from the CSVs. Ships as
  # anc/REGENERATION. Tracked source is paper/regeneration.txt.
  local regen_member=()
  if [ -f "$here/regeneration.txt" ]; then
    regen_member=(-C "$here" regeneration.txt)
  else
    echo "   ! paper/regeneration.txt missing; bundle will omit the regeneration map" >&2
  fi

  # The data files ship under anc/ so arXiv lists them as ancillary downloads
  # rather than loose beside main.tex. These --transform rules rewrite only the
  # data member names at pack time: results/... (the CSVs and the staged README)
  # and the audit md. main.tex and figures/ do not match either rule, so they
  # stay at the bundle root where the pdflatex build needs them. GNU tar, matching
  # this script's existing mapfile/-C assumptions.
  local xform=(
    --transform='s,^results/,anc/results/,'
    --transform='s,^CORRECTNESS_EXCLUSIONS\.md$,anc/CORRECTNESS_EXCLUSIONS.md,'
    --transform='s,^regeneration\.txt$,anc/REGENERATION,'
  )
  if [ "${#csvs[@]}" -gt 0 ]; then
    tar czf arxiv.tar.gz "${xform[@]}" main.tex figures/ -C "$repo" "${csvs[@]}" "${readme_member[@]}" "${doc_member[@]}" "${regen_member[@]}"
  else
    echo "   ! no results/*/records.concat.csv found; packing paper only" >&2
    tar czf arxiv.tar.gz "${xform[@]}" main.tex figures/ "${readme_member[@]}" "${doc_member[@]}" "${regen_member[@]}"
  fi
  echo "Packed arxiv.tar.gz ($(tar tzf arxiv.tar.gz | grep -c . ) entries, $(du -h arxiv.tar.gz | cut -f1))"
}

# The abstract as plain text, for pasting into the arXiv and Zenodo submission
# forms. Same reasoning as arxiv.tar.gz and for the same reason it is gitignored:
# it is derived entirely from main.tex, and the version that was kept by hand
# drifted from the paper. Regenerating it on every build means the abstract that
# gets submitted is the abstract that is in the PDF.
#
# Each paragraph is written as ONE unwrapped line, separated by a blank line.
# That is deliberate and is the whole point of the file: both target fields are
# single-line-per-paragraph text areas, and source-style hard wrapping at 79
# columns pastes into Zenodo's description as ragged mid-sentence breaks.
#
# This runs BEFORE either engine, and does not depend on one. The abstract is a
# slice of the .tex source, not a product of the compile, so it is still produced
# on a machine with no TeX installed at all.
abstract() {
  local out=abstract.txt sprg offl
  # Expand the two arm macros from their own \newcommand definitions rather than
  # hardcoding the names here, so renaming an arm in main.tex cannot leave this
  # file quietly stale.
  sprg=$(sed -n 's/^\\newcommand{\\sprg}{\\textsc{\(.*\)}}$/\1/p' main.tex)
  offl=$(sed -n 's/^\\newcommand{\\offl}{\\textsc{\(.*\)}}$/\1/p' main.tex)
  if [ -z "$sprg" ] || [ -z "$offl" ]; then
    echo "WARNING: could not read the \\sprg/\\offl definitions from main.tex;" >&2
    echo "         $out may contain unexpanded macros." >&2
  fi

  # Slice the abstract environment, drop its two delimiter lines, then undo the
  # markup the abstract actually uses. The leftover check below is what catches
  # anything new that this list does not handle.
  sed -n '/^\\begin{abstract}$/,/^\\end{abstract}$/p' main.tex \
    | sed -e '1d' -e '$d' \
    | sed -E \
        -e 's/\\noindent//g' \
        -e "s/\\\\sprg\\{\\}/$sprg/g" \
        -e "s/\\\\offl\\{\\}/$offl/g" \
        -e 's/\\(emph|textbf|textit|texttt|textsc)\{([^}]*)\}/\2/g' \
        -e 's/\{,\}/,/g' \
        -e 's/``/"/g' -e "s/''/\"/g" \
        -e 's/\\([%$&_#])/\1/g' \
        -e 's/~/ /g' \
    | awk '
        NF   { para = (para == "" ? $0 : para " " $0); next }
        para { out = (out == "" ? para : out "\n\n" para); para = "" }
        END  { if (para != "") out = (out == "" ? para : out "\n\n" para)
               if (out != "") print out }' \
    > "$out"

  # Anything still carrying a backslash or a brace is markup this function did
  # not know about, which would otherwise be pasted into a submission form
  # verbatim. Warn loudly rather than failing: the PDF is the build's real
  # output, and a visible warning with the offending lines is more useful than
  # an aborted build.
  if grep -n '[\\{}]' "$out" >&2; then
    echo "WARNING: the lines above still contain LaTeX markup." >&2
    echo "         Teach abstract() in build.sh about it, or simplify the abstract." >&2
  fi

  # arXiv's abstract field caps at 1920 characters, so an abstract that grows past
  # it cannot be submitted as written. Checked on every build because the failure
  # surfaces at submission time otherwise, which is the worst moment to find it.
  local words chars
  words=$(wc -w < "$out" | tr -d ' ')
  chars=$(wc -c < "$out" | tr -d ' ')
  echo "Wrote $out ($words words, $chars characters, arXiv limit 1920)"
  if [ "$chars" -gt 1920 ]; then
    echo "WARNING: the abstract is $((chars - 1920)) characters over arXiv's 1920 limit." >&2
    echo "         Trim the abstract environment in main.tex before submitting." >&2
  fi
}

abstract

# Are the tracked figures the ones the current analysis produces? figures.sh
# --check compares them against the last gallery render without rendering
# anything, so it costs nothing and needs no venv. A WARNING, never a failure:
# a fresh clone has no blog/ render to compare against, and a reviewer building
# the paper has no business being blocked by the harness's output.
if [ -x ./figures.sh ]; then
  echo "== figures =="
  ./figures.sh --check || {
    echo "   WARNING: the figures above are stale. ./figures.sh refreshes them." >&2
    echo "   Building with what is in figures/ anyway." >&2
  }
  echo
fi

if command -v pdflatex >/dev/null 2>&1; then
  echo "pdflatex found: building the file exactly as submitted."
  pdflatex -interaction=nonstopmode -halt-on-error main.tex
  pdflatex -interaction=nonstopmode -halt-on-error main.tex   # twice, for refs
  echo "Built main.pdf"
  pack
  exit 0
fi

TEC="${TECTONIC:-tectonic}"
if ! command -v "$TEC" >/dev/null 2>&1; then
  echo "Neither pdflatex nor tectonic found. Install either, or set TECTONIC=/path/to/tectonic." >&2
  exit 1
fi

echo "No pdflatex. Falling back to tectonic with \\pdfoutput stripped."
echo "This checks the document but does NOT verify the submitted file byte for byte."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
grep -v '^\\pdfoutput=1$' main.tex > "$tmp/main.tex"
cp -r figures "$tmp/"
"$TEC" -X compile "$tmp/main.tex" >/dev/null
cp "$tmp/main.pdf" main.pdf
echo "Built main.pdf (verification build)"
pack

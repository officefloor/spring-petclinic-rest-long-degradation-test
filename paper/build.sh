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
# gitignored: every byte in it is already tracked as main.tex and figures/, so
# committing it would only add a large binary that churns on each rebuild.
pack() {
  tar czf arxiv.tar.gz main.tex figures/
  echo "Packed arxiv.tar.gz ($(tar tzf arxiv.tar.gz | grep -c . ) entries)"
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

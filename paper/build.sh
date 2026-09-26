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

if command -v pdflatex >/dev/null 2>&1; then
  echo "pdflatex found: building the file exactly as submitted."
  pdflatex -interaction=nonstopmode -halt-on-error main.tex
  pdflatex -interaction=nonstopmode -halt-on-error main.tex   # twice, for refs
  echo "Built main.pdf"
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

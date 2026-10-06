# The paper

Paper (v2): *Conserved amount, negotiable placement. Prompting perturbs one
architecture, an AI reviewer both*

> v2 adds a fifth condition (an AI reviewer), reports the four external-control
> conditions separately from it, drops the borrowed whole-application erosion
> measure, and recomputes every number from the corrected analysis. v1 is tagged
> `paper-v1` in the harness repository.

## What is here

| File | Purpose |
|---|---|
| `main.tex` | The paper. Self contained: no `.bib`, no `.bbl`, bibliography is a `thebibliography` environment. |
| `figures/plasticity.png` | Figure 1. |
| `figures/plasticity_dist.png` | Figure 2. |
| `figures/strict_pass_adj.png` | Figure 3 — strict pass with the two under-determined tests removed (the fair measure; the raw rate is the `strict` column of the correctness table). |
| `results-README.txt` | The run key. A static, tracked, human-editable description of which run is which condition (the opaque `blind-*` ids the paper deliberately does not print). `build.sh` packs it into `arxiv.tar.gz` as `results/README`, beside the CSVs. Edit it here, the same as editing `main.tex`. |
| `figures.sh` | Regenerates `figures/` from `../results/` and copies them in. `--check` reports drift without rendering, which `build.sh` runs on every build. |
| `setup.sh` | Installs both engines and the LaTeX packages `main.tex` needs. Run once. |
| `build.sh` | Builds the PDF. Uses `pdflatex` when present, else `tectonic` with a caveat (see below). |
| `main.pdf` | The built paper, 23 pages. Written by `build.sh` and **gitignored**, for the same reason as `arxiv.tar.gz` below: it is derivable from `main.tex` and `figures/`. |
| `arxiv.tar.gz` | The arXiv submission bundle. Packed by `build.sh` on every build, and **gitignored** (derived). Holds `main.tex`, `figures/`, the raw per-checkpoint metrics `results/<run>/records.concat.csv` (one CSV per run), and the run key `results/README` (from `results-README.txt`), and the correctness-exclusions audit `CORRECTNESS_EXCLUSIONS.md`, so a reader of the arXiv source has the data behind every table and figure, the key to which run is which, and the basis for the `strict (adj)` measure. The derived per-metric PNGs and logs under `results/<run>/analysis/` are left out, to keep the source package small, and they regenerate from the CSVs. ~3 MB. |
| `abstract.txt` | The abstract as plain text, for pasting into the arXiv abstract field and the Zenodo description. Written by `build.sh` on every build from `main.tex`'s `abstract` environment, and **gitignored** for the same reason as the two above. Each paragraph is **one unwrapped line**, blank-line separated, because both fields take text that way and 79-column source wrapping pastes into Zenodo as ragged mid-sentence breaks. The build prints the character count and warns past arXiv's 1920 limit. Regenerated before the compile and needs no TeX, so `./build.sh` refreshes it even with no LaTeX installed. |

## Build

```
./setup.sh     # once: installs the engines and packages
./build.sh
```

`setup.sh` installs TeX Live (`pdflatex`) from apt and Tectonic as a pinned
static binary under `~/.local/bin`, then checks every `\usepackage` in
`main.tex` resolves. Only the apt half needs root. It is idempotent, and
`SKIP_TEXLIVE=1` skips the part that does, leaving a tectonic-only setup that
builds the paper without root but carries the caveat below. If you already have
a TeX distribution, skip `setup.sh` entirely.

`pdflatex main.tex` twice also works, and is exactly what arXiv does, but it
will not repack `arxiv.tar.gz`. Use `build.sh` and both artifacts stay in step.

### The one engine caveat

Line 1 is `\pdfoutput=1`. arXiv scans the first five lines for it and uses it to
select `pdflatex`. That matters here because every figure is a PNG: without the
line, arXiv may route the submission through `latex` + `dvips`, which cannot
read PNG.

The side effect is that `hyperref` then loads its pdfTeX driver, so the file no
longer builds under a XeTeX engine such as `tectonic`. That is not a defect. It
means the file targets the engine arXiv runs. `build.sh` falls back to tectonic
with that single line stripped, which checks structure, tables, floats,
references and figure paths, but is **not** a test of the submitted file. If you
have `pdflatex`, use it, because that path builds the file exactly as submitted.

## Reproducing the numbers

Every figure in the paper is derived from the analysed runs in `../results/`.
The condition to run mapping is NOT repeated here, because a copy in a README is
a copy that goes stale. It lives in `tools/gallery/metric_gallery.py` as `RUNS`,
and `figures.sh` reads it from there. To print it:

```
python -c "from tools.gallery.metric_gallery import RUNS
print('\n'.join(f'{c:18s} {r}' for c, r, _ in RUNS))"
```

All three figures are regenerated and copied in with:

```
./figures.sh                      # all of them
./figures.sh --only strict_pass   # just one
```

It refuses to run if a required run has not been analysed, and names the one it
is missing. `build.sh` calls `./figures.sh --check` on every build, which
compares the tracked figures against the last render and warns if they differ.
That check never fails the build: a fresh clone has no render to compare with.

The statistics in the tables come from three scripts, each seeded at 0 and each
taking `--latex` to emit its table rows verbatim:

| Script | Produces |
|---|---|
| `tools.gallery.bootstrap_ratio` | Tables 3 and 4: `S`, `R`, bootstrap intervals, `P(R>1)` |
| `tools.gallery.floor_effect` | Table 8 (room-normalised) and the floor-effect correlations |
| `tools.gallery.plasticity_dist` | Figure 2 and the per-family counts |
| `tools.gallery.paper_cells` | Tables 1, 2, 5, 6, 7, 9: amount, added, convergence, correctness, outcome, and the escape / duplication / money paragraphs |

Run them from the repository root, e.g. `python -m tools.gallery.floor_effect`.
The first three take `--conditions four|five|both`, so the four-condition spread
(the four external-control levers, the paper's primary statistic) and the
five-condition spread (adding the AI reviewer) are both reproducible from one
command. `paper_cells` carries the two base-tree values of the added table as
constants, with the command that re-measures them in its module header.

## Publishing

arXiv primary class is `cs.SE`. The Zenodo DOI is reserved and printed under the
author block in `main.tex` (`\thedoi`). Nothing outside this directory is needed
to build or submit the paper.

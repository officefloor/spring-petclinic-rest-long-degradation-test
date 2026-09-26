# The paper

Paper: *Conserved amount, negotiable placement: prompting moves one
architecture's complexity distribution and not the other's*

## What is here

| File | Purpose |
|---|---|
| `main.tex` | The paper. Self contained: no `.bib`, no `.bbl`, bibliography is a `thebibliography` environment. |
| `figures/plasticity.png` | Figure 1. |
| `figures/plasticity_dist.png` | Figure 2. |
| `figures/strict_pass.png` | Figure 3. |
| `build.sh` | Builds the PDF. Uses `pdflatex` when present, else `tectonic` with a caveat (see below). |
| `main.pdf` | Last local build, 17 pages. |
| `arxiv.tar.gz` | The arXiv submission bundle. Packed by `build.sh` on every build, and **gitignored**: every byte in it is already tracked as `main.tex` and `figures/`. |

## Build

```
./build.sh
```

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

Every figure in the paper comes from the four runs in `../results/`:

| Condition | Run |
|---|---|
| `just-solve` | `blind-202608100006` |
| `cohesion-prompt` | `blind-202609160027` |
| `impact-gated` (advisory) | `blind-202609031757` |
| `formula-provided` | `blind-202609010045` |

Figure 1 is regenerated with:

```
python -m tools.gallery.plasticity_fig
cp ../blog/metric-gallery/figs/plasticity.png figures/
```

## Publishing

Submission steps, the Zenodo checklist and the endorsement draft are in
`~/work-paper-todo/`. Nothing there is needed to build the paper.

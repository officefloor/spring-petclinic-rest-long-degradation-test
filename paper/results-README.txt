Raw metrics for the paper
  "Conserved amount, negotiable placement.
   Prompting perturbs one architecture, an AI reviewer both"

This directory holds the per-checkpoint metric records the paper is computed
from, one CSV per condition. The paper itself does not print run ids, script
names, repository URLs or branch names; this file is where all of that lives, and
it is packed into the arXiv source beside the CSVs.

Each results/<run>/records.concat.csv holds the record for one condition. Rows
are 2 arms x 10 chains x 60 change requests = 1200, over 280 metric columns. The
arm column is "spring" (the mutative Spring controller) or "officefloor" (the
additive OfficeFloor pipeline). The phase column bins each chain's 60 change
requests into fifths (Start, Early, Mid, Late, Final); the paper's "final phase"
is the rows with phase == Final, change requests 49-60.


THE FIVE RUNS, in the order the paper's tables use

  condition         what it is                                   run (<run>)         date        branch strategy
  just-solve        control, the change request alone            blind-202608100006  2026-08-10  just-solve
  cohesion-prompt   a plain-language request for cohesion        blind-202609160027  2026-09-16  cohesion-prompt
  impact-gated      a quality gate plus one guided refactor      blind-202609031757  2026-09-03  impact_gated
  formula-provided  the structural cost function in the prompt   blind-202609010045  2026-09-01  impact_gated
  ai-reviewed       an independent AI reviewer, author resumed   blind-202609290948  2026-09-29  reviewed

The formula-provided and impact-gated runs share the branch strategy name
"impact_gated" because the formula run predates the later "advisory" enforcement
mode. Each chain's committed configuration snapshot is the authority on which is
which.


CORRECTNESS, AND THE TWO UNDER-DETERMINED TESTS

Each CSV carries two strict-pass columns. strict_pass is the raw rate, every
selected test green. strict_pass_adj is the same with two tests removed whose own
specification does not determine the right answer, so scoring them measures which
defensible reading a run took rather than whether it was correct. The paper's
correctness figure is drawn on the adjusted rate and the table reports both. The
two removed tests are Cp28Tests#coreIdentityCollisionWithComputedHousehold (from
change request 36) and Cp51Tests#coreCapsLevelByHousehold (from change request
51). Fifteen other tests that fail on first appearance, including the two highest
failure rates, are KEPT, because their spec does determine the answer and failing
them is non-compliance. The full audit, the method, the two diagnostics that
separate an ambiguity from a defect, and the basis for every test kept as well as
the two dropped, is in CORRECTNESS_EXCLUSIONS.md, packed beside this file.


BASE EACH RUN STARTS FROM

Every run of an arm starts from one fixed base commit, the application plus the
injected acceptance suite and no pre-existing tests. The sixty change requests
are applied on top of it. These base branches live in the run-data repository
below.

  arm          base branch
  spring       spring-compare-no-tests
  officefloor  officefloor-compare-no-tests

Measured on those base commits, the amount metrics the paper's "added" table
subtracts are: spring total_cc 404, Halstead 153297, ck_wmc 518; officefloor
total_cc 351, Halstead 152798, ck_wmc 431.


REPOSITORIES

  harness    the frozen change-request plan, the acceptance suite, the
             measurement and analysis code, and the per-checkpoint records
             https://github.com/officefloor/spring-petclinic-rest-long-degradation-test

  run data   the codebases themselves, one branch per chain, each checkpoint a
             commit carrying its transcript, diff, build log and measurement
             record; branches are named evolve/<run>/<strategy>/<arm>/chain<n>,
             and the base branches above are in the same repository
             https://github.com/officefloor/spring-petclinic-rest

The commit in the harness repository that produced this version of the paper is
tagged paper-v2.


REPRODUCING THE NUMBERS

Every metric is recomputed from the committed source by the harness, not read
back from anything an agent wrote. From the harness repository root, with its
virtualenv Python, each script below reads these same CSVs and takes its
randomness from a fixed default seed of 0.

  script                                produces
  tools/gallery/bootstrap_ratio.py      the intervention spread S, the plasticity
                                        ratio R, their bootstrap intervals and
                                        P(R>1), for the four-condition and the
                                        five-condition spread tables.
                                        --conditions four|five|both
  tools/gallery/floor_effect.py         the room-normalised floor-effect table and
                                        the floor-effect correlations.
                                        --conditions four
  tools/gallery/plasticity_dist.py      the whole-distribution figure and the
                                        per-metric-family counts.
                                        --conditions four|five|both
  tools/gallery/paper_cells.py          the amount, added, convergence, AI-review
                                        convergence, correctness and outcome cell
                                        numbers, and the escape / duplication /
                                        money paragraphs.
  tools/gallery/plasticity_fig.py       the per-condition movement figure.
  tools/gallery/metric_gallery.py       the strict-pass figure (via figures.sh).

paper/rebuild-paper.sh runs the figures, writes the reconciliation stats, and
builds the PDF in one pass. paper/results-README.txt (this file) is the source of
results/README in the arXiv bundle; edit it there, in the harness repository.

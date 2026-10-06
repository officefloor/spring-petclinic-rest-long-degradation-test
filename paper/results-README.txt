Raw metrics for the paper
  "Conserved amount, negotiable placement. External instruction moves one
   architecture's complexity distribution, and an AI reviewer moves the other's"

This directory holds the per-checkpoint metric records the paper is computed
from, one CSV per condition. The paper itself does not print the opaque run ids;
this file is the key that maps each run to its condition, and it is packed into
the arXiv source beside the CSVs.

Each results/<run>/records.concat.csv holds the record for one condition. Rows
are 2 arms x 10 chains x 60 change requests = 1200, over 280 metric columns. The
arm column is "spring" (the mutative Spring controller) or "officefloor" (the
additive OfficeFloor pipeline). The phase column bins each chain's 60 change
requests into fifths (Start, Early, Mid, Late, Final); the paper's "final phase"
is the rows with phase == Final, change requests 49-60.

The five runs, in the order the paper's tables use:

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

Full run data (every checkpoint commit, agent transcript, diff, build log) lives
in the run-data repository, one branch per chain, named
evolve/<run>/<strategy>/<arm>/chain<n>. The analysis code that recomputes every
table and figure in the paper from these CSVs is in the harness repository.

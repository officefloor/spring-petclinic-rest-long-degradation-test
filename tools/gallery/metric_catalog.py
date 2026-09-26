"""Plain-language catalogue of every metric the gallery plots.

This is the prose half of `metric_gallery.py`. The numbers come from the run
CSVs. This file says what each number MEANS and exactly how it is calculated, so
a reader who has never seen the experiment can look at one figure in isolation
and know both what they are looking at and how it was produced.

Each entry carries:
  title      the heading for that metric's blog section
  group      which section of the gallery it belongs to (see GROUPS)
  direction  "down" (lower is better), "up" (higher is better), "flat"
             (no direction: a prediction of NO difference), or "" (descriptive)
  source     the published definition, or the tool that computes it
  what       what the metric is, in plain language, at some length
  formula    the equation, as inline HTML. This is the field that makes a figure
             self-contained: a reader should be able to recompute the number
  terms      what every symbol in `formula` means, and over what scope it is summed
  how        how it is obtained in this harness: which tool, which files, when
  read       how to read the figure, and what a gap between the arms MEANS
  caveat     the known way to misread it (optional; from AGENTS.md's gotchas)

Formulas are written in Unicode and inline HTML, NOT LaTeX and not MathJax.
The destination is a Blogger post, and a post body cannot rely on an external
script or stylesheet loading. Sigma, square root, superscripts and <sub>/<sup>
render everywhere with no dependency at all.

Every formula here was read off the implementation, not off the paper. Where the
harness deviates from the published definition the deviation is stated. The
relevant sources are `harness/metrics.py` (erosion, verbosity, blast radius,
WMC, the node walk, the impact score, re-edit rate), `harness/placement.py` (the
concentration indices, Halstead, Maintainability Index, indirection,
propagation, change entropy, the CK and PMD readers) and
`harness/correctness.py` (the suite outcomes).

HOUSE STYLE for every string in this file. It is published prose, read by
working engineers, so it is held to the blog's rules:
  * Short sentences. One idea each.
  * NO dash punctuation. No em dash, no en dash, no spaced hyphen. If a dash
    wants to appear it means two sentences got joined. Break it there, or use a
    colon. Hyphenated compound words such as "scale-free" are fine.
  * Say the connecting word. Write "because", "so", "which means". Do not let a
    dash stand in for it.
  * Inline HTML is the markup that reaches the page: <b>, <i>, <code>, <sub>,
    <sup>. Markdown emphasis is NOT rendered, so never use asterisks.
  * `metric_gallery.py` asserts all of this at import. It refuses to build the
    page if a dash or a markdown asterisk creeps back in.

Definitions are kept consistent with the README "Metrics glossary" and the
AGENTS.md decisive-statistics section. When a metric's definition changes in
`harness/metrics.py` or `harness/placement.py`, update the entry here too, the
`formula` field included.
"""

# --------------------------------------------------------------------------
# Section order for the generated post. Each group gets a heading and a short
# intro that frames the PREDICTION for the metrics inside it. The three
# structural groups predict opposite things, and a reader who does not know
# that will read the "tax" group as evidence against the thesis.
# --------------------------------------------------------------------------
GROUPS = [
    ("outcome", "What it cost and whether it stayed correct",
     "These are the outcome measures: money, time, and whether the accumulated "
     "rules kept working. Nothing here is structural. They are the things a team "
     "actually feels. They come first because every structural number later on is "
     "only interesting if it predicts one of these."),

    ("amount", "How much complexity there is",
     "Tesler's conservation law says a problem has an irreducible amount of "
     "complexity: architecture moves it, it does not delete it. So the prediction "
     "for every metric in this group is <b>no difference between the two "
     "architectures</b>. Four independent operationalisations are used: control "
     "flow, cognitive nesting, execution paths, and vocabulary size. If all four "
     "agree, the conservation claim does not rest on McCabe alone. If these came "
     "out different, the experiment would be measuring the workload rather than "
     "the architecture."),

    ("placement", "Where the complexity sits",
     "This is the thesis. The same total complexity can end up pooled in one god "
     "method or spread across many small units. These metrics measure which. The "
     "prediction is that the <b>concentrated</b> arm scores worse, and keeps "
     "getting worse as rules accumulate."),

    ("comprehension", "What you must understand to change one rule",
     "Concentration metrics can be gamed by moving code somewhere else. These "
     "cannot. They follow the call graph out from the endpoint and add up "
     "everything reachable, so work pushed downstream still counts. This is the "
     "group to lead with whenever an arm has been prompted or tooled toward a "
     "structural target."),

    ("blast", "How much existing code each rule disturbs",
     "Blast radius. For one change request, how much already-working code had to "
     "be opened, and how widely the diff spread. An architecture where each new "
     "rule is a new file has a blast radius near zero by construction. One where "
     "every rule edits the same method does not."),

    ("impact", "The structural-impact score",
     "A single score combining blast radius with the complexity of the context "
     "that was disturbed. Editing a method inside a heavy god class costs far more "
     "than the same edit inside an isolated unit. This score was defined <i>on "
     "this experiment</i>, so it cannot be the evidence for a claim about this "
     "experiment. It is reported because it is the quantity the impact-gated and "
     "formula-provided conditions were optimising."),

    ("cohesion", "Cohesion: does a class do one thing",
     "Cohesion asks whether the methods of a class use the same fields. It asks "
     "whether the class is one idea or several stapled together. These are the "
     "measures the plain-English cohesion prompt was asking for in words."),

    ("tax", "The price of distributing",
     "These are the <b>counter-signals</b>. They are measures where spreading "
     "logic across many small units is expected to score <i>worse</i>. Brooks' "
     "accidental complexity, indirection, coupling. They are published here rather "
     "than left for a reviewer to find, because an honest comparison has to price "
     "both sides."),

    ("duplication", "Duplication and boilerplate",
     "Splitting logic into many units creates the opportunity to copy code "
     "between them. This group measures whether that happened."),

    ("validity", "Validity guards",
     "Not findings. Guards. Each of these answers “can the tools still see the "
     "code?”. If one of them moves, some other number on this page is lying, and "
     "the caveat says which."),
]

# --------------------------------------------------------------------------
# The catalogue. Order within a group is the order of the generated sections.
# --------------------------------------------------------------------------
M = {}


def _add(key, **kw):
    M[key] = kw


# Reusable term text. Several metrics share the same underlying population, and
# repeating the definition in twenty entries guarantees the twenty copies drift.
PROD_JAVA = ("The population is <b>production Java only</b>, meaning the files "
             "matched by the arm's <code>source_globs</code> at that checkpoint's "
             "commit. Tests are excluded. OfficeFloor's YAML wiring is counted in "
             "a separate pool and is never folded into a Java denominator, because "
             "mixing them would let a wiring-based architecture dilute any "
             "per-line metric.")
CC_DEF = ("<b>CC(f)</b> is the cyclomatic complexity of function <i>f</i>, as "
          "reported by <code>lizard</code>: one plus the number of decision "
          "points, counting <code>if</code>, <code>for</code>, <code>while</code>, "
          "<code>case</code>, <code>catch</code>, the ternary operator, and each "
          "<code>&amp;&amp;</code> or <code>||</code>.")
CHAIN_AGG = ("Each figure plots the mean across the ten independent runs at that "
             "change request. The band is one standard deviation across those ten.")


# =========================================================================
# OUTCOME: cost, time, and whether it stayed correct
# =========================================================================
_add("cost_usd",
     title="Cost per change request (USD)",
     group="outcome", direction="down",
     source="Anthropic API billing, as reported by the agent CLI per turn",
     what="What one change request cost to implement, in dollars of model usage. "
          "Each change request is a fresh agent session with no memory of the "
          "previous one, so this is the whole cost of reading enough of the "
          "codebase to understand it, deciding what to do, and writing the code. "
          "It is the most direct answer to the question the whole experiment "
          "exists to ask, which is whether architecture changes what maintenance "
          "costs as a system accumulates rules.",
     formula="cost = input&nbsp;tokens &middot; p<sub>in</sub> "
             "+ cache&nbsp;reads &middot; p<sub>cache</sub> "
             "+ output&nbsp;tokens &middot; p<sub>out</sub>",
     terms="The agent CLI reports this figure directly, so the harness does not "
           "compute it. The three <b>p</b> terms are the model's published per "
           "token prices, which differ: a cache read is billed well below a fresh "
           "input token, and an output token well above both. Only the implement "
           "turn is counted. The gate's refactor turns and the cold-reader probe "
           "are billed to their own separate fields." + " " + CHAIN_AGG,
     how="Read from the agent's terminal JSON for the implement turn at that "
         "checkpoint. No modelling and no estimation.",
     read="A rising line means each successive rule costs more than the last. The "
          "codebase is getting more expensive to change. A flat line means the "
          "sixtieth rule costs about what the first one did. The gap between the "
          "arms at the right hand edge is the compounding penalty for the "
          "architecture.",
     caveat="Cost mixes reading and writing. A run can also get cheaper by giving "
            "up. Read it beside the correctness metrics, never alone.")

_add("duration_api_ms",
     title="Model inference time per change request",
     group="outcome", direction="down",
     source="agent CLI, API time excluding local tool execution",
     what="How long the model spent thinking and generating for one rule, in "
          "milliseconds. It excludes the time spent running Maven, booting a JVM "
          "and executing tests. That exclusion matters: wall-clock time is "
          "dominated by the build, which is a property of the toolchain and not of "
          "the architecture, so wall-clock would bury the signal under noise.",
     formula="duration_api_ms = &Sigma;<sub>requests in the turn</sub> "
             "(response&nbsp;received &minus; request&nbsp;sent)",
     terms="Summed over every model request the implement turn made, which is one "
           "per agent step. Local tool execution happens between requests and is "
           "therefore not inside any of the intervals. " + CHAIN_AGG,
     how="Read from the agent's <code>duration_api_ms</code> for the implement "
         "turn. The harness also records <code>duration_ms</code>, the wall-clock "
         "figure, which is not plotted for the reason given above.",
     read="This tracks cost closely, and for the same reason: more context to read "
          "and more code to write. It is the independent confirmation that a cost "
          "difference is real work rather than a billing artefact.")

_add("cache_read_tokens",
     title="Cache-read tokens: the comprehension proxy",
     group="outcome", direction="down",
     source="agent CLI token accounting",
     what="How much existing context the agent had to pull back in to make the "
          "change. This is the closest available proxy for the question that "
          "actually matters to a team, which is how much of this codebase you have "
          "to understand before you can safely touch it. Every checkpoint is a "
          "fresh session, so nothing carries over from the last rule. Whatever the "
          "agent reads, it reads again from scratch.",
     formula="cache_read_tokens = tokens served from the prompt cache during the "
             "implement turn",
     terms="A token is roughly three quarters of an English word, or a few "
           "characters of source. The figure counts prompt content the API served "
           "from cache rather than re-processing. It includes the harness's own "
           "fixed instructions, which are constant across both arms and all four "
           "conditions, so the constant part cancels when arms are compared. "
           + CHAIN_AGG,
     how="Read from the agent's token accounting for the implement turn. The "
         "harness never uses session resume, so no prior conversation is ever read "
         "back. The only thing crossing between checkpoints is the code itself.",
     read="Rising means the agent has to hold more of the system in its head to "
          "add one rule. That is the machine analogue of a developer's ramp-up "
          "time, and it is the outcome the concentration metrics are meant to "
          "predict.",
     caveat="It is a proxy. The constant harness prompt is part of the total, so "
            "read the trend and the arm gap rather than the absolute level.")

_add("num_turns",
     title="Turns taken per change request",
     group="outcome", direction="down",
     source="agent CLI",
     what="How many agent steps the implement turn took. One step is one model "
          "response plus whatever tools it called. It is a rough measure of how "
          "much trial and error the change needed, because a first attempt that "
          "compiles and passes ends the turn quickly.",
     formula="num_turns = count of agent steps until the implement turn completes",
     terms="Counted by the agent CLI. A step that only reads a file counts the "
           "same as a step that rewrites one. " + CHAIN_AGG,
     how="Read from the agent's <code>num_turns</code> for the implement turn.",
     read="A codebase that fights back produces more turns. Read it with cost, "
          "which it partly drives.")

_add("output_tokens",
     title="Output tokens per change request",
     group="outcome", direction="",
     source="agent CLI",
     what="How much text the model generated for one rule. That covers the code it "
          "wrote, the edits it issued, and its own reasoning.",
     formula="output_tokens = tokens generated by the model during the implement turn",
     terms="Output tokens are the most expensive of the three billing categories, "
           "so this is also the largest single driver of the cost line. " + CHAIN_AGG,
     how="Read from the agent's token accounting for the implement turn.",
     read="Mostly a size signal rather than a quality one. Its real use is as a "
          "sanity check that a cheaper arm is not simply doing less work.")

_add("strict_pass",
     title="Strict pass rate: was everything green after this rule",
     group="outcome", direction="up",
     source="SWE-CI (arXiv:2603.03823) gate semantics",
     what="Whether every selected test was green after the change. That means this "
          "rule's own tests plus every earlier rule's tests. The suite is "
          "black-box and the agent never sees it. This is the safety headline of "
          "the whole experiment, because a rule landed at the cost of breaking two "
          "earlier ones is not progress.",
     formula="strict_pass(c) = 1 if passed(c) = selected(c), else 0"
             "<br>plotted value = (1/K) &Sigma;<sub>k=1..K</sub> strict_pass<sub>k</sub>(c)",
     terms="<b>c</b> is the change request, numbered 1 to 60. <b>selected(c)</b> is "
           "every test belonging to change requests 1 through <i>c</i>. "
           "<b>passed(c)</b> is how many of them were green. <b>K</b> is 10, the "
           "number of independent runs, so the plotted value is the fraction of "
           "runs that were fully green at that change request.",
     how="The harness runs the selected Surefire tests after every checkpoint and "
         "parses the XML. A checkpoint whose test run crashed is flagged invalid "
         "and excluded rather than scored, because a crashed fork reports a "
         "successful build with zero selected tests and would otherwise read as "
         "the entire prior suite regressing.",
     read="A line that sags toward the later change requests means the agent is "
          "landing new rules while quietly breaking old ones. Compare conditions "
          "here before believing any structural improvement. An intervention that "
          "improves structure while dropping this line has not made the codebase "
          "better.",
     caveat="Use this, and not the raw regression counts, to ask whether a "
            "condition held the suite. A rule broken once and never repaired keeps "
            "failing here at every later change request, which is the honest "
            "accounting. The transition counts do not show it.")

_add("iso_pass",
     title="Isolated pass rate: did this rule itself work",
     group="outcome", direction="up",
     source="harness; the non-regression half of the suite",
     what="Whether the change request itself was implemented correctly, ignoring "
          "whether it broke anything earlier. Held up against the strict rate, it "
          "separates two very different failures: could not do the task, versus "
          "did the task and broke something else.",
     formula="iso_pass(c) = 1 if every Core, Error and Functionality test of change "
             "request <i>c</i> passes, else 0",
     terms="The acceptance suite is split into four families. <b>Core</b> is the "
           "happy path. <b>Error</b> is the rejection and edge-case behaviour. "
           "<b>Functionality</b> is hidden behaviour the agent was not told about. "
           "<b>Regression</b> is every earlier change request's tests. This metric "
           "uses the first three and excludes Regression by construction.",
     how="Same Surefire parse as the strict rate, filtered to this checkpoint's own "
         "three families.",
     read="A high isolated rate with a low strict rate is the signature of "
          "accumulating damage. The agent can still do each new task. It just "
          "cannot do it without breaking the last one.")

_add("core_pass",
     title="Core pass rate: is the endpoint still alive",
     group="outcome", direction="up",
     source="harness; the happy-path suite",
     what="Whether the basic happy path of the endpoint still works. Creating a "
          "valid owner and getting a 201 back.",
     formula="core_pass(c) = 1 if every Core test of change request <i>c</i> passes, "
             "else 0",
     terms="Core tests are the ones that must never fail. They are a small family "
           "per change request, so the denominator is small and the metric is "
           "coarse by design.",
     how="Same Surefire parse, filtered to the Core family.",
     read="Near 1.0 everywhere is expected. Any visible dip is a serious failure "
          "and is worth chasing in that run's own summary rather than here.")

_add("regressions",
     title="Regressions introduced at this checkpoint",
     group="outcome", direction="down",
     source="SWE-CI; pass to fail transitions",
     what="How many tests were green before this rule landed and red after it. It "
          "is a rate of new breakage, not a level of damage. It answers the "
          "question of what this one checkpoint broke.",
     formula="regressions(c) = | passing(c&minus;1) &setminus; passing(c) |",
     terms="<b>passing(c)</b> is the set of test identifiers green after change "
           "request <i>c</i>. The backslash is set difference, so the count is "
           "tests in the earlier set but not the later one. A test that was already "
           "red before this checkpoint cannot appear here.",
     how="The harness keeps the pass or fail map per checkpoint and differences "
         "consecutive maps by test identifier.",
     read="Spikes mark the change requests that broke things. It is a per event "
          "measure and does not accumulate.",
     caveat="Two conditions can have near-identical totals here while differing "
            "twentyfold in how many tests are standing broken at any moment. This "
            "metric does not re-count a rule that was broken earlier and never "
            "fixed. For how broken it is right now, use the strict pass rate.")

_add("true_regressions",
     title="Unintended regressions: the safety signal",
     group="outcome", direction="down",
     source="SWE-CI, with the harness's intended and unintended split",
     what="Regressions the change request did not ask for. Some change requests "
          "deliberately revise an earlier rule, and when they do, the earlier "
          "rule's tests are supposed to change. Those do not count here. What is "
          "left is the cleanest breakage signal on the page, because it means the "
          "agent broke something it was never asked to touch.",
     formula="true_regressions(c) = | (passing(c&minus;1) &setminus; passing(c)) "
             "&setminus; intended(c) |",
     terms="<b>intended(c)</b> is the set of earlier tests that change request "
           "<i>c</i> declared it would change, which the checkpoint plan records "
           "as its <code>mutates</code> list. For a purely additive change request "
           "<b>intended(c)</b> is empty, so every regression is a true one.",
     how="The <code>mutates</code> declaration lives in <code>checkpoints.yaml</code> "
         "beside the change request, so the intended set is fixed before any run "
         "starts and cannot be fitted to a result afterwards.",
     read="This is the number that means it broke something it was not asked to "
          "break. Flat at zero is the target.")

_add("normalized_change",
     title="Normalized change",
     group="outcome", direction="up",
     source="SWE-CI (arXiv:2603.03823)",
     what="A single score for how much the change moved the suite toward its "
          "target. It is positive for progress and negative for regression, and "
          "deliberately asymmetric: breaking things is scored against a different "
          "denominator from fixing them, so a small amount of breakage in a large "
          "suite is not lost in rounding.",
     formula="NC(c) = (passed &minus; base) / (target &minus; base) &nbsp;if "
             "passed &ge; base<br>"
             "NC(c) = (passed &minus; base) / base &nbsp;if passed &lt; base",
     terms="<b>base</b> is how many tests were passing before this change request. "
           "<b>passed</b> is how many are passing after it. <b>target</b> is the "
           "total number selected, which is the best achievable. The result lies "
           "in the range &minus;1 to 1. The improvement branch is progress toward "
           "what was still missing. The regression branch is loss measured against "
           "what already worked, which is why it bites harder.",
     how="Computed in <code>harness/correctness.py</code> from the same pass or "
         "fail maps as the other correctness fields. Degenerate denominators are "
         "guarded: a zero baseline scores &minus;1 on the regression branch and a "
         "zero gap scores 1 on the improvement branch.",
     read="A compact per checkpoint verdict. Its use is spotting which phase of the "
          "sixty rules a condition started losing ground in.")

_add("probe_recall",
     title="Cold-reader recall: can a fresh agent still find the rules",
     group="outcome", direction="up",
     source="harness read-only comprehension probe",
     what="A fresh agent with no history is dropped into the codebase and asked "
          "what business rules the create-owner endpoint enforces. This is the "
          "fraction it finds. It is the one metric here that measures "
          "comprehension directly rather than by proxy, which is why it is worth "
          "the cost of running it.",
     formula="probe_recall = | rules&nbsp;found | / | rules&nbsp;implemented&nbsp;so&nbsp;far |",
     terms="<b>rules implemented so far</b> is the change requests landed up to "
           "that checkpoint, which is known exactly because the plan is fixed. "
           "<b>rules found</b> is how many of them the probe named. The probe runs "
           "in its own session with no tools that can modify anything.",
     how="Run periodically rather than at every checkpoint, which is why the line "
         "is sparse. The probe's own cost and tokens are recorded separately from "
         "the implement turn so they never contaminate the cost line.",
     read="This is the comprehension outcome the whole experiment is about. Not "
          "whether the code is complex but whether a newcomer can find out what it "
          "does.",
     caveat="Sparse by design. Only a fraction of checkpoints carry a probe, so "
            "the line has few points and each one is noisier than a dense metric.")


# =========================================================================
# AMOUNT: prediction is NO arm difference (Tesler)
# =========================================================================
_add("total_cc",
     title="Total cyclomatic complexity",
     group="amount", direction="flat",
     source="McCabe 1976, via lizard",
     what="The total number of independent paths through the whole application. "
          "Every branch point in every function, summed. It is the standard answer "
          "to how much decision-making a codebase contains, and it is the primary "
          "test of Tesler's conservation law here: the sixty change requests "
          "demand a certain number of decisions, and no architecture can delete "
          "them.",
     formula="total_cc = &Sigma;<sub>f &isin; F</sub> CC(f)",
     terms="<b>F</b> is every function in production Java at that checkpoint's "
           "commit. " + CC_DEF + " " + PROD_JAVA,
     how="<code>lizard</code> parses every matched file and reports one record per "
         "function. The harness sums the cyclomatic complexity column. A parser "
         "that fails on a file yields no functions for it, which would make that "
         "file look free, so <code>parser_selftest</code> must pass before a run "
         "or an analysis is trusted.",
     read="The prediction is that the two lines <b>sit on top of each other</b>. If "
          "a condition lowers this, it either skipped work or pushed logic "
          "somewhere the parser cannot read. Check the validity group before "
          "celebrating.")

_add("pmd_cognitive_total",
     title="Total cognitive complexity",
     group="amount", direction="flat",
     source="Campbell / SonarSource 2018, via PMD",
     what="A complexity measure built around how hard code is for a human to "
          "follow, rather than how many paths it has. Nesting is penalised "
          "heavily. A long flat sequence of independent checks is forgiven. That "
          "makes it the one measure in this group that could separate a deeply "
          "nested god method from a long flat dispatch, which is exactly the "
          "distinction cyclomatic complexity is blind to.",
     formula="cognitive(f) = &Sigma;<sub>s &isin; structures(f)</sub> "
             "(1 + nesting(s))<br>"
             "pmd_cognitive_total = &Sigma;<sub>f &isin; F</sub> cognitive(f)",
     terms="<b>structures(f)</b> are the flow-breaking constructs in <i>f</i>: "
           "<code>if</code>, <code>else if</code>, <code>else</code>, "
           "<code>switch</code>, each loop, each <code>catch</code>, each ternary, "
           "and each run of mixed <code>&amp;&amp;</code> or <code>||</code> "
           "operators. <b>nesting(s)</b> is how many enclosing structures <i>s</i> "
           "sits inside. Some constructs take the increment without contributing "
           "nesting, which is what forgives a flat sequence: ten sibling "
           "<code>if</code> statements score 10, while ten nested ones score 55.",
     how="PMD computes it with its own Java parser. The harness spawns PMD once "
         "per checkpoint for both of its rulesets and splits the merged report, "
         "because a JVM launch per ruleset would dominate the analysis time.",
     read="Agreement with total cyclomatic complexity means the conservation result "
          "is not an artefact of how branches are counted. Disagreement would mean "
          "one arm's complexity is more deeply nested, which is a real finding "
          "about shape rather than amount.")

_add("pmd_npath_total",
     title="Total NPath complexity",
     group="amount", direction="flat",
     source="Nejmeh 1988, via PMD",
     what="The number of acyclic execution paths through a function. It is "
          "cyclomatic complexity's multiplicative cousin. Where McCabe adds across "
          "sequential branches, NPath multiplies, which is closer to the number of "
          "distinct behaviours a test suite would have to cover. Two sequential "
          "if-statements are 3 by McCabe and 4 by NPath. Ten of them are 11 versus "
          "1024.",
     formula="NP(<i>if</i>) = NP(cond) + NP(then) + NP(else)<br>"
             "NP(<i>seq</i>) = NP(s<sub>1</sub>) &times; NP(s<sub>2</sub>) &times; &hellip;<br>"
             "pmd_npath_total = &Sigma;<sub>f &isin; F</sub> NP(body of f)",
     terms="The recursion is over the statement tree. Statements in sequence "
           "multiply, which is where the explosion comes from. A branch adds its "
           "arms. A statement with no control flow has NP 1. Loops and "
           "<code>switch</code> have their own rules in Nejmeh's original paper, "
           "which PMD implements.",
     how="PMD, from the same single spawn as cognitive complexity.",
     read="Because it multiplies, NPath detonates when decisions pile up in the "
          "same method. A conservation result that survives NPath is a strong one.",
     caveat="The scale is enormous and is dominated by whichever single method has "
            "the most sequential branches. Read the shape of the line, not its "
            "value.")

_add("halstead_volume",
     title="Total Halstead volume",
     group="amount", direction="flat",
     source="Halstead 1977",
     what="Program size measured by vocabulary rather than by control flow. It "
          "asks how many distinct operators and operands there are and how often "
          "they appear. It has no concept of a branch at all, which is what makes "
          "it valuable here: if it agrees with the cyclomatic total, the "
          "conservation result is not a property of one family of measure.",
     formula="V = N &middot; log<sub>2</sub> &eta;<br>"
             "where &eta; = &eta;<sub>1</sub> + &eta;<sub>2</sub> and "
             "N = N<sub>1</sub> + N<sub>2</sub>",
     terms="<b>&eta;<sub>1</sub></b> is the number of distinct operators and "
           "<b>&eta;<sub>2</sub></b> the number of distinct operands, so "
           "<b>&eta;</b> is the vocabulary. <b>N<sub>1</sub></b> and "
           "<b>N<sub>2</sub></b> are the total occurrences of each, so <b>N</b> is "
           "the program length. Volume is therefore length times the bits needed "
           "to name one vocabulary item.",
     how="The harness tokenises each file itself in "
         "<code>placement.halstead</code>. Symbolic operators and the control-flow "
         "keywords count as operators. Identifiers, numbers and type keywords "
         "count as operands. Comments are stripped. <b>Every string and character "
         "literal is replaced by one placeholder operand before tokenising</b>, so "
         "an arm cannot move its Halstead score by writing longer error messages. "
         "File volumes are summed.",
     read="The fourth independent way of asking how much is there. Treat the units "
          "as arbitrary and compare the two lines.")

_add("halstead_effort",
     title="Total Halstead effort",
     group="amount", direction="flat",
     source="Halstead 1977",
     what="Halstead's own estimate of the mental work needed to write or "
          "understand the program. It is volume multiplied by difficulty, where "
          "difficulty grows as a small vocabulary of operands gets reused many "
          "times. It is more sensitive than volume, and it moves for reasons "
          "volume does not.",
     formula="D = (&eta;<sub>1</sub> / 2) &middot; (N<sub>2</sub> / &eta;<sub>2</sub>)"
             "<br>E = D &middot; V",
     terms="<b>D</b> is difficulty. The first factor is half the operator "
           "vocabulary. The second is the average number of times each distinct "
           "operand is used, so a function that keeps reusing the same few "
           "variables scores as harder. <b>V</b> is the volume above. Effort is "
           "their product, summed over files.",
     how="Computed in the same tokenising pass as volume.",
     read="Read it as a more sensitive volume. A gap here with no gap in volume "
           "means one arm reuses its operands more heavily.")

_add("ck_wmc_total",
     title="Total weighted methods per class (independent parser)",
     group="amount", direction="flat",
     source="Chidamber & Kemerer 1994, via the CK tool (Aniche 2015)",
     what="The same total-complexity question, computed class by class, by a "
          "completely different tool with a completely different parser. This is a "
          "cross-check rather than a finding. Every other complexity number on this "
          "page comes from lizard. If a parser quirk were driving the conservation "
          "result, this is where it would show up.",
     formula="WMC(C) = &Sigma;<sub>m &isin; methods(C)</sub> CC(m)<br>"
             "ck_wmc_total = &Sigma;<sub>C &isin; classes</sub> WMC(C)",
     terms="<b>C</b> ranges over every class the CK tool can parse. Chidamber and "
           "Kemerer left the per-method weight open. CK uses cyclomatic "
           "complexity, which is the conventional choice and matches the lizard "
           "side, so the two totals are directly comparable.",
     how="CK is a Java program that parses source with Eclipse JDT, which is a "
         "full compiler front end. lizard uses its own lightweight parser. The "
         "harness runs CK once per checkpoint over the arm's source directories "
         "and reads its per-class CSV.",
     read="Agreement with total cyclomatic complexity is the result you want, and "
          "it is a boring one. Disagreement means one of the two parsers is failing "
          "to read some file, which would make that file look perfect.")

_add("mi_mean",
     title="Maintainability Index, average file",
     group="amount", direction="up",
     source="Coleman et al. 1994, in the SEI and Visual Studio rescaling",
     what="A composite index built from Halstead volume, cyclomatic complexity and "
          "lines of code, rescaled so that higher is more maintainable. It is the "
          "number a reviewer expects to see, and it combines all three families of "
          "measure, so it is a useful single check on whether aggregate "
          "maintainability differs at all before any placement argument is made.",
     formula="MI(file) = max(0, (171 &minus; 5.2&nbsp;ln&nbsp;V "
             "&minus; 0.23&nbsp;CC &minus; 16.2&nbsp;ln&nbsp;LOC) &middot; 100/171)"
             "<br>mi_mean = mean over files of MI(file)",
     terms="<b>V</b> is that file's Halstead volume, <b>CC</b> its summed "
           "cyclomatic complexity and <b>LOC</b> its line count. The constants are "
           "Coleman's, fitted in 1994. The <code>&middot; 100/171</code> factor "
           "and the floor at zero are the later SEI rescaling into a 0 to 100 "
           "range, which is the form most tools report. It is computed <b>per "
           "file and then averaged</b>, not over the codebase as one blob.",
     how="Computed in <code>placement.maintainability_index</code> from the "
         "harness's own Halstead pass and lizard's per-function complexity, "
         "grouped by file.",
     read="It is location-blind by construction, which is precisely why it must not "
          "be the thesis statistic. It cannot see concentration.",
     caveat="Averaging over files rewards fragmentation. An architecture that adds "
            "many small healthy files raises its own average without improving "
            "anything. Read it with the worst-file version below, which cannot be "
            "diluted.")

_add("mi_min",
     title="Maintainability Index, worst file",
     group="amount", direction="up",
     source="Coleman et al. 1994",
     what="The Maintainability Index of the single worst file in the codebase. "
          "Unlike the average it cannot be diluted by adding good files, which "
          "makes it the version worth quoting.",
     formula="mi_min = min over files of MI(file)",
     terms="Same per-file MI as above. The minimum is taken over every production "
           "Java file with a positive volume and line count.",
     how="Same pass as the mean.",
     read="A falling line means the worst thing in the codebase is getting worse, "
          "whatever else is happening. That is usually the thing a maintainer will "
          "actually meet.")

_add("total_fns",
     title="Function count",
     group="amount", direction="",
     source="lizard",
     what="How many functions exist in production Java. This is descriptive, and "
          "it is also the scale correction for several other metrics. A "
          "distributed architecture should climb here, because that is the "
          "mechanism it works by, not a finding about it.",
     formula="total_fns = | F |",
     terms="<b>F</b> is the same function population as the cyclomatic total. "
           + PROD_JAVA,
     how="Count of lizard's function records at the checkpoint commit.",
     read="It matters because several concentration metrics are <i>not</i> "
          "scale-free. An arm with more units scores better on those for free. This "
          "line is how you check whether a concentration gap is a difference in "
          "shape or just a difference in count.")

_add("total_files",
     title="File count",
     group="amount", direction="",
     source="lizard",
     what="How many production Java files exist. The same role as the function "
          "count, one level up, and the denominator for every file-based "
          "concentration index on this page.",
     formula="total_files = | { file(f) : f &isin; F } |",
     terms="<b>file(f)</b> is the path the function was found in. Only files "
           "containing at least one parsed function are counted, which is worth "
           "knowing: a file the parser cannot read does not appear here either.",
     how="Distinct file paths among lizard's function records.",
     read="Read it beside any HHI or top-share figure. Those are not scale-free, "
          "so a rising file count lowers them for free.")

_add("total_packages",
     title="Package count",
     group="amount", direction="",
     source="harness",
     what="How many Java packages the production code spans. It says whether new "
          "rules got their own home in the source tree or were filed into existing "
          "ones.",
     formula="total_packages = | { package(f) : f &isin; F } |",
     terms="<b>package(f)</b> is derived from the file's path below the source "
           "root, with the file name removed, which is the package a Java file in "
           "a conventional layout declares.",
     how="Derived from file paths in <code>placement._package_of</code> rather "
         "than by reading <code>package</code> statements, so it reflects the "
         "directory structure a developer navigates.",
     read="Descriptive. It is context for the package-level concentration index.")

_add("java_loc",
     title="Production Java lines of code",
     group="amount", direction="",
     source="lizard nloc, summed",
     what="Total production Java, excluding tests and excluding the YAML wiring. "
          "The raw size line. Every ratio metric on this page has this or a close "
          "relative as its denominator, so a surprising ratio is often a size "
          "story.",
     formula="java_loc = &Sigma;<sub>f &isin; F</sub> nloc(f)",
     terms="<b>nloc(f)</b> is lizard's count of non-comment, non-blank lines in "
           "the function. Note that this sums <i>function bodies</i>, so file-level "
           "declarations, imports and field initialisers are not included. "
           + PROD_JAVA,
     how="Summed from lizard's per-function records. The YAML pool is counted into "
         "<code>yaml_loc</code> separately and the two are never added together.",
     read="Both arms should grow. The interesting question is whether one grows "
          "faster for the same sixty rules, which would mean it needs more code to "
          "express the same behaviour.")


# =========================================================================
# PLACEMENT: the thesis
# =========================================================================
# Shared term text for the four concentration indices, which all take the same
# vector of per-unit weights and differ only in how they summarise it.
_SHARES = ("The input is a vector of per-unit weights <b>x<sub>1</sub> &hellip; "
           "x<sub>n</sub></b>, one per unit, zeros dropped. <b>p<sub>i</sub> = "
           "x<sub>i</sub> / &Sigma;x</b> is unit <i>i</i>'s share of the total.")
_NOT_SCALEFREE = ("<b>Not scale-free.</b> An arm with more units scores lower for "
                  "free, whatever the shape of its distribution. Always read it "
                  "beside the Gini, which is scale-free, and beside the unit "
                  "count. If Gini agrees, the honest claim is that the "
                  "distribution is more unequal. If only this moves, the honest "
                  "claim is only that the units are larger.")

_add("ccdist_file_gini",
     title="Complexity inequality across files (Gini)",
     group="placement", direction="down",
     source="Gini 1912, applied to per-file cyclomatic complexity",
     what="Take every file's total complexity and ask how unequally it is "
          "distributed. It is the same statistic economists use for income. 0 "
          "means every file carries the same complexity. 1 means one file carries "
          "it all. This is the headline concentration metric of the whole "
          "experiment, because it is the only one of the four that measures shape "
          "alone.",
     formula="G = &Sigma;<sub>i=1..n</sub> (2i &minus; n &minus; 1) &middot; "
             "x<sub>i</sub> &nbsp;/&nbsp; (n &middot; &Sigma;x)",
     terms=_SHARES + " For the Gini the weights must be <b>sorted ascending</b>, "
           "so <b>i</b> is the rank from lightest to heaviest and the leading "
           "factor runs from negative to positive. <b>x<sub>i</sub></b> is file "
           "<i>i</i>'s summed CC over the functions in it. The result is "
           "undefined, and blank, for fewer than two files.",
     how="<code>placement.gini</code> over per-file CC totals at the checkpoint "
         "commit. Files with zero complexity are dropped before sorting, because "
         "an interface or a constants holder would otherwise read as poverty.",
     read="<b>This is the one to lead with.</b> Gini is scale-free: it describes "
          "the shape of the distribution and is insensitive to how many units it "
          "is spread over. An architecture cannot improve its Gini by splitting "
          "files into more files of the same shape. So if Gini separates the arms, "
          "the distribution really is more unequal.")

_add("ccdist_file_hhi",
     title="Complexity concentration across files (HHI)",
     group="placement", direction="down",
     source="Herfindahl-Hirschman index (Hirschman 1945), over per-file CC shares",
     what="The sum of squared shares. It is the standard concentration index from "
          "competition regulation, where it decides whether a market is too "
          "concentrated. One file holding everything scores 1. A hundred equal "
          "files score 0.01. Squaring is what makes it responsive: it is dominated "
          "by the largest holder, so it moves sharply when one file runs away.",
     formula="HHI = &Sigma;<sub>i=1..n</sub> p<sub>i</sub><sup>2</sup>",
     terms=_SHARES + " The index ranges from <b>1/n</b>, for perfectly even, up to "
           "<b>1</b>, for everything in one unit. That lower bound is the whole "
           "problem with it here, because it depends on <i>n</i>.",
     how="<code>placement.hhi</code> over per-file CC totals.",
     read="Sharper than the Gini when one file is running away, because squaring "
          "weights the leader.",
     caveat=_NOT_SCALEFREE)

_add("ccdist_file_top1",
     title="Share of all complexity in the single heaviest file",
     group="placement", direction="down",
     source="concentration ratio CR1",
     what="What fraction of the entire application's complexity lives in its one "
          "biggest file. This is the most directly interpretable number on the "
          "page. It reads as a sentence: one file in this codebase holds this much "
          "of all its decisions.",
     formula="CR<sub>1</sub> = max<sub>i</sub> x<sub>i</sub> / &Sigma;x",
     terms=_SHARES + " No sorting or squaring. It is simply the largest single "
           "share.",
     how="<code>placement.top_share</code> with k=1, over per-file CC totals.",
     read="If this climbs toward a third as rules accumulate, the god-file story is "
          "not a metaphor. It is also the easiest figure to quote to someone who "
          "does not want a statistics lesson.")

_add("ccdist_file_top5",
     title="Share of all complexity in the heaviest five files",
     group="placement", direction="down",
     source="concentration ratio CR5",
     what="The same question widened to five files, so a codebase cannot look "
          "healthy simply by splitting its god file in two.",
     formula="CR<sub>5</sub> = &Sigma;<sub>i=1..5</sub> x<sub>(i)</sub> / &Sigma;x",
     terms=_SHARES + " <b>x<sub>(i)</sub></b> denotes the weights sorted "
           "<b>descending</b>, so the sum is over the five heaviest. With fewer "
           "than five non-zero files the value is 1 by construction.",
     how="<code>placement.top_share</code> with k=5.",
     read="Resistant to the cosmetic split. If the top-1 share falls but this does "
          "not, the complexity was moved next door rather than distributed.")

_add("ccdist_file_hnorm",
     title="Complexity spread across files (normalised entropy)",
     group="placement", direction="up",
     source="Shannon entropy, normalised by log n",
     what="How evenly complexity is spread, on a scale of 0 to 1 where 1 is "
          "perfectly even. It is the information-theoretic mirror of the "
          "concentration indices, and it reads as the number of bits you would "
          "need to say which file a randomly chosen unit of complexity came from.",
     formula="H = &minus;&Sigma;<sub>i</sub> p<sub>i</sub> ln p<sub>i</sub>"
             "<br>H<sub>norm</sub> = H / ln n",
     terms=_SHARES + " <b>n</b> is the number of non-zero units. Dividing by "
           "<b>ln n</b> is the maximum entropy that many units can have, which is "
           "what puts the result on a 0 to 1 scale and removes most of the unit "
           "count advantage that HHI gives away. The base of the logarithm cancels "
           "in the ratio, so natural log here and log base 2 elsewhere give the "
           "same normalised number.",
     how="<code>placement.norm_entropy</code> over per-file CC totals. Undefined, "
         "and blank, for fewer than two files.",
     read="Note the direction flips. <b>Higher means more distributed.</b> Because "
          "it is normalised it makes a useful referee between the Gini and the "
          "HHI when those two disagree.")

_add("ccdist_fn_gini",
     title="Complexity inequality across functions (Gini)",
     group="placement", direction="down",
     source="Gini 1912, applied to per-function CC",
     what="The same inequality question one level down, across individual "
          "functions rather than files. Files can be split for cosmetic reasons. A "
          "function is the unit a developer actually reads at one sitting, so this "
          "is the god-method question rather than the god-file one.",
     formula="G = &Sigma;<sub>i=1..n</sub> (2i &minus; n &minus; 1) &middot; "
             "x<sub>i</sub> &nbsp;/&nbsp; (n &middot; &Sigma;x)",
     terms="Same formula as the file Gini, with <b>x<sub>i</sub></b> now the "
           "cyclomatic complexity of one function, sorted ascending. <b>n</b> is "
           "the number of functions with non-zero complexity.",
     how="<code>placement.gini</code> over the per-function CC column.",
     read="This asks whether one <i>method</i> is becoming the place decisions go. "
          "It is harder to game than the file version, because you cannot split a "
          "method without changing the code.")

_add("ccdist_fn_hhi",
     title="Complexity concentration across functions (HHI)",
     group="placement", direction="down",
     source="Herfindahl-Hirschman index over per-function CC shares",
     what="Concentration of decisions into single methods. The god-method signal, "
          "as opposed to the god-class signal.",
     formula="HHI = &Sigma;<sub>i=1..n</sub> p<sub>i</sub><sup>2</sup>",
     terms="Same formula as the file HHI, with <b>p<sub>i</sub></b> now one "
           "function's share of total cyclomatic complexity.",
     how="<code>placement.hhi</code> over the per-function CC column.",
     read="Squaring means one very heavy method dominates the figure, which is the "
          "behaviour you want from a god-method detector.",
     caveat=_NOT_SCALEFREE)

_add("ccdist_pkg_hhi",
     title="Complexity concentration across packages (HHI)",
     group="placement", direction="down",
     source="Herfindahl-Hirschman index over per-package CC shares",
     what="Concentration at the coarsest level, across whole packages. It survives "
          "any amount of file-level reshuffling inside a package.",
     formula="HHI = &Sigma;<sub>i=1..n</sub> p<sub>i</sub><sup>2</sup>",
     terms="<b>p<sub>i</sub></b> is package <i>i</i>'s share of total cyclomatic "
           "complexity, where a package is the directory path below the source "
           "root. <b>n</b> is the package count, which is small, so this index "
           "sits much higher than the file or function versions and must not be "
           "compared against them numerically.",
     how="<code>placement.hhi</code> over CC grouped by "
         "<code>placement._package_of</code>.",
     read="If a condition improves the file numbers but not this one, the rules "
          "were split into more files inside the same package. That is a smaller "
          "change than it looks.")

_add("wmcdist_class_hhi",
     title="Class-weight concentration (HHI over WMC)",
     group="placement", direction="down",
     source="Herfindahl-Hirschman index over per-class WMC, via CK",
     what="The concentration question over classes, weighted by how much "
          "complexity each class's methods carry. It is the class-level view of "
          "the god-object question, computed by the independent parser.",
     formula="HHI = &Sigma;<sub>i</sub> p<sub>i</sub><sup>2</sup>, &nbsp; "
             "p<sub>i</sub> = WMC(C<sub>i</sub>) / &Sigma;<sub>j</sub> WMC(C<sub>j</sub>)",
     terms="<b>WMC(C)</b> is the sum of cyclomatic complexity over the methods of "
           "class <i>C</i>, as CK reports it. Unlike the file-based indices this "
           "one sees nested and inner classes as their own units, because CK "
           "resolves real class declarations rather than assuming one class per "
           "file.",
     how="<code>placement.hhi</code> over CK's per-class WMC column.",
     read="A useful cross-check on the file-level indices, since it uses a "
          "different notion of a unit and a different parser.",
     caveat=_NOT_SCALEFREE)

_add("cogdist_fn_hhi",
     title="Cognitive-complexity concentration across functions",
     group="placement", direction="down",
     source="HHI over per-function cognitive complexity (PMD)",
     what="Concentration measured in units of human difficulty rather than branch "
          "count. It asks whether the nesting is pooling in one place, which is a "
          "different question from whether the branches are.",
     formula="HHI = &Sigma;<sub>i</sub> p<sub>i</sub><sup>2</sup>, &nbsp; "
             "p<sub>i</sub> = cognitive(f<sub>i</sub>) / &Sigma;<sub>j</sub> "
             "cognitive(f<sub>j</sub>)",
     terms="<b>cognitive(f)</b> is the Campbell measure defined in the amount "
           "group: one point per flow-breaking structure plus one per level of "
           "nesting it sits inside.",
     how="<code>placement.hhi</code> over PMD's per-method cognitive complexity.",
     read="If concentration shows up in cyclomatic terms but not cognitive terms, "
          "the concentrated method is long but flat. If it shows up in both, it is "
          "long <i>and</i> deeply nested. That is the genuinely hard kind.",
     caveat=_NOT_SCALEFREE)

_add("voldist_file_hhi",
     title="Halstead-volume concentration across files",
     group="placement", direction="down",
     source="HHI over per-file Halstead volume",
     what="Concentration measured by vocabulary rather than by control flow. It is "
          "the control-flow-free confirmation that the concentration result is not "
          "an artefact of how branches are counted.",
     formula="HHI = &Sigma;<sub>i</sub> p<sub>i</sub><sup>2</sup>, &nbsp; "
             "p<sub>i</sub> = V(file<sub>i</sub>) / &Sigma;<sub>j</sub> V(file<sub>j</sub>)",
     terms="<b>V(file)</b> is that file's Halstead volume, as defined in the amount "
           "group. Because literals are collapsed to one placeholder operand, this "
           "cannot be moved by editing message text.",
     how="<code>placement.hhi</code> over the harness's per-file Halstead volumes.",
     read="A branch-free second opinion on the file-level concentration result.",
     caveat=_NOT_SCALEFREE)

_add("wmc_max",
     title="Heaviest class in the codebase (WMC)",
     group="placement", direction="down",
     source="Chidamber & Kemerer 1994, via lizard",
     what="Weighted methods per class is the sum of the cyclomatic complexities of "
          "every method in a class. The heaviest such class is the god-class "
          "candidate. It catches what a per-method erosion threshold cannot: a "
          "controller that stays tidy method by method, while accumulating twenty "
          "rules' worth of methods, becomes a god class without any single method "
          "ever crossing CC 10.",
     formula="WMC(C) = &Sigma;<sub>m &isin; methods(C)</sub> CC(m)<br>"
             "wmc_max = max<sub>C &isin; touched</sub> WMC(C)",
     terms="<b>C</b> ranges over the <b>touched subsystem</b>, which is the "
           "production Java files changed since the baseline commit. That scoping "
           "is deliberate: it tracks what the agent is building rather than what "
           "shipped with the framework. On the lizard side a class is identified "
           "with a file, on the assumption of one top-level class per Java file.",
     how="<code>metrics.wmc_stats</code> groups lizard's functions by file, sums "
         "CC per group and returns the worst, along with its name, method count "
         "and line count.",
     read="Rising means one class is accumulating everything.",
     caveat="<b>Role-blind, and that matters here.</b> The two architectures answer "
            "this question with different <i>kinds</i> of class. One arm's heaviest "
            "is usually the controller, around 32 methods averaging CC above 3. The "
            "other's is often the Owner entity, around 60 accessors at CC 1. Those "
            "are not the same problem. Use the handler-scoped version below for any "
            "claim about the architectures.")

_add("wmc_handler",
     title="Weight of the handler class (like-for-like)",
     group="placement", direction="down",
     source="C&K WMC, pinned to the class the endpoint routes through",
     what="The same god-class number, but measured on the class that actually "
          "handles the create-owner request, in both architectures. Pinning it to "
          "a role rather than to whichever class happens to be heaviest is what "
          "makes it a fair comparison.",
     formula="wmc_handler = &Sigma;<sub>m &isin; methods(H)</sub> CC(m)",
     terms="<b>H</b> is the handler class, which is the file containing the "
           "function the create endpoint routes through. The harness finds it per "
           "arm from the configured <code>entry_handler</code> pattern, so it "
           "resolves to the Spring controller in one arm and to the wired "
           "create function's class in the other. The field is blank until that "
           "class exists.",
     how="Same scoping as handler erosion, in "
         "<code>metrics.entry_handler_stats</code> and its WMC companion.",
     read="A rising line means the front door is turning into a god class. This is "
          "the like-for-like god-class comparison, same role, both arms.",
     caveat="<b>Not prompt-robust.</b> This can be driven to zero by telling the "
            "agent the formula. The logic simply moves into new files while the "
            "total complexity is unchanged. It stays valid for the ungated "
            "control. Never publish it as the headline for an intervention arm "
            "without the whole-path number from the comprehension group beside it.")

_add("ck_handler_wmc",
     title="Weight of the handler class (independent parser)",
     group="placement", direction="down",
     source="CK tool (Aniche 2015), Eclipse JDT parser",
     what="The handler-class weight again, from the second tool. A cross-check "
          "that neither parser is silently failing on the handler file, which is "
          "the one file on which the whole concentration argument rests.",
     formula="WMC(H) = &Sigma;<sub>m &isin; methods(H)</sub> CC(m), as CK reports it",
     terms="<b>H</b> is matched by class name rather than by file path here, "
           "because CK reports per class. Differences from the lizard figure are "
           "usually nested classes, which CK attributes separately.",
     how="Read from CK's per-class CSV, filtered to the handler class name.",
     read="Agreement with the lizard figure is the boring result you want.")

_add("entry_cc",
     title="Complexity of the front-door method",
     group="placement", direction="down",
     source="McCabe 1976, scoped to the entry function",
     what="The cyclomatic complexity of the single method the HTTP request lands "
          "in. That is the method a developer opens first when asked to change "
          "this endpoint, so it is the purest available measure of whether the "
          "front door bloats.",
     formula="entry_cc = CC(e)",
     terms="<b>e</b> is the one function the create endpoint routes through, which "
           "is <code>addOwner</code> in the Spring arm and the wired create "
           "function's service method in the OfficeFloor arm. " + CC_DEF,
     how="<code>metrics.entry_handler_stats</code> matches the configured entry "
         "pattern against lizard's function list and reports that function's CC, "
         "line count and name.",
     read="The purest front-door measure, and the easiest to explain.",
     caveat="<b>Entry-scoped, so it understates a pipeline architecture by "
            "construction.</b> An architecture whose entry node just dispatches "
            "will read about 1 while its worst downstream step reads about 13. "
            "Never publish this without the whole-path complexity beside it. A "
            "reader who opens the wiring file will make that objection for you.")

_add("hotspot_cc",
     title="Worst single function in the touched subsystem",
     group="placement", direction="down",
     source="lizard",
     what="The highest cyclomatic complexity of any one function among the files "
          "this run has changed. Scoping it to changed files means it tracks what "
          "the agent is actually building, rather than whatever the framework "
          "shipped with.",
     formula="hotspot_cc = max<sub>f &isin; touched</sub> CC(f)",
     terms="<b>touched</b> is the set of production Java functions in files changed "
           "since the baseline commit. The harness also records which function it "
           "was, as <code>hotspot_fn</code>, so the figure can be traced to a "
           "name.",
     how="<code>metrics.hotspot_stats</code> over the dynamically scoped subsystem.",
     read="A climbing line means the worst thing the agent has written keeps "
          "getting worse. Because it is a maximum it is noisy, so read the trend.")

_add("erosion",
     title="Structural erosion, whole application",
     group="placement", direction="down",
     source="SlopCodeBench (arXiv:2603.24755) Eq. 3",
     what="What fraction of the codebase's complexity sits inside functions that "
          "are over the complexity threshold. Each function is given a mass that "
          "combines its branching with its size, and erosion is the share of that "
          "mass held by functions judged too complex. It is the benchmark's own "
          "headline measure, which is why it is reported here at all.",
     formula="mass(f) = CC(f) &middot; &radic;<span style=\"text-decoration:overline\">"
             "max(SLOC(f), 1)</span><br>"
             "erosion = &Sigma;<sub>f : CC(f) &gt; 10</sub> mass(f) &nbsp;/&nbsp; "
             "&Sigma;<sub>f &isin; F</sub> mass(f)",
     terms=CC_DEF + " <b>SLOC(f)</b> is the function's non-comment line count. The "
           "square root is the benchmark's choice: it means size matters but with "
           "diminishing returns, so a 400-line function is not simply scored as "
           "ten times a 40-line one. The threshold of <b>CC &gt; 10</b> is "
           "McCabe's own recommended limit, not a value chosen here. " + PROD_JAVA,
     how="<code>metrics.erosion_detail</code>. The harness records the numerator "
         "and denominator separately, as <code>erosion_high_mass</code> and "
         "<code>erosion_total_mass</code>, so the ratio is reproducible from the "
         "CSV without rerunning anything.",
     read="Kept for comparability with the published benchmark.",
     caveat="<b>Demoted from decisive in this experiment.</b> It is "
            "location-blind. It cannot tell a CC-19 god method from a CC-19 "
            "isolated single-responsibility algorithm. Here it is also dominated "
            "by architecture-neutral leaf algorithms (soundex, phone "
            "normalisation, deduplication) that both arms have to implement. Its "
            "arm ordering has come out backwards. Read it as a leaf-algorithm "
            "measure, not as a test of the thesis.")

_add("erosion_scoped",
     title="Structural erosion, changed files only",
     group="placement", direction="down",
     source="SlopCodeBench Eq. 3, scoped to the touched subsystem",
     what="The same erosion ratio, restricted to files this run has actually "
          "modified, so untouched framework code cannot dilute it.",
     formula="erosion_scoped = &Sigma;<sub>f &isin; touched, CC(f) &gt; 10</sub> "
             "mass(f) &nbsp;/&nbsp; &Sigma;<sub>f &isin; touched</sub> mass(f)",
     terms="Same mass and same threshold as the whole-app version. <b>touched</b> "
           "is the production Java functions in files changed since the baseline "
           "commit, which grows as the run proceeds. The harness records the "
           "subsystem's function count as <code>subsystem_nfns</code> so the "
           "denominator's size is visible.",
     how="<code>metrics.erosion_detail</code> over the dynamically scoped "
         "subsystem.",
     read="A tighter version of the whole-app number.",
     caveat="It inherits the same location-blindness. A big isolated algorithm in a "
            "changed file scores exactly the same as a big god method there.")

_add("erosion_handler",
     title="Structural erosion of the handler class",
     group="placement", direction="down",
     source="SlopCodeBench Eq. 3, scoped to the entry handler's own class",
     what="Erosion measured only inside the class that handles the request. "
          "Scoping it this way excludes the leaf algorithms that swamp the two "
          "wider versions. What is left is the clean concentration signal: does "
          "the endpoint's own handler surface rot as rules accumulate?",
     formula="erosion_handler = &Sigma;<sub>f &isin; H, CC(f) &gt; 10</sub> mass(f) "
             "&nbsp;/&nbsp; &Sigma;<sub>f &isin; H</sub> mass(f)",
     terms="<b>H</b> is the functions of the handler class only, found by the same "
           "entry pattern as the handler WMC. The harness records "
           "<code>erosion_handler_class</code> and "
           "<code>erosion_handler_nfns</code> so you can confirm which class was "
           "measured and how many functions were in the denominator.",
     how="<code>metrics.handler_scoped_erosion</code>.",
     read="This is the erosion number that tests the thesis.",
     caveat="Like the handler WMC, this can be driven to exactly zero by an "
            "intervention that relocates logic without removing it. It stays valid "
            "for the ungated control. For an intervention arm, read the "
            "comprehension group instead.")

_add("pmd_god_classes",
     title="God classes detected",
     group="placement", direction="down",
     source="Lanza & Marinescu 2006 thresholds, via PMD's GodClass rule",
     what="How many classes trip a published god-class detector. The value of this "
          "metric is that nobody in this experiment chose the thresholds. It is an "
          "externally defined, binary verdict, which makes it immune to the "
          "accusation that the scoring was tuned to the result.",
     formula="GodClass(C) &hArr; WMC(C) &ge; 47 &nbsp;&and;&nbsp; ATFD(C) &gt; 5 "
             "&nbsp;&and;&nbsp; TCC(C) &lt; 1/3<br>"
             "pmd_god_classes = | { C : GodClass(C) } |",
     terms="All three conditions must hold. <b>WMC</b> is weighted methods per "
           "class, as above. <b>ATFD</b> is Access To Foreign Data: the number of "
           "distinct fields of <i>other</i> classes this one reaches into, which "
           "is what distinguishes a class doing too much from a class that is "
           "merely large. <b>TCC</b> is tight class cohesion, defined in the "
           "cohesion group, so the third condition says the class is also "
           "internally incoherent. The constants 47, 5 and 1/3 are Lanza and "
           "Marinescu's.",
     how="PMD's <code>GodClass</code> rule, from the same single PMD spawn as the "
         "complexity measures. The harness counts distinct violating classes.",
     read="A step change in this line is a strong, externally validated statement "
          "that the codebase acquired a god class at that change request.")

_add("pmd_handler_is_god_class",
     title="Is the handler class itself a god class",
     group="placement", direction="down",
     source="PMD GodClass rule, evaluated on the handler class",
     what="Whether the class handling the endpoint trips the published detector. "
          "It is binary, externally defined, and about the specific class both "
          "architectures agree is the entry point, which makes it the single most "
          "quotable structural result on this page.",
     formula="value(c) = 1 if GodClass(H) at change request <i>c</i>, else 0"
             "<br>plotted value = (1/K) &Sigma;<sub>k=1..K</sub> value<sub>k</sub>(c)",
     terms="<b>H</b> is the handler class. <b>GodClass</b> is the three-condition "
           "test above. <b>K</b> is 10, the number of runs, so the plotted line is "
           "the fraction of runs in which the front door has become a god class by "
           "that change request.",
     how="The harness passes the handler class name to "
         "<code>placement.pmd_metrics_from_report</code> and records whether PMD "
         "flagged it.",
     read="Read the line as: in what fraction of runs has the front door become a "
          "god class by change request N.")

_add("pmd_data_classes",
     title="Data classes detected",
     group="placement", direction="",
     source="PMD DataClass rule",
     what="Classes that are mostly fields and accessors with little behaviour. "
          "This is context rather than a finding. It is how you tell whether a "
          "heaviest-class result is about a controller full of decisions or an "
          "entity full of getters.",
     formula="pmd_data_classes = | { C : DataClass(C) } |",
     terms="PMD's <code>DataClass</code> rule fires on a class with a high "
           "proportion of public accessors, few real methods and low complexity "
           "per method. It is the complement of the god class: too little "
           "behaviour rather than too much.",
     how="Same single PMD spawn, counting distinct violating classes.",
     read="Use it to interpret the role-blind heaviest-class metric. A rising data "
          "class count in one arm usually means its entity is growing accessors.")


# =========================================================================
# COMPREHENSION: relocation-proof
# =========================================================================
_NODE_TERMS = (
    "<b>Nodes</b> are the steps the request passes through. They come from the "
    "arm's own declared wiring, which is the YAML file named by "
    "<code>node_roots.wiring_file</code>. An arm that declares no wiring "
    "contributes exactly one node, its <code>entry_handler</code>. "
    "<b>closure(r)</b> is the set of methods reachable from node <i>r</i> by "
    "following Java call edges transitively, computed by breadth-first search "
    "over a call graph the harness builds from lizard's function list plus name "
    "resolution. <b>cc(S) = &Sigma;<sub>k &isin; S</sub> CC(k)</b> for a set of "
    "methods <i>S</i>.")
_NODE_HOLE = (
    "<b>Code the framework dispatches is not code the handler calls.</b> A rule "
    "moved into a <code>@RestControllerAdvice</code>, an <code>@Aspect</code>, a "
    "servlet <code>Filter</code>, a <code>@PrePersist</code> entity listener or a "
    "<code>ConstraintValidator</code> leaves this walk entirely, because the "
    "container invokes it and there is no Java call edge to follow. Check the "
    "framework-dispatch counter in the validity group before trusting this for a "
    "given condition.")

_add("node_cc_median",
     title="Complexity reachable from a typical handling step",
     group="comprehension", direction="down",
     source="harness call-graph walk from the declared wiring nodes",
     what="Pick one step in the request's handling. Follow every method it calls, "
          "transitively, and add up the complexity. That total is what a developer "
          "must understand to change that one step. This metric is the median of "
          "that total across all the steps. It is the closest thing on this page "
          "to the real question, which is what it costs to change one rule.",
     formula="node_cc_median = median<sub>r &isin; nodes</sub> cc(closure(r))",
     terms=_NODE_TERMS,
     how="<code>metrics.node_closure_stats</code>. The call index is built once "
         "per checkpoint and shared with the indirection and propagation metrics, "
         "because resolving the graph is the expensive part.",
     read="<b>This is the concentration statistic to lead with.</b> It is "
          "relocation-proof: work pushed into a helper still lands in that "
          "helper's caller's closure, so moving code downstream does not improve "
          "it. It is the metric that survived the condition where the agent was "
          "told the scoring formula.",
     caveat=_NODE_HOLE)

_add("node_cc_max",
     title="Complexity reachable from the worst handling step",
     group="comprehension", direction="down",
     source="harness call-graph walk",
     what="The same closure complexity, for whichever step is worst. The median "
          "says what a typical change costs. This says what the worst change "
          "costs, which is often what a team actually remembers.",
     formula="node_cc_max = max<sub>r &isin; nodes</sub> cc(closure(r))",
     terms=_NODE_TERMS + " The harness also records the mean and the 90th "
           "percentile of the same distribution, as <code>node_cc_mean</code> and "
           "<code>node_cc_p90</code>.",
     how="Same single pass as the median.",
     read="A distributed architecture is allowed a high median and a low maximum, "
          "because it has many small steps. It is in trouble if its maximum "
          "approaches the concentrated arm's, because that means one of its steps "
          "has become the god method it was supposed to avoid.",
     caveat=_NODE_HOLE)

_add("node_path_cc",
     title="Complexity of the entire handling path",
     group="comprehension", direction="down",
     source="harness call-graph walk, unioned over all nodes",
     what="Everything reachable from any step of the request path, counted once. "
          "This is the honest total: what the whole feature costs to understand. "
          "Taking the union rather than the sum matters, because a shared helper "
          "reachable from six steps is one thing to learn, not six.",
     formula="node_path_cc = cc( &bigcup;<sub>r &isin; nodes</sub> closure(r) )",
     terms=_NODE_TERMS + " The union is over method identities, so a helper "
           "reached from several nodes is counted exactly once. The harness also "
           "records the size of that union as <code>node_path_methods</code>.",
     how="Same single pass. The set union is taken before summing complexity, not "
         "after.",
     read="<b>This is the answer to “you just moved it downstream”.</b> It must "
          "be published beside the front-door and handler-class metrics. It is "
          "also where the two architectures have historically come out closest. In "
          "one control run it read 229 against 202. That is the same total work, "
          "arranged differently. It is Tesler's conservation showing up in the "
          "place where it is hardest to argue with.",
     caveat=_NODE_HOLE + " A chain whose rules moved into advice classes can "
            "report a path complexity in single digits while implementing all "
            "sixty rules. A number that low is a detector of the escape, not a "
            "result.")

_add("node_count",
     title="Number of handling steps",
     group="comprehension", direction="",
     source="harness, from the architecture's declared wiring",
     what="How many distinct steps the request passes through. This is the "
          "mechanism, not a finding. It is also the correct denominator when "
          "reading the median closure complexity, because a rising median across a "
          "rising node count is a different story from a rising median at a fixed "
          "one.",
     formula="node_count = | nodes |",
     terms="Nodes declared in the arm's wiring file, or 1 for an architecture that "
           "declares none. The asymmetry is real and is the point: one arm has a "
           "single node by design.",
     how="<code>metrics._node_roots</code> parses the wiring file and resolves each "
         "declared step to a method in the call index. A step it cannot resolve is "
         "dropped, so this is a floor rather than a declaration count.",
     read="Read it beside the median. It is also the honest companion to the "
          "indirection metrics, whose depth figure understates a pipeline exactly "
          "because all its steps sit at depth zero.")

_add("node_exclusive_share",
     title="How much of the path belongs to exactly one step",
     group="comprehension", direction="up",
     source="harness call-graph walk",
     what="Of all the complexity reachable from the handling path, what fraction is "
          "reachable from only one step. High means each step owns its own logic. "
          "Low means the steps are thin wrappers over a shared blob. This is the "
          "metric that would expose a fake decomposition, because twenty wired "
          "steps that all call the same helper would show a high step count and a "
          "low exclusive share.",
     formula="reach(k) = | { r : k &isin; closure(r) } |<br>"
             "node_exclusive_share = &Sigma;<sub>r</sub> cc({ k &isin; closure(r) : "
             "reach(k) = 1 }) &nbsp;/&nbsp; &Sigma;<sub>r</sub> cc(closure(r))",
     terms=_NODE_TERMS + " <b>reach(k)</b> counts how many nodes can reach method "
           "<i>k</i>. Note that the denominator is the <b>sum</b> over nodes, not "
           "the union, so a method shared by six nodes is counted six times below "
           "the line and zero times above it. That is what makes sharing "
           "expensive in this ratio.",
     how="Same single pass. <b>Blank for an arm with one node</b>, where it would "
         "be trivially 1.0. That blank is deliberate: in an arm-versus-arm table a "
         "trivial 1.0 would read as perfect cohesion when it actually means there "
         "are no separable rules to share between.",
     read="This is the cohesion test for a pipeline architecture. It is the number "
          "to ask for when someone claims a decomposition is only cosmetic.")

_add("node_methods_median",
     title="Methods reachable from a typical handling step",
     group="comprehension", direction="down",
     source="harness call-graph walk",
     what="The same closure, counted in methods rather than in complexity. It is "
          "how many distinct methods you would have to read. Because it weights "
          "every method equally it is immune to any argument about how complexity "
          "should be scored.",
     formula="node_methods_median = median<sub>r &isin; nodes</sub> | closure(r) |",
     terms=_NODE_TERMS,
     how="Same single pass as the complexity median.",
     read="A count-based confirmation of the closure result. If it agrees with the "
          "complexity median, the finding does not depend on McCabe weights.",
     caveat=_NODE_HOLE)


# =========================================================================
# BLAST RADIUS and change spread
# =========================================================================
_add("existing_fns_modified",
     title="Pre-existing functions modified per rule",
     group="blast", direction="down",
     source="harness diff analysis",
     what="How many functions that already existed, and already worked, had to be "
          "opened to land this one change request. This is the blast radius "
          "proper. It is the measure that most directly explains the regression "
          "results, because you cannot break what you did not edit.",
     formula="existing_fns_modified(c) = | { f : file(f) existed at c&minus;1 "
             "&and; lines(f) &cap; changed(c) &ne; &empty; } |",
     terms="<b>changed(c)</b> is the set of line ranges the checkpoint's diff "
           "touched on the new side. <b>lines(f)</b> is function <i>f</i>'s line "
           "span at the new commit. A function counts if the diff overlapped it at "
           "all, including by a single inserted line. Functions in files created "
           "by this checkpoint are excluded, because they did not previously "
           "exist.",
     how="<code>metrics.blast_radius_detail</code> takes "
         "<code>git diff --name-status -M</code> between the previous and current "
         "checkpoint commits, maps changed hunks to functions at the new commit, "
         "and counts those in pre-existing files.",
     read="Zero means the rule was purely additive and nothing that already worked "
          "was put at risk. A rising line means the opposite.")

_add("files_created",
     title="New production files created per rule",
     group="blast", direction="",
     source="harness diff analysis",
     what="How many new production Java files the change request produced. It has "
          "no good direction. It is simultaneously the mechanism by which blast "
          "radius stays near zero and the mechanism by which a codebase "
          "fragments.",
     formula="files_created(c) = | { p : status(p) = A &and; p is production Java } |",
     terms="<b>status(p) = A</b> is git's added status for path <i>p</i> in the "
           "checkpoint diff, with rename detection on, so a renamed file is not "
           "miscounted as a creation. Test files and YAML are excluded.",
     how="<code>metrics.blast_radius_detail</code>, from the same "
         "<code>--name-status -M</code> parse.",
     read="Read it with the duplication group. New files that copy each other are "
          "not a win, and one condition in this study produced exactly that.")

_add("files_touched",
     title="Files touched per rule",
     group="blast", direction="down",
     source="git diff shortstat",
     what="How many files the change request touched in total, new and existing. "
          "The raw spread of one change. High values mean a rule could not be "
          "expressed in one place.",
     formula="files_touched(c) = | { p : p appears in diff(c&minus;1, c) } |",
     terms="Every path in the checkpoint diff, before the production-Java filter, "
           "so it includes configuration and resources. The harness records the "
           "added and removed line counts alongside, as <code>diff_added</code> "
           "and <code>diff_removed</code>.",
     how="<code>git diff --shortstat</code> between consecutive checkpoint commits.",
     read="The coarsest blast measure, and the one that needs no parser at all, "
          "which makes it a useful sanity check on the parsed ones.")

_add("packages_touched",
     title="Packages touched per rule",
     group="blast", direction="down",
     source="harness diff analysis",
     what="How many distinct Java packages one change request reached into. It "
          "ignores cosmetic file splits inside a package, so it is a coarser and "
          "more meaningful spread measure than the file count. A rule that touches "
          "four packages is a rule that did not have a home.",
     formula="packages_touched(c) = | { package(p) : p &isin; diff(c), "
             "p is production Java } |",
     terms="<b>package(p)</b> is the directory path below the source root, which is "
           "the package a conventionally laid out Java file declares.",
     how="Derived from the production-Java paths in the checkpoint diff.",
     read="Low and flat is the signature of a rule that had an obvious place to go.")

_add("reedit_rate",
     title="Temporal coupling: how much of this edit was someone else's rule",
     group="blast", direction="down",
     source="harness line-authorship analysis (git blame)",
     what="Of the lines inside the functions this change request edited, what share "
          "was written by earlier change requests. It is the clearest operational "
          "statement of the phrase “the rules are tangled”. A high rate means "
          "implementing rule 47 required reading and rewriting the code for rules "
          "12 and 30.",
     formula="reedit_rate(c) = prior_lines / body_lines<br>"
             "body_lines = &Sigma;<sub>f &isin; edited(c)</sub> | lines(f) |",
     terms="<b>edited(c)</b> is the pre-existing functions this checkpoint touched. "
           "<b>body_lines</b> counts <i>whole function bodies</i>, not just the "
           "changed lines. <b>prior_lines</b> is how many of those lines git blame "
           "attributes to a commit that is neither this checkpoint nor an ancestor "
           "of the baseline, which is exactly the set of earlier change requests. "
           "Blank when the checkpoint edited no existing function body.",
     how="<code>metrics.reedit_stats</code> blames each edited function's body at "
         "the current commit and bins every line into one of three eras: the "
         "original application, an earlier checkpoint, or this checkpoint. "
         "Counting whole bodies is deliberate, because it catches a one-line "
         "insertion into a large shared method, which blaming only the diff lines "
         "would miss.",
     read="This is both the comprehension cost and the mechanism for unintended "
          "regressions, in one number.",
     caveat="Blank on any checkpoint that only added new units, which is why the "
            "line is sparser in the distributed arm. A blank is a result, not "
            "missing data: it means nothing old was reopened.")

_add("change_entropy_norm",
     title="Change spread for this rule (entropy)",
     group="blast", direction="",
     source="Hassan 2009 change entropy, normalised",
     what="How evenly this one change request's diff spread across files, on a "
          "scale of 0 to 1. Hassan's original finding was that scattered changes "
          "predict faults better than the volume of change does, which is why the "
          "measure exists at all. It is the cleanest placement measure in the "
          "suite, because it is pure git with no parse and nothing bespoke.",
     formula="H = &minus;&Sigma;<sub>i</sub> p<sub>i</sub> log<sub>2</sub> "
             "p<sub>i</sub><br>H<sub>norm</sub> = H / log<sub>2</sub> n",
     terms="<b>p<sub>i</sub></b> is file <i>i</i>'s share of the lines this "
           "checkpoint changed, taken from <code>git diff --numstat</code>. "
           "<b>n</b> is the number of files with at least one changed line. With "
           "fewer than two such files the value is 0 by definition, because a "
           "change confined to one file has no spread.",
     how="<code>placement.change_entropy</code> with the previous checkpoint as "
         "the left-hand side, over the <code>src/main</code> pathspec.",
     read="Read this one carefully. <b>The direction depends on your theory.</b> "
          "High entropy means the change was scattered, which Hassan associates "
          "with faults. But a distributed architecture scatters by design, into "
          "files that did not previously exist. Use the cumulative version below "
          "for the architectural claim. Use this one for the per-change fault "
          "risk.")

_add("change_top1",
     title="Share of this rule's changed lines in one file",
     group="blast", direction="",
     source="concentration ratio CR1 over the checkpoint diff",
     what="Of the lines this change request touched, what fraction landed in a "
          "single file.",
     formula="CR<sub>1</sub> = max<sub>i</sub> lines<sub>i</sub> / "
             "&Sigma;<sub>j</sub> lines<sub>j</sub>",
     terms="<b>lines<sub>i</sub></b> is the changed-line count in file <i>i</i>, "
           "from <code>git diff --numstat</code>. Added and removed lines are both "
           "counted.",
     how="Same numstat parse as the change entropy.",
     read="Near 1.0 means the whole rule went into one file. For a rule landing in "
          "a <i>new</i> file that is ideal. For a rule landing in the <i>same</i> "
          "file as the last forty rules it is the god-file mechanism in action. The "
          "cumulative metrics below are what distinguish the two cases.")

_add("cum_change_entropy_norm",
     title="Cumulative change spread (entropy)",
     group="blast", direction="up",
     source="Hassan 2009 change entropy, cumulative from the baseline",
     what="The same spread question asked over all the change so far, rather than "
          "just this rule. This is the version that answers the architectural "
          "question, because it cannot be satisfied by a series of individually "
          "tidy diffs that all land in the same place.",
     formula="H<sub>norm</sub> = H / log<sub>2</sub> n, computed over "
             "diff(base, c)",
     terms="Identical to the per-rule entropy, except that the diff is taken from "
           "the <b>baseline commit</b> to the current checkpoint rather than from "
           "the previous checkpoint. So <b>p<sub>i</sub></b> is file <i>i</i>'s "
           "share of every line changed since the run began, and <b>n</b> is every "
           "file touched at least once.",
     how="The same <code>placement.change_entropy</code> call, which computes both "
         "prefixes in one pass from two numstat invocations.",
     read="An architecture where every rule lands in its own file keeps this high. "
          "An architecture where every rule lands in the same method keeps it low "
          "no matter how tidy any individual diff looked.")

_add("cum_change_top1",
     title="Share of all change so far in one file",
     group="blast", direction="down",
     source="concentration ratio CR1 over the cumulative diff",
     what="Across every rule so far, what fraction of all changed lines landed in "
          "a single file. The most legible cumulative concentration number: this "
          "much of everything this project did happened in one file.",
     formula="CR<sub>1</sub> = max<sub>i</sub> lines<sub>i</sub> / "
             "&Sigma;<sub>j</sub> lines<sub>j</sub>, over diff(base, c)",
     terms="<b>lines<sub>i</sub></b> is file <i>i</i>'s cumulative changed-line "
           "count since the baseline commit.",
     how="Same cumulative numstat as the cumulative entropy.",
     read="This is the figure to quote when you want one sentence rather than an "
          "index.")

_add("cum_change_top5",
     title="Share of all change so far in five files",
     group="blast", direction="down",
     source="concentration ratio CR5 over the cumulative diff",
     what="The same, widened to five files, so a cosmetic split of the hot file "
          "cannot fix it.",
     formula="CR<sub>5</sub> = &Sigma;<sub>i=1..5</sub> lines<sub>(i)</sub> / "
             "&Sigma;<sub>j</sub> lines<sub>j</sub>",
     terms="<b>lines<sub>(i)</sub></b> is the cumulative changed-line counts sorted "
           "descending, so the numerator is the five busiest files.",
     how="Same cumulative numstat.",
     read="If the top-1 share falls but this does not, the hot file was split "
          "rather than relieved.")

_add("cum_change_hhi",
     title="Cumulative change concentration (HHI)",
     group="blast", direction="down",
     source="Herfindahl-Hirschman index over cumulative per-file changed-line shares",
     what="The concentration index applied to history rather than to the current "
          "code. Two codebases can look structurally similar at the end while "
          "having got there very differently, and this is what tells them apart.",
     formula="HHI = &Sigma;<sub>i</sub> p<sub>i</sub><sup>2</sup>, &nbsp; "
             "p<sub>i</sub> = lines<sub>i</sub> / &Sigma;<sub>j</sub> lines<sub>j</sub>",
     terms="<b>p<sub>i</sub></b> is file <i>i</i>'s share of all lines changed "
           "since the baseline commit.",
     how="<code>placement.hhi</code> over the cumulative numstat.",
     read="The history view of concentration. It is the one metric here that a "
          "final-state snapshot cannot reproduce.",
     caveat=_NOT_SCALEFREE)

_add("cum_change_files",
     title="Files carrying the change so far",
     group="blast", direction="",
     source="harness, cumulative numstat",
     what="How many distinct files have been touched at least once since the "
          "baseline. It is the denominator behind the cumulative concentration "
          "metrics, and a plain statement of how wide the project's footprint has "
          "grown.",
     formula="cum_change_files = | { i : lines<sub>i</sub> &gt; 0 } | over "
             "diff(base, c)",
     terms="Counted over the cumulative numstat, so a file touched at change "
           "request 3 still counts at change request 60.",
     how="Same cumulative numstat parse.",
     read="Read it beside the cumulative HHI, which it deflates for free.")


# =========================================================================
# IMPACT: the bespoke score the interventions were optimising
# =========================================================================
_IMPACT_TERMS = (
    "<b>cost(f)</b> is the per function term. <b>WMC_other(f)</b> is the summed "
    "cyclomatic complexity of the <i>other</i> methods in <i>f</i>'s class, which "
    "stands for the context you must hold in your head to change <i>f</i> safely. "
    "A brand-new class has <b>WMC_other = 0</b>, which the "
    "<code>max(&hellip;, 1)</code> floors to 1, so a new isolated unit still costs "
    "something. That floor is what closes the fragmentation loophole. "
    "<b>&Delta;lines(f)</b> is the changed-line count in <i>f</i>, and for a new "
    "function it is that function's own size. <b>files_changed</b> is the number "
    "of distinct production Java files the commit touched, applied as a "
    "multiplier, so scattering one rule across many classes is not free.")
_IMPACT_CAVEAT = (
    "<b>This score was defined on this experiment, so it cannot be the evidence "
    "for a claim about this experiment.</b> It is also the quantity two of the "
    "four conditions were optimising, which makes it the clearest Goodhart "
    "demonstration here. Watch it collapse in those conditions while the "
    "published, externally defined metrics move far less.")

_add("impact_composite",
     title="Structural impact: the composite score",
     group="impact", direction="down",
     source="defined in this harness (harness/metrics.py)",
     what="One number for how much a change cost the structure. It is blast radius "
          "weighted by the complexity of the context that was disturbed. Editing a "
          "method inside a heavy god class costs far more here than the same edit "
          "inside an isolated unit, which is the whole design.",
     formula="cost(f) = max(WMC_other(f), 1) &middot; CC(f) &middot; "
             "max(1, &Delta;lines(f))<br>"
             "impact_composite = files_changed &middot; "
             "&Sigma;<sub>f &isin; changed</sub> cost(f)",
     terms=_IMPACT_TERMS + " The sum runs over every changed function, both "
           "modified and new. A within-commit rename is charged as a mutation "
           "rather than a free addition when the two bodies have a line-set "
           "Jaccard similarity of at least 0.6.",
     how="<code>metrics.impact_stats</code> parses each touched file at both the "
         "previous and the current commit with lizard, matches functions by name, "
         "and falls back to body similarity for renames. Note what it cannot see: "
         "only lines inside a parsed function body count, so logic expressed "
         "declaratively, in a MapStruct expression, in <code>openapi.yml</code>, "
         "in <code>schema.sql</code> or in OfficeFloor's wiring, scores zero. Both "
         "arms have that escape hatch, so it is not an arm bias, but read a zero "
         "as “the logic went where this metric cannot look” rather than as "
         "“the change was cheap”.",
     read="The scale is large and heavily skewed, because it is a product of four "
          "terms. The shape of the line matters far more than its value.",
     caveat=_IMPACT_CAVEAT)

_add("impact_mutation",
     title="Structural impact: disturbing existing functions",
     group="impact", direction="down",
     source="this harness",
     what="The half of the impact score that comes from modifying code that "
          "already existed. This is the component that carries the discrimination "
          "between the two architectures, because the context weight means a "
          "mandated rule revision is genuine architectural signal rather than "
          "spurious re-touching.",
     formula="impact_mutation = files_changed &middot; "
             "&Sigma;<sub>f &isin; modified &cup; renamed</sub> cost(f)",
     terms=_IMPACT_TERMS + " The sum is restricted to functions that existed at "
           "the previous commit and were modified, plus those detected as renames "
           "by the 0.6 Jaccard rule.",
     how="Same single pass as the composite.",
     read="This is where the two architectures separate most sharply. If the "
          "composite moves and this does not, the movement was all in additions.",
     caveat=_IMPACT_CAVEAT)

_add("impact_godclass",
     title="Structural impact: adding new functions",
     group="impact", direction="down",
     source="this harness",
     what="The half of the impact score that comes from new code: new files and "
          "new methods added to existing classes. It is reported so the "
          "composite's behaviour can be attributed to the right half.",
     formula="impact_godclass = files_changed &middot; "
             "&Sigma;<sub>f &isin; new</sub> cost(f)",
     terms=_IMPACT_TERMS + " The sum covers functions with no counterpart at the "
           "previous commit. For these <b>&Delta;lines(f)</b> is the new "
           "function's own line count, and <b>WMC_other</b> is 0 in a brand-new "
           "class, floored to 1.",
     how="Same single pass as the composite.",
     read="Because of the floor and the spread multiplier, both architectures pay "
          "something for additions. So this component does <i>not</i> separate "
          "them cleanly, and that is correct. The discrimination is supposed to "
          "live in the mutation term.",
     caveat=_IMPACT_CAVEAT)

for _base, _label in (("impact_composite", "composite"),
                      ("impact_mutation", "mutation of existing functions"),
                      ("impact_godclass", "new-function additions")):
    _add(_base + "_add",
         title=f"Structural impact ({_label}): purely additive rules only",
         group="impact", direction="down",
         source="this harness, filtered view",
         what="The same impact score, restricted to the change requests that only "
              "<i>add</i> a rule and never revise an earlier one. This is the easy "
              "case, where an architecture is not asked to change its mind about "
              "anything.",
         formula=f"value(c) = {_base}(c) if c is additive, else blank",
         terms="A change request is <b>additive</b> when the checkpoint plan "
               "declares no <code>mutates</code> list for it. The filtered field "
               "is left blank, not zero, on the other checkpoints. Blank matters: "
               "a zero would drag the mean of this view toward nothing on every "
               "revision checkpoint, which would make the two views "
               "incomparable.",
         how="Derived in the gallery and in <code>analyze</code> from the base "
             "field and the <code>checkpoint_type</code> column. It is never "
             "written to the per-checkpoint CSV.",
         read="If a condition only looks good here, it only looks good when nothing "
              "has to change.",
         caveat=_IMPACT_CAVEAT)
    _add(_base + "_mut",
         title=f"Structural impact ({_label}): rule-revision rules only",
         group="impact", direction="down",
         source="this harness, filtered view",
         what="The same impact score, restricted to the change requests that "
              "deliberately revise an earlier rule. Fourteen of the sixty change "
              "requests are of this kind, and they are placed deliberately rather "
              "than at random.",
         formula=f"value(c) = {_base}(c) if c is mutative, else blank",
         terms="A change request is <b>mutative</b> when the checkpoint plan "
               "declares a <code>mutates</code> list, naming the earlier rules it "
               "is allowed to change. Additive checkpoints are blanked, for the "
               "same reason as above.",
         how="Same derivation. Unlike the correctness metrics, the impact score "
             "keeps the mutative checkpoints in its base field rather than "
             "discounting them, because the context weight makes a mandated "
             "revision genuine architectural signal.",
         read="<b>The interesting case.</b> Revising an existing rule is where an "
              "architecture either pays for having isolated the concern or does "
              "not. In the control run the concentrated arm paid roughly 36,000 "
              "per revision. The distributed arm paid 4,800.",
         caveat=_IMPACT_CAVEAT)


# =========================================================================
# COHESION
# =========================================================================
_CK_SCOPE = ("Computed by the CK tool, which parses source with Eclipse JDT. Only "
             "declared source classes are seen: library types are not, and neither "
             "is anything the parser fails on, so the class count in the validity "
             "group is worth checking beside any CK figure.")

_add("ck_lcom_mean",
     title="Lack of cohesion, average class (LCOM)",
     group="cohesion", direction="down",
     source="Chidamber & Kemerer 1994, via the CK tool",
     what="Counts the method pairs in a class that share no field, against the "
          "pairs that do. A class whose methods all touch the same state is one "
          "idea. A class whose methods touch disjoint state is several classes "
          "wearing one name. This is the numeric version of what the "
          "plain-English cohesion prompt asked for in words.",
     formula="LCOM(C) = max(0, |P| &minus; |Q|)<br>"
             "ck_lcom_mean = mean over classes of LCOM(C)",
     terms="<b>P</b> is the set of method pairs in <i>C</i> whose accessed-field "
           "sets are disjoint. <b>Q</b> is the set of pairs that share at least "
           "one field. <b>Low is cohesive.</b> The measure is unbounded above and "
           "grows roughly with the square of the method count, so a large class is "
           "penalised twice: once for incoherence and once for being large.",
     how=_CK_SCOPE + " The harness reads CK's per-class LCOM column and takes the "
         "mean, and separately the maximum.",
     read="The natural place to check whether asking the agent for cohesion "
          "actually produced it.",
     caveat="Unbounded and method-count sensitive. Read it with the normalised "
            "LCOM* below and with tight class cohesion, which has the opposite "
            "sign. Agreement across all three is what makes a cohesion claim safe.")

_add("ck_lcom_max",
     title="Lack of cohesion, worst class",
     group="cohesion", direction="down",
     source="C&K 1994, via CK",
     what="The least cohesive class in the codebase. Unlike the mean it cannot be "
          "diluted by adding cohesive classes, so it answers whether there is a "
          "junk-drawer class in here, rather than whether classes are cohesive on "
          "average.",
     formula="ck_lcom_max = max over classes of LCOM(C)",
     terms="Same LCOM as above. Because it is unbounded and grows with method "
           "count, the worst class is often simply the largest one, so read it "
           "beside the class-weight concentration index.",
     how=_CK_SCOPE,
     read="A step change here means a junk drawer appeared.")

_add("ck_lcom_star_mean",
     title="Lack of cohesion, normalised (LCOM*)",
     group="cohesion", direction="down",
     source="Henderson-Sellers 1996, via CK",
     what="A redesign of LCOM that is bounded roughly to the range 0 to 1 and does "
          "not simply grow with the number of methods. Because it is normalised, a "
          "difference here is a difference in shape rather than in class size, "
          "which is exactly the correction the original LCOM needs.",
     formula="LCOM* (C) = ( (1/a) &Sigma;<sub>j=1..a</sub> &mu;(a<sub>j</sub>) "
             "&minus; m ) / ( 1 &minus; m )",
     terms="<b>m</b> is the number of methods in <i>C</i> and <b>a</b> the number "
           "of fields. <b>&mu;(a<sub>j</sub>)</b> is how many of those methods "
           "access field <i>j</i>. So the first term is the average number of "
           "methods per field. If every method touches every field the numerator "
           "is <b>m &minus; m = 0</b> and the result is 0, meaning perfectly "
           "cohesive. If each field is touched by exactly one method the result "
           "approaches 1. <b>Low is cohesive.</b> Undefined for a class with fewer "
           "than two methods or no fields.",
     how=_CK_SCOPE,
     read="The version to prefer when comparing arms whose classes differ in size.")

_add("ck_tcc_mean",
     title="Tight class cohesion (TCC)",
     group="cohesion", direction="up",
     source="Bieman & Kang 1995, via CK",
     what="The fraction of method pairs in a class that are directly connected "
          "through shared field access. It is reported precisely because its "
          "direction is inverted relative to LCOM: if a condition improves LCOM "
          "and worsens TCC, the improvement is an artefact of one definition "
          "rather than a real gain in cohesion.",
     formula="TCC(C) = NDC / NP, &nbsp; NP = m(m &minus; 1) / 2",
     terms="<b>m</b> is the number of visible methods. <b>NP</b> is therefore every "
           "possible pair of them. <b>NDC</b> is the number of pairs that are "
           "<i>directly</i> connected, meaning they access at least one instance "
           "variable in common. <b>High is cohesive</b>, which is the opposite "
           "sign to LCOM. Undefined, and blank, for a class with fewer than two "
           "methods.",
     how=_CK_SCOPE,
     read="Agreement with LCOM in the opposite direction is what makes a cohesion "
          "claim safe. Disagreement means one definition is doing the work.")

_add("ck_lcc_mean",
     title="Loose class cohesion (LCC)",
     group="cohesion", direction="up",
     source="Bieman & Kang 1995, via CK",
     what="The same as tight cohesion, but it also counts methods connected "
          "indirectly, through a chain of other methods. It is always at least as "
          "high as the tight version, and the gap between them is informative on "
          "its own.",
     formula="LCC(C) = (NDC + NIC) / NP",
     terms="<b>NIC</b> is the number of pairs connected only <i>indirectly</i>: "
           "not sharing a field themselves, but linked through a chain of methods "
           "that do. <b>NDC</b> and <b>NP</b> are as in TCC. <b>High is "
           "cohesive.</b>",
     how=_CK_SCOPE,
     read="A large gap between LCC and TCC means the class holds together only "
          "through intermediaries, which is weaker cohesion than the LCC figure "
          "alone suggests.")

_add("ck_handler_lcom",
     title="Lack of cohesion of the handler class",
     group="cohesion", direction="down",
     source="C&K 1994, via CK, pinned to the handler class",
     what="Cohesion of the one class both architectures agree is the entry point. "
          "Codebase averages can be moved by adding files. This cannot.",
     formula="ck_handler_lcom = LCOM(H)",
     terms="<b>H</b> is the handler class, matched by name in CK's per-class "
           "output. Same LCOM definition as the codebase mean. <b>Low is "
           "cohesive.</b>",
     how=_CK_SCOPE,
     read="The like-for-like cohesion comparison. A controller accumulating rules "
          "that touch disjoint state climbs here.")

_add("ck_handler_tcc",
     title="Tight cohesion of the handler class",
     group="cohesion", direction="up",
     source="Bieman & Kang 1995, via CK, pinned to the handler class",
     what="The inverted-sign cohesion check, on the handler class.",
     formula="ck_handler_tcc = TCC(H) = NDC(H) / NP(H)",
     terms="Same TCC definition. <b>High is cohesive.</b> Undefined, and therefore "
           "blank, for a handler class with fewer than two methods, because there "
           "are no pairs to connect.",
     how=_CK_SCOPE,
     read="Sparse by construction in whichever arm keeps its handler minimal. The "
          "blanks are a result, not missing data: a handler with one method has no "
          "cohesion to measure.")

_add("ck_dit_mean",
     title="Depth of inheritance tree",
     group="cohesion", direction="down",
     source="Chidamber & Kemerer 1994, via CK",
     what="How deep the class hierarchy goes, on average. It is reported to show "
          "that neither architecture is achieving its structure through "
          "inheritance, which matters because none of the other metrics on this "
          "page would attribute complexity hidden in a hierarchy correctly.",
     formula="DIT(C) = number of edges from C up to the root<br>"
             "ck_dit_mean = mean over classes of DIT(C)",
     terms="A class extending nothing has <b>DIT = 1</b> in CK's convention, "
           "counting <code>Object</code> as the root. Interfaces implemented do "
           "not add depth.",
     how=_CK_SCOPE,
     read="Flat and low in both arms is the expected and desired result. A rise "
          "would mean complexity moved into a hierarchy.")


# =========================================================================
# TAX: counter-signals, expected to favour the concentrated arm
# =========================================================================
_add("indirection_median",
     title="Call hops from a handling step",
     group="tax", direction="down",
     source="harness breadth-first search over the call graph",
     what="How many calls deep you have to go, from a handling step, to reach the "
          "code that does the work. Every hop is a file a developer has to open. "
          "This is the sceptic's objection made numeric: you did not remove the "
          "complexity, you buried it behind indirection.",
     formula="depth(k) = length of the shortest call path from any node to k<br>"
             "indirection_median = median<sub>k &isin; reached</sub> depth(k)",
     terms="<b>reached</b> is every method reachable from the handling nodes. The "
           "handling nodes themselves have <b>depth 0</b>. Depth is assigned by "
           "breadth-first search, so it is the shortest path, not the longest. The "
           "harness also records how many methods were reached, as "
           "<code>indirection_reached</code>, which is the denominator.",
     how="<code>placement.indirection_stats</code>, sharing the same call index as "
         "the comprehension metrics.",
     read="<b>Expected to favour the concentrated arm.</b> Everything in one method "
          "is zero hops away. This is Brooks' accidental complexity as a number, "
          "and it is the honest price of decomposition.",
     caveat="<b>It understates a pipeline architecture.</b> Depth is measured from "
            "the handling nodes, so a pipeline's twenty wired steps are all at "
            "depth 0 while a single-handler arm has exactly one depth-0 method. "
            "Worse, a pipeline's hops between steps are declared in YAML and "
            "dispatched by the container, so they are not Java calls and do not "
            "appear here at all. The honest reading of a pipeline arm is this "
            "depth <i>plus</i> its step count. Quoting this column alone would let "
            "the arm with the most indirection report the least.")

_add("indirection_max",
     title="Deepest call chain",
     group="tax", direction="down",
     source="harness breadth-first search over the call graph",
     what="The longest shortest-path from a handling step to any reachable method. "
          "It is the worst-case navigation cost for one change.",
     formula="indirection_max = max<sub>k &isin; reached</sub> depth(k)",
     terms="Same depth assignment as the median. Because every depth is a shortest "
           "path, this is the eccentricity of the reachable set rather than the "
           "length of the longest walk.",
     how="Same single pass.",
     read="A rising maximum with a flat median means one long tail appeared rather "
          "than a general deepening.")

_add("indirection_deep_share",
     title="Share of reached methods more than two hops away",
     group="tax", direction="down",
     source="harness breadth-first search over the call graph",
     what="Of everything the request path reaches, what fraction is far enough "
          "away that you would not find it by reading the handler. It is a "
          "distribution-shape measure rather than an extreme: not how deep the "
          "deepest is, but how much of the system lives out in the far field.",
     formula="indirection_deep_share = | { k : depth(k) &gt; 2 } | / | reached |",
     terms="The threshold of <b>2</b> is a choice, and it is the only arbitrary "
           "constant in this group. It is meant as “further than the handler and "
           "the thing it obviously calls”.",
     how="Same single pass.",
     read="Expected to be a counter-signal, like the rest of this group.")

_add("ck_cbo_mean",
     title="Coupling between objects, average class",
     group="tax", direction="down",
     source="Chidamber & Kemerer 1994, via CK",
     what="How many other classes a class depends on. Splitting one class into six "
          "creates coupling between the six that did not exist before, so this is "
          "expected to be a counter-signal.",
     formula="CBO(C) = | { D &ne; C : C references D or D references C } |<br>"
             "ck_cbo_mean = mean over classes of CBO(C)",
     terms="A <b>reference</b> is any use of the other class: a field type, a "
           "parameter type, a local variable, a method call, a thrown exception. "
           "CK counts distinct classes, not distinct references, so calling one "
           "class fifty times still counts 1. " + _CK_SCOPE,
     how=_CK_SCOPE,
     read="If a distributed architecture keeps this flat while adding units, that "
          "is a real result in its favour, because it is the objection you would "
          "most expect to land.")

_add("ck_cbo_max",
     title="Coupling between objects, worst class",
     group="tax", direction="down",
     source="C&K 1994, via CK",
     what="The single most entangled class in the codebase.",
     formula="ck_cbo_max = max over classes of CBO(C)",
     terms="Same CBO definition as the mean.",
     how=_CK_SCOPE,
     read="Where the mean is diluted by many small classes, the maximum is not. A "
          "rising maximum with a flat mean means one class is becoming the hub.")

_add("ck_fanout_mean",
     title="Fan-out, average class",
     group="tax", direction="down",
     source="CK",
     what="How many other classes a class calls out to. It is the directional half "
          "of coupling: not how entangled a class is, but how much it depends on "
          "others.",
     formula="fanout(C) = | { D : C references D } |<br>"
             "ck_fanout_mean = mean over classes of fanout(C)",
     terms="Unlike CBO this counts only outgoing references. CK records the "
           "incoming direction separately as fan-in, which the harness also "
           "stores.",
     how=_CK_SCOPE,
     read="Rising fan-out with flat fan-in is the orchestrator shape: a class that "
          "coordinates rather than one that is depended upon.")

_add("ck_rfc_mean",
     title="Response for a class, average",
     group="tax", direction="down",
     source="Chidamber & Kemerer 1994, via CK",
     what="How many distinct methods could end up executing in response to one "
          "message to this class. That is its own methods plus everything they "
          "call. It is roughly the size of the behaviour you have to consider when "
          "you call into a class, which makes it both a testability and a "
          "comprehension measure.",
     formula="RFC(C) = | M(C) &cup; &bigcup;<sub>m &isin; M(C)</sub> R(m) |<br>"
             "ck_rfc_mean = mean over classes of RFC(C)",
     terms="<b>M(C)</b> is the methods declared by <i>C</i>. <b>R(m)</b> is the "
           "set of methods invoked by <i>m</i>. CK uses the one-level version, "
           "which is the common implementation: it counts methods called "
           "<i>directly</i> by the class's own methods and does not recurse.",
     how=_CK_SCOPE,
     read="It rises with both concentration and indirection, which makes it a "
          "useful tiebreaker between those two stories.")

_add("ck_rfc_max",
     title="Response for a class, worst",
     group="tax", direction="down",
     source="C&K 1994, via CK",
     what="The class with the largest response set. The worst thing in the "
          "codebase to call into.",
     formula="ck_rfc_max = max over classes of RFC(C)",
     terms="Same one-level RFC definition as the mean.",
     how=_CK_SCOPE,
     read="Read it beside the handler's own RFC below. If the worst class in the "
          "codebase is the handler, that is the thesis. If it is something else, "
          "say so.")

_add("ck_handler_rfc",
     title="Response set of the handler class",
     group="tax", direction="down",
     source="CK, pinned to the handler class",
     what="How much behaviour is reachable from one call into the endpoint's class. "
          "It is closely related to the whole-path complexity in the comprehension "
          "group, but computed by a different tool, in units of methods rather "
          "than branches, and only one level deep.",
     formula="ck_handler_rfc = | M(H) &cup; &bigcup;<sub>m &isin; M(H)</sub> R(m) |",
     terms="<b>H</b> is the handler class. One level only, so unlike the "
           "comprehension walk this does not follow the call graph transitively.",
     how=_CK_SCOPE,
     read="A second opinion on the handler's comprehension load, from a tool with "
          "a different parser and a different definition.")

_add("ck_handler_cbo",
     title="Coupling of the handler class",
     group="tax", direction="down",
     source="CK, pinned to the handler class",
     what="How many other classes the endpoint's own class depends on. A handler "
          "that collects dependencies is a handler that is accumulating "
          "responsibilities.",
     formula="ck_handler_cbo = | { D &ne; H : H references D or D references H } |",
     terms="Same CBO definition, scoped to the handler class.",
     how=_CK_SCOPE,
     read="In a pipeline architecture the dependencies move to the wiring, which is "
          "exactly the kind of relocation the framework-dispatch caveat is about. "
          "A very low figure here for an arm implementing sixty rules is a prompt "
          "to check the validity group.")

_add("pmd_demeter_violations",
     title="Law of Demeter violations",
     group="tax", direction="down",
     source="Lieberherr & Holland 1989, via PMD",
     what="Places where code reaches through one object to get at another, as in "
          "<code>a.getB().getC().doThing()</code>. It is the classic symptom of a "
          "class knowing too much about its neighbours' internals, and it is "
          "another externally defined detector with thresholds nobody here chose.",
     formula="pmd_demeter_violations = count of method calls whose receiver is not "
             "<code>this</code>, a parameter, a locally created object, or a field "
             "of <code>this</code>",
     terms="The law says a method may only call methods on: itself, its own "
           "parameters, objects it created, and its own fields. PMD's rule reports "
           "one violation per offending call site, so a single long chain can "
           "contribute several.",
     how="PMD's <code>LawOfDemeter</code> rule, from the same single spawn as the "
         "complexity measures.",
     read="It tends to rise with distribution, so treat it as a counter-signal. It "
          "is also a famously noisy rule, so read the trend rather than the "
          "absolute count.")

_add("propagation_cost",
     title="Propagation cost",
     group="tax", direction="down",
     source="MacCormack, Rusnak & Baldwin 2006",
     what="If you change a random file, what fraction of the codebase could feel "
          "it? It is the density of the transitive closure of the file dependency "
          "matrix, and it is the one whole-architecture coupling number here with "
          "real pedigree in the modularity literature.",
     formula="propagation_cost = &Sigma;<sub>i=1..n</sub> | reach(i) | / "
             "n<sup>2</sup>",
     terms="<b>n</b> is the number of production Java files. <b>reach(i)</b> is the "
           "set of <i>other</i> files reachable from file <i>i</i> by following "
           "call edges transitively, so a file does not count itself. The "
           "numerator is therefore the number of ordered reachable pairs, and "
           "dividing by <b>n<sup>2</sup></b> gives the expected fraction of the "
           "system a random change can touch.",
     how="<code>placement.propagation_cost</code> collapses the method call graph "
         "to a file graph, dropping self-edges, then runs a depth-first reach from "
         "every file.",
     read="Lower means better modularised. Use the between-arm comparison at the "
          "same change request and nothing else.",
     caveat="Two load-bearing caveats. First, the <b>n<sup>2</sup> denominator "
            "rewards having more files</b>, so an arm that splits the same code "
            "over more files scores lower for free. Second, it inherits a "
            "<b>conservative call resolver</b> that drops every edge it cannot "
            "prove. MacCormack reports 10 to 60 percent for real systems, so a "
            "value an order of magnitude below that means edges are missing rather "
            "than that the design is exceptional. Never quote the absolute value.")

_add("propagation_fanout_median",
     title="Files reachable from a typical file",
     group="tax", direction="down",
     source="MacCormack et al. 2006, unnormalised",
     what="The raw count behind propagation cost. From one file, how many files can "
          "you reach by following dependencies. Because it is not normalised it "
          "cannot be improved by adding files, which makes it the honest version.",
     formula="propagation_fanout_median = median<sub>i=1..n</sub> | reach(i) |",
     terms="Same file graph and same transitive reach as the propagation cost, "
           "with <b>no n<sup>2</sup> division</b>. The harness also records the "
           "maximum and the file count.",
     how="Same single pass as the propagation cost.",
     read="If the normalised and unnormalised numbers tell different stories, the "
          "difference is packaging rather than structure. That comparison is the "
          "reason both are reported.")


# =========================================================================
# DUPLICATION
# =========================================================================
_add("verbosity",
     title="Verbosity: duplicated and anti-pattern lines",
     group="duplication", direction="down",
     source="SlopCodeBench (arXiv:2603.24755) Eq. 4",
     what="The share of the codebase that is either copy-pasted from elsewhere in "
          "the same codebase or matches a known anti-pattern. This is the metric "
          "that catches the cheap way to score well on everything else on this "
          "page, which is to copy the logic into a new small class instead of "
          "factoring it out.",
     formula="verbosity = | clone_lines &cup; pattern_lines | / LOC",
     terms="<b>clone_lines</b> and <b>pattern_lines</b> are sets of "
           "<b>(file, line number)</b> pairs, not counts, which is what makes the "
           "union meaningful. The union rather than the sum matters: a line that is "
           "both duplicated and an anti-pattern is charged once. <b>LOC</b> is the "
           "production Java line count. The result can exceed 1 in principle, "
           "because the LOC denominator counts function bodies while the line sets "
           "are gathered over whole files.",
     how="<code>metrics.verbosity</code>. Clones come from jscpd, anti-patterns "
         "from PMD or ast-grep depending on the run's own config snapshot, so an "
         "old run replays with the detector it actually used. If one detector "
         "cannot run, the metric is computed from the other and the harness "
         "records which halves ran.",
     read="One of the four conditions produced exactly the failure this metric "
          "exists to catch. Read it beside the placement group, not on its own.")

_add("verbosity_clone_lines",
     title="Duplicated lines",
     group="duplication", direction="down",
     source="jscpd clone detection",
     what="The count of lines that appear as a near-identical block somewhere else "
          "in the codebase. It is the copy-paste half of verbosity, reported "
          "on its own so the two halves can be told apart.",
     formula="verbosity_clone_lines = | clone_lines |",
     terms="<b>clone_lines</b> is the set of (file, line) pairs jscpd reports as "
           "belonging to a duplicated block. Both copies of a clone are counted, "
           "because both are lines a maintainer has to keep in step. jscpd's "
           "minimum block size is what decides whether a short repeated idiom "
           "counts, and it is pinned in <code>tools/package.json</code> so the "
           "threshold cannot drift between runs.",
     how="jscpd at a pinned version, over the arm's source directories. "
         "<code>quality_selftest</code> fails closed if the pinned version is not "
         "what is installed.",
     read="A rising line here while the structural metrics improve is the signature "
          "of fragmentation masquerading as decomposition.")

_add("verbosity_pattern_lines",
     title="Anti-pattern lines",
     group="duplication", direction="down",
     source="PMD ruleset, or the ast-grep rules in astgrep-rules/",
     what="The count of lines matching structural anti-patterns. The rules are "
          "defined over the syntax tree rather than over text, so they survive "
          "reformatting and renaming, which makes them harder to game than a "
          "text-based lint.",
     formula="verbosity_pattern_lines = | pattern_lines |",
     terms="<b>pattern_lines</b> is the set of (file, line) pairs flagged by the "
           "configured detector. With PMD the ruleset is "
           "<code>pmd-rules/java-wasteful.xml</code>. With ast-grep it is the "
           "rules in <code>astgrep-rules/</code>. Which one applies is read from "
           "the run's own config snapshot.",
     how="From the same single PMD spawn as the complexity measures, filtered to "
         "the wasteful ruleset's rule names. The quality gate routes through the "
         "same choice, so gate and metric can never disagree about what a smell "
         "is.",
     read="The other half of verbosity. If this moves and the clone count does "
          "not, the agent is writing fresh bad code rather than copying old code.")


# =========================================================================
# VALIDITY guards
# =========================================================================
_add("container_total",
     title="Framework-dispatched classes: the call-graph escape counter",
     group="validity", direction="",
     source="harness; counts advice, aspects, filters, entity listeners and validators",
     what="How many classes are invoked by the framework rather than by an ordinary "
          "method call. This is not a finding. It is a lie detector for every "
          "other metric on this page that follows a call graph.",
     formula="container_total = advice + aspect + filter + entity_listener + "
             "validator",
     terms="Each term counts classes carrying the corresponding framework hook: "
           "<b>advice</b> is <code>@ControllerAdvice</code> or "
           "<code>@RestControllerAdvice</code>; <b>aspect</b> is "
           "<code>@Aspect</code>; <b>filter</b> is a servlet "
           "<code>Filter</code> or a <code>HandlerInterceptor</code>; "
           "<b>entity_listener</b> is <code>@EntityListeners</code> or a "
           "<code>@PrePersist</code> callback; <b>validator</b> is a "
           "<code>ConstraintValidator</code>. The harness stores each term "
           "separately as well as the total.",
     how="<code>placement.container_dispatch</code> scans the production Java files "
         "for those annotations and interfaces at the checkpoint commit.",
     read="<b>Not a finding. A lie detector.</b> No call-graph walk can see a class "
          "the container dispatches, so every comprehension metric on this page is "
          "measuring a shrinking fraction of the code wherever this line rises. In "
          "one condition, chains ended with eighteen advice classes and a handler "
          "containing the stock upstream body. The whole-path complexity read 3 "
          "for a codebase implementing all sixty rules. If this line has moved off "
          "its baseline for a condition, discount that condition's comprehension "
          "numbers rather than the thesis.")

_add("gate_invalid",
     title="Invalid test gates",
     group="validity", direction="down",
     source="harness resilience layer",
     what="Checkpoints where the test run itself failed in a way that would "
          "otherwise be scored as a mass regression. A crashed Surefire fork is the "
          "usual cause. It reports a successful build and zero selected tests, "
          "which naively scores as the entire prior suite regressing at once.",
     formula="gate_invalid(c) = 1 if build_ok &and; selected(c) = 0 &and; "
             "neighbours select many, else 0",
     terms="The signature is the conjunction: the build succeeded, no tests were "
           "selected, and the surrounding checkpoints select dozens. A checkpoint "
           "flagged this way is <b>excluded from correctness scoring and "
           "retried</b> rather than recorded as a failure.",
     how="Detected in <code>harness/correctness.py</code>, which blanks every "
         "correctness field and sets this flag. <code>analyze</code> also repairs "
         "old captures by the same signature, which is why any correctness number "
         "produced before the fix must be recomputed rather than trusted.",
     read="Should be flat at zero. It exists because an unflagged crashed fork once "
          "read as 143 regressions where the true figure was 0. The biggest risk "
          "to a study like this is infrastructure, not statistics.")

_add("total_selected",
     title="Tests selected per checkpoint",
     group="validity", direction="up",
     source="harness test selection",
     what="How many black-box acceptance tests ran at this checkpoint. That is this "
          "rule's own tests plus every prior rule's. It rises by construction as "
          "rules accumulate, and that rise is what makes the later change requests "
          "harder than the early ones.",
     formula="total_selected(c) = &Sigma;<sub>j=1..c</sub> | tests(j) |",
     terms="<b>tests(j)</b> is the acceptance tests belonging to change request "
           "<i>j</i>, across all four families. Selection is by change request "
           "number, so it is deterministic and identical in both arms.",
     how="The harness selects by checkpoint from <code>acceptance/</code> and runs "
         "them with Surefire after every checkpoint.",
     read="A smooth rise is correct. A sudden drop to zero at a checkpoint whose "
          "neighbours pass dozens is the crashed-fork signature above.")

_add("ck_classes",
     title="Classes seen by the independent parser",
     group="validity", direction="",
     source="CK tool",
     what="How many classes the second parser could read. A parser that fails on a "
          "file produces no metrics for it, which makes that file look perfect, so "
          "this is the cheapest available check that both tools are seeing the same "
          "codebase.",
     formula="ck_classes = number of rows in CK's per-class output",
     terms="CK counts real class declarations, so nested and inner classes appear "
           "as their own rows. That is why this figure normally sits above the file "
           "count rather than equal to it.",
     how="Row count of CK's class CSV at the checkpoint commit.",
     read="Compare the shape of this line against the file count. A divergence "
          "means CK started failing on something, and every CK metric on this page "
          "is then measuring less than it claims.")

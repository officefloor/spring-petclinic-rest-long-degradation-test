#!/usr/bin/env python3
"""Generate the academic-format Blogger post for the conservation paper.

The paper exists twice: as `paper/main.tex` for arXiv, and as a Blogger fragment
for the blog. Both quote the same forty-odd numbers. Typing them twice is how
the two versions drift, so the fragment is generated from the SAME literal
tables that the LaTeX carries, held here once.

House style is the blog's, enforced by `metric_gallery.check_catalog_style`'s
rules: short sentences, no dash punctuation, inline HTML rather than markdown,
and inline style attributes rather than a <style> block, because Blogger renders
a post body inside its own template and some themes strip <style>.

Usage:
    python -m tools.gallery.paper_post > blog/conserved-amount-paper.html
"""
from __future__ import annotations

import html
import sys

FIGS = "https://officefloor.github.io/spring-petclinic-rest-long-degradation-test/figs/"

S = {
    "h2": "margin: 2.1em 0 0.4em; font-size: 1.3em; line-height: 1.3;",
    "h3": "margin: 1.6em 0 0.35em; font-size: 1.08em; line-height: 1.3;",
    "code": "font-family: ui-monospace, Menlo, monospace; font-size: 0.95em;",
    "img": "width: 100%; height: auto; display: block; border: 1px solid rgb(221, 221, 221);",
    "cap": "margin: 0.5em 0 1.4em; font-size: 0.82em; color: rgb(136, 136, 136);",
    "table": "border-collapse: collapse; width: 100%; font-size: 0.86em; margin: 0.4em 0;",
    "th": "padding: 6px 10px 6px 0; text-align: left;",
    "thn": ("padding: 6px 0 6px 12px; text-align: right; font-size: 0.8em; "
            "letter-spacing: 0.05em; text-transform: uppercase; color: rgb(136, 136, 136);"),
    "td": "padding: 5px 10px 5px 0;",
    "tdn": ("padding: 5px 0 5px 12px; text-align: right; "
            "font-family: ui-monospace, Menlo, monospace; font-size: 0.9em;"),
    "tdb": ("padding: 5px 0 5px 12px; text-align: right; font-weight: bold; "
            "font-family: ui-monospace, Menlo, monospace; font-size: 0.9em;"),
    "trh": "border-bottom: 2px solid rgb(204, 204, 204); text-align: left;",
    "tr": "border-bottom: 1px solid rgb(238, 238, 238);",
    "trg": "border-bottom: 1px solid rgb(238, 238, 238); border-top: 1px solid rgb(204, 204, 204);",
    "grp": ("padding: 9px 10px 4px 0; font-style: italic; color: rgb(119, 119, 119); "
            "font-size: 0.95em;"),
    "sp": "color: rgb(235, 104, 52); font-weight: bold;",
    "of": "color: rgb(42, 120, 214); font-weight: bold;",
    "eq": ("margin: 1.1em 0; padding: 0.9em 1em; background: rgb(247, 247, 245); "
           "border: 1px solid rgb(225, 225, 220); border-radius: 4px; "
           "font-family: ui-monospace, Menlo, monospace; font-size: 0.95em; "
           "line-height: 1.9; overflow-x: auto;"),
    "note": "font-size: 0.87em; color: rgb(119, 119, 119);",
    "meta": "margin: 0 0 1.4em; font-size: 0.88em; color: rgb(119, 119, 119);",
    "ref": "font-size: 0.87em; color: rgb(85, 85, 85); margin: 0.3em 0;",
}

SP = f'<span style="{S["sp"]}">Spring</span>'
OF = f'<span style="{S["of"]}">OfficeFloor</span>'


def c(text):
    return f'<code style="{S["code"]}">{html.escape(text)}</code>'


def table(head, rows, aligns=None):
    """rows: list of either a list of cells, or ("GROUP", label)."""
    n = len(head)
    aligns = aligns or (["l"] + ["r"] * (n - 1))
    out = [f'<table style="{S["table"]}"><tbody>',
           f'<tr style="{S["trh"]}">' + "".join(
               f'<th style="{S["th"] if a == "l" else S["thn"]}">{h}</th>'
               for h, a in zip(head, aligns)) + "</tr>"]
    for row in rows:
        if isinstance(row, tuple) and row and row[0] == "GROUP":
            out.append(f'<tr style="{S["trg"]}"><td style="{S["grp"]}" '
                       f'colspan="{n}">{row[1]}</td></tr>')
            continue
        cells = []
        for i, (v, a) in enumerate(zip(row, aligns)):
            bold = isinstance(v, str) and v.startswith("*")
            v = v[1:] if bold else v
            st = S["td"] if a == "l" else (S["tdb"] if bold else S["tdn"])
            cells.append(f'<td style="{st}">{v}</td>')
        out.append(f'<tr style="{S["tr"]}">' + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def fig(name, caption):
    url = FIGS + name
    return (f'<p><a href="{url}" target="_blank"><img src="{url}" '
            f'alt="{html.escape(caption[:80])}" style="{S["img"]}" loading="lazy"></a></p>\n'
            f'<p style="{S["cap"]}">{caption}</p>')


# --------------------------------------------------------------------------
# The numbers. Same literals as paper/main.tex. Change both or neither.
# --------------------------------------------------------------------------
AMOUNT = [
    ("total_cc", "652 (21)", "694 (17)", "646 (23)", "642 (38)",
     "656 (12)", "681 (28)", "641 (20)", "597 (19)", "15%"),
    ("halstead_volume", "215,300", "220,800", "209,000", "206,100",
     "216,600", "221,500", "214,100", "207,800", "7%"),
    ("ck_wmc_total", "762 (20)", "826 (18)", "761 (21)", "750 (38)",
     "738 (12)", "766 (27)", "725 (21)", "679 (17)", "20%"),
    ("pmd_cognitive_total", "323 (14)", "293 (12)", "293 (11)", "283 (24)",
     "319 (17)", "289 (22)", "310 (23)", "268 (14)", "18%"),
]

ADDED = [
    ("total_cc", "239 (18)", "285 (15)", "236 (20)", "235 (35)", "20%",
     "296 (13)", "321 (27)", "280 (20)", "241 (18)", "28%"),
    ("halstead_volume", "56,500", "62,300", "51,100", "48,600", "25%",
     "58,800", "63,500", "56,200", "50,800", "22%"),
    ("ck_wmc_total", "235 (18)", "302 (16)", "238 (18)", "229 (35)", "29%",
     "297 (12)", "326 (26)", "283 (21)", "242 (17)", "29%"),
]

SPREAD = [
    ("GROUP", "Placement"),
    ("cum_change_top1", "110%", "11%", "*10.0"),
    ("cum_change_entropy_norm", "24%", "3%", "*9.2"),
    ("cum_change_hhi", "142%", "20%", "*7.3"),
    ("mi_mean", "5%", "1%", "*5.6"),
    ("ccdist_file_top1", "87%", "17%", "*5.3"),
    ("ck_cbo_mean", "14%", "3%", "*4.2"),
    ("ccdist_file_gini", "34%", "8%", "*4.1"),
    ("total_files", "37%", "9%", "*4.0"),
    ("ccdist_file_hhi", "106%", "28%", "*3.7"),
    ("node_cc_median", "87%", "24%", "*3.5"),
    ("wmcdist_class_hhi", "100%", "29%", "*3.4"),
    ("propagation_cost", "36%", "12%", "*2.9"),
    ("GROUP", "Amount"),
    ("halstead_volume", "7%", "6%", "1.1"),
    ("java_loc", "11%", "10%", "1.1"),
    ("total_fns", "15%", "16%", "1.0"),
    ("pmd_cognitive_total", "13%", "17%", "0.8"),
    ("ck_wmc_total", "10%", "12%", "0.8"),
    ("total_cc", "8%", "13%", "0.6"),
    ("GROUP", "Placement metrics showing no architecture effect"),
    ("ccdist_fn_gini", "15%", "14%", "1.1"),
    ("cogdist_fn_gini", "16%", "16%", "1.0"),
]

CONVERGE = [
    ("cum_change_top1", "0.344", "0.110", "*0.106"),
    ("ccdist_file_top1", "0.197", "0.078", "*0.086"),
    ("ccdist_file_hhi", "0.0727", "0.0232", "*0.0217"),
    ("wmcdist_class_hhi", "0.0554", "0.0191", "*0.0182"),
    ("cum_change_entropy_norm", "0.721", "0.921", "*0.886"),
]

REFS_UNSORTED = [
    # (key, first author surname for sorting, text)
    ("brooks", "Brooks",
     "F. P. Brooks Jr., &ldquo;No Silver Bullet: Essence and Accidents of Software "
     "Engineering,&rdquo; <i>IEEE Computer</i> 20(4), 10&ndash;19, 1987."),
    ("ck", "Chidamber",
     "S. R. Chidamber and C. F. Kemerer, &ldquo;A Metrics Suite for Object Oriented "
     "Design,&rdquo; <i>IEEE TSE</i> 20(6), 476&ndash;493, 1994."),
    ("aniche", "Aniche",
     'M. Aniche, &ldquo;Java code metrics calculator (CK),&rdquo; 2015. '
     '<a href="https://github.com/mauricioaniche/ck" target="_blank">github.com/mauricioaniche/ck</a>'),
    ("goodhart", "Goodhart",
     "C. A. E. Goodhart, &ldquo;Problems of Monetary Management: The U.K. "
     "Experience,&rdquo; in <i>Papers in Monetary Economics</i>, Reserve Bank of "
     "Australia, 1975."),
    ("halstead", "Halstead",
     "M. H. Halstead, <i>Elements of Software Science</i>, Elsevier, 1977."),
    ("hassan", "Hassan",
     "A. E. Hassan, &ldquo;Predicting Faults Using the Complexity of Code "
     "Changes,&rdquo; <i>ICSE</i>, 78&ndash;88, 2009."),
    ("hs", "Henderson-Sellers",
     "B. Henderson-Sellers, <i>Object-Oriented Metrics: Measures of Complexity</i>, "
     "Prentice Hall, 1996."),
    ("maccormack", "MacCormack",
     "A. MacCormack, J. Rusnak and C. Y. Baldwin, &ldquo;Exploring the Structure of "
     "Complex Software Designs,&rdquo; <i>Management Science</i> 52(7), "
     "1015&ndash;1030, 2006."),
    ("mccabe", "McCabe",
     "T. J. McCabe, &ldquo;A Complexity Measure,&rdquo; <i>IEEE TSE</i> SE-2(4), "
     "308&ndash;320, 1976."),
    ("norman", "Norman",
     "D. A. Norman, <i>Living with Complexity</i>, MIT Press, 2010. Discusses the "
     "conservation of complexity, attributed to Larry Tesler. Tesler's law has no "
     "canonical primary publication, so this is cited as a secondary source."),
    ("oman", "Oman",
     "P. Oman and J. Hagemeister, &ldquo;Metrics for Assessing a Software System's "
     "Maintainability,&rdquo; <i>ICSM</i>, 337&ndash;344, 1992."),
    ("strathern", "Strathern",
     "M. Strathern, &ldquo;'Improving ratings': audit in the British University "
     "system,&rdquo; <i>European Review</i> 5(3), 305&ndash;321, 1997."),
    ("slop", "Orlanski",
     "G. Orlanski, D. Roy, A. Yun, C. Shin, A. Gu, A. Ge, D. Adila, N. Roberts, "
     "F. Sala and A. Albarghouthi, &ldquo;SlopCodeBench: Benchmarking How Coding "
     "Agents Degrade Over Long-Horizon Iterative Tasks,&rdquo; arXiv:2603.24755, "
     "2026. Source of the erosion, verbosity and degradation slope methods, and of "
     "the prompt arm design."),
    ("sweci", "Chen",
     "J. Chen, X. Xu, H. Wei, C. Chen and B. Zhao, &ldquo;SWE-CI: Evaluating Agent "
     "Capabilities in Maintaining Codebases via Continuous Integration,&rdquo; "
     "arXiv:2603.03823, 2026. Source of the gate semantics, normalized change and "
     "zero regression rate."),
    ("repo", "Sagenschneider",
     'D. Sagenschneider, &ldquo;PetClinic-Evolve harness,&rdquo; 2026. The harness, '
     'the change request plan, the acceptance suite and the analysis code: '
     '<a href="https://github.com/officefloor/spring-petclinic-rest-long-degradation-test" '
     'target="_blank">github.com/officefloor/spring-petclinic-rest-long-degradation-test</a>'),
]

# Numbering is derived from the sort, never written down.
REFS_SORTED = sorted(REFS_UNSORTED, key=lambda e: e[1].lower())
REF_NUM = {k: i for i, (k, _s, _t) in enumerate(REFS_SORTED, 1)}


def r(key):
    """Reference marker, numbered by the bibliography's own sort order."""
    return f"[{REF_NUM[key]}]"


def build() -> str:
    o = []
    A = o.append

    A(f'<p style="{S["meta"]}"><i>Part of a '
      f'<a href="https://blog.officefloor.net/2026/08/architecture-as-independent-variable.html" '
      f'target="_blank">series</a> on how software architecture shapes AI driven code '
      f'degradation. This is the paper version of the argument. A PDF and the LaTeX '
      f'source are in the repository {r("repo")}, prepared for arXiv.</i></p>')

    # ---- Abstract
    A(f'<h2 style="{S["h2"]}">Abstract</h2>')
    A(f'<p>Tesler\'s conservation law holds that a problem carries an irreducible '
      f'amount of complexity, and Brooks separates that essential part from the '
      f'accidental part a solution adds. If the essential part is fixed, then '
      f'architecture is a question of placement rather than quantity. We test both '
      f'halves of that claim on a controlled experiment in which an AI coding agent '
      f'implements sixty accumulating change requests against a single REST endpoint, '
      f'ten independent runs per cell, with the model held fixed. The independent '
      f'variables are the architecture, a mutative {SP} controller against an additive '
      f'{OF} composed pipeline, and the instruction the agent receives, which is one of '
      f'four: a bare change request, a plain language request for cohesion, a tool that '
      f'grades each change and asks for a refactor, and the structural cost function '
      f'itself pasted into the prompt.</p>')
    A(f'<p>Across all eight cells the amount of complexity in the finished system '
      f'varies by 7% on total Halstead volume and 15% on total cyclomatic complexity, '
      f'and the complexity <i>added</i> by the sixty rules varies by 20% to 29% within '
      f'an architecture. Placement does not behave this way. We define a per metric '
      f'<b>intervention spread</b>, the range across the four conditions divided by '
      f'their mean, and report the ratio of the two architectures\' spreads. On amount '
      f'metrics that ratio is near 1: both architectures are equally immovable. On '
      f'twelve placement metrics it runs from 2.9 to 10.0, entirely because the mutative '
      f'architecture moves. Under its strongest intervention the mutative arm arrives at '
      f'the placement the additive arm occupies with no intervention at all. We report '
      f'the price: correctness fell under every intervention in both architectures, and '
      f'two placement metrics show no effect at all.</p>')

    # ---- 1
    A(f'<h2 style="{S["h2"]}">1 Introduction</h2>')
    A(f'<p>Larry Tesler\'s law of conservation of complexity holds that a problem '
      f'carries an irreducible amount of complexity, and that design moves it rather '
      f'than removing it {r("norman")}. Brooks draws the same line from the other direction, '
      f'separating the <i>essential</i> complexity that belongs to the problem from the '
      f'<i>accidental</i> complexity that a particular solution adds {r("brooks")}. Both claims '
      f'are widely quoted and rarely measured, because measuring them needs a setting in '
      f'which the problem is genuinely held fixed while the solution is genuinely allowed '
      f'to vary.</p>')
    A(f'<p>An AI coding agent working through a fixed list of change requests is such a '
      f'setting. The task is identical by construction. The model is identical. What can '
      f'be varied is the architecture the change lands in, and the instruction the agent '
      f'is given before it writes.</p>')
    A(f'<p>This paper reports a two by four study. Two architectures receive sixty '
      f'accumulating change requests each, under four instruction conditions, ten '
      f'independent runs per cell: 4,800 agent implementations in total.</p>')
    A(f'<p>The usual question to ask of such a design is which architecture ends up with '
      f'the better structure. We ask a prior one. If the amount of complexity is fixed by '
      f'the problem, then every architectural argument is an argument about arrangement, '
      f'and the interesting property of an architecture is not the arrangement it happens '
      f'to have but <b>how far that arrangement can be moved by anything other than the '
      f'architecture itself</b>. An architecture whose structure is set by the prompt, '
      f'the review or the dashboard is only as durable as the discipline applying '
      f'them.</p>')

    # ---- 2
    A(f'<h2 style="{S["h2"]}">2 Background and related work</h2>')
    A(f'<p><b>Complexity as a conserved quantity.</b> Tesler\'s law is normally invoked '
      f'in interface design, where the question is whether the user or the program '
      f'absorbs a step {r("norman")}. Its software engineering form is Brooks\' essence and '
      f'accident distinction {r("brooks")}. Neither is usually stated in a way that a '
      f'measurement could falsify, which is what this study tries to supply.</p>')
    A(f'<p><b>Measuring amount.</b> We use four operationalisations that rest on '
      f'different theories, so that agreement between them is evidence rather than an '
      f'artefact of one definition: McCabe\'s cyclomatic complexity over control flow '
      f'{r("mccabe")}, Halstead volume over program vocabulary {r("halstead")}, weighted methods per '
      f'class from the Chidamber and Kemerer suite {r("ck")}, and PMD\'s cognitive '
      f'complexity over nesting.</p>')
    A(f'<p><b>Measuring arrangement.</b> Concentration is measured with the '
      f'Herfindahl-Hirschman index and the Gini coefficient over per file and per class '
      f'complexity shares, which answer "how unequally is this spread" while staying '
      f'silent on the total. Change is measured with Hassan\'s change entropy {r("hassan")}, '
      f'applied cumulatively over the whole run rather than per commit. Coupling is '
      f'measured with CK\'s coupling between objects {r("ck")} and with MacCormack\'s '
      f'propagation cost {r("maccormack")}. The Maintainability Index {r("oman")} is computed per file '
      f'and averaged. Cohesion is measured with LCOM {r("ck")}{r("hs")}.</p>')
    A(f'<p><b>Measurement under optimisation pressure.</b> Goodhart\'s law, in '
      f'Strathern\'s formulation, holds that a measure which becomes a target ceases to '
      f'be a good measure {r("goodhart")}{r("strathern")}. Two of our four conditions apply deliberate '
      f'optimisation pressure, and one applies it to a disclosed formula. We therefore '
      f'report which of our metrics survived that pressure and which did not, and exclude '
      f'the optimised score itself from every claim.</p>')
    A(f'<p><b>Agentic degradation benchmarks.</b> The erosion, verbosity and degradation '
      f'slope methods, and the idea of contrasting prompt arms, follow SlopCodeBench '
      f'{r("slop")}. The gate semantics, normalized change and zero regression rate follow '
      f'SWE-CI {r("sweci")}.</p>')

    # ---- 3
    A(f'<h2 style="{S["h2"]}">3 The question and the statistic</h2>')
    A(f'<p>Suppose the amount of complexity is fixed by the problem. Then two '
      f'architectures that solve it differ only in arrangement, and the arrangement of '
      f'any given codebase is the joint product of the architecture and everything else '
      f'that shaped it: the prompt, the review, the metric on the dashboard. An '
      f'architecture whose arrangement is substantially determined by those other things '
      f'is one whose structure is only as durable as the discipline applying them. An '
      f'architecture whose arrangement is determined by its own composition is not.</p>')
    A(f'<p>That is an empirical question, and it needs a statistic. For a metric '
      f'<i>m</i> and an architecture <i>a</i>, let &mu;<sub>c</sub>(<i>m</i>,<i>a</i>) '
      f'be the mean over ten runs of the per run mean of <i>m</i> over the final phase, '
      f'under condition <i>c</i>.</p>')
    A(f'<div style="{S["eq"]}">'
      f'S(<i>m</i>,<i>a</i>) = ( max<sub>c</sub> &mu;<sub>c</sub> &minus; '
      f'min<sub>c</sub> &mu;<sub>c</sub> ) / | mean<sub>c</sub> &mu;<sub>c</sub> |'
      f'<br>R(<i>m</i>) = S(<i>m</i>, Spring) / S(<i>m</i>, OfficeFloor)</div>')
    A(f'<p>S is the <b>intervention spread</b>. It asks how far an intervention moved an '
      f'architecture on that metric, expressed relative to the metric\'s own level so '
      f'that metrics on different scales are comparable. R is the <b>plasticity '
      f'ratio</b>. It asks whether the two architectures were moved equally. Under Tesler '
      f'conservation, amount metrics should have small S for both architectures, and '
      f'therefore R near 1. The thesis of this paper is that placement metrics have R '
      f'much greater than 1.</p>')
    A(f'<p>Both are descriptive statistics over four points. They are not hypothesis '
      f'tests, and section 7 says what follows from that.</p>')

    # ---- 4
    A(f'<h2 style="{S["h2"]}">4 Study design</h2>')
    A(f'<p><b>Task.</b> A fixed plan of sixty change requests, each adding or revising a '
      f'business rule on one endpoint, {c("POST /api/owners")}, of the Spring PetClinic '
      f'REST application. The plan and its acceptance suite were frozen on 2026-08-08, '
      f'before the earliest of the four runs reported here, so all four conditions faced '
      f'an identical task.</p>')
    A(f'<p><b>Architectures.</b> The <i>mutative</i> arm is an idiomatic Spring '
      f'{c("@RestController")}: a rule is a statement added to a handler method. The '
      f'<i>additive</i> arm is the same application built with OfficeFloor, where the '
      f'endpoint is a YAML composed graph of functions and a rule is a new function and a '
      f'new edge. Both arms implement the same sixty rules and are held to the same black '
      f'box acceptance suite, which the agent never sees.</p>')
    A(f'<p><b>Agent.</b> {c("claude-opus-4-8")}, held fixed across all cells. Each change '
      f'request is a fresh session with no memory of the previous one, so the agent '
      f're-reads whatever it needs from the code itself. Nothing but the code crosses '
      f'between checkpoints.</p>')
    A(f'<p><b>Conditions.</b> Four, each a full sweep of both architectures at ten runs '
      f'each, each changing exactly one lever.</p>')
    A(table(["condition", "lever", "what the agent was given"],
            [[c("just-solve"), "control", "The change request and nothing else."],
             [c("cohesion-prompt"), "prompt",
              "One plain language paragraph asking for well structured code. "
              "No metric named, experiment not mentioned."],
             [c("impact-gated"), "tool",
              "Neutral implement prompt, but a change that grades badly gets one "
              "quality gated refactor guided by the flagged locations, then is "
              "accepted whatever its grade. Fired on 195 of 1,200 checkpoints."],
             [c("formula-provided"), "disclosure",
              "The structural cost function itself pasted into the implement prompt "
              "as the objective. Its gate fired on 3 of 1,200 checkpoints, so this "
              "condition is the prompt lever, measured."]],
            aligns=["l", "l", "l"]))
    A(f'<p><b>Measurement.</b> Every metric is recomputed from the committed source at '
      f'every checkpoint by {c("lizard")}, PMD, CK {r("aniche")} and {c("jscpd")}, never read '
      f'back from anything the agent wrote. The population is production Java only. '
      f'OfficeFloor\'s YAML wiring is counted in a separate pool and is never folded into '
      f'a Java denominator, because doing so would let a wiring based architecture dilute '
      f'any per line metric.</p>')
    A(f'<p><b>Aggregation.</b> A run is binned into fifths of twelve change requests. '
      f'Unless stated otherwise, every reported value is the final phase, meaning change '
      f'requests 49 to 60, averaged within a run first and then across the ten runs, so '
      f'that a run missing a checkpoint does not get a smaller vote than a complete one. '
      f'Parenthesised figures are one standard deviation across the ten runs.</p>')
    A(f'<p><b>Scale.</b> 4 conditions by 2 architectures by 10 runs by 60 change '
      f'requests is 4,800 agent implementations, at a total implement turn model spend of '
      f'$6,815.</p>')

    # ---- 5
    A(f'<h2 style="{S["h2"]}">5 Results</h2>')
    A(f'<h3 style="{S["h3"]}">5.1 The amount is conserved</h3>')
    A(f'<p>Table 1 gives the four amount operationalisations for all eight cells. They '
      f'rest on different theories and different tools, and they agree. Total Halstead '
      f'volume varies by 7% across all eight cells, total cyclomatic complexity by 15%. '
      f'No condition reached under the floor, in either architecture.</p>')
    rows = []
    for name, *v in AMOUNT:
        rows.append([c(name) + " " + SP, v[0], v[1], v[2], v[3], v[8]])
        rows.append([c(name) + " " + OF, v[4], v[5], v[6], v[7], ""])
    A(table(["metric", "just-solve", "cohesion", "gated", "formula", "spread, all 8"], rows))
    A(f'<p style="{S["cap"]}">Table 1. Amount of complexity in the finished system, '
      f'final phase, mean (SD) over ten runs. Halstead SDs omitted for width and are in '
      f'the paper. Spread is the range over all eight cells divided by their mean.</p>')

    A(f'<p>Finished totals are the quantity a team maintains, but the two applications do '
      f'not start level: the mutative baseline is 413 points of cyclomatic complexity and '
      f'the additive baseline is 361, so a matching total is not automatically a matching '
      f'amount of work. Table 2 therefore repeats the test on the complexity the sixty '
      f'rules <i>added</i>.</p>')
    rows = []
    for name, *v in ADDED:
        rows.append([c(name) + " " + SP, v[0], v[1], v[2], v[3], v[4]])
        rows.append([c(name) + " " + OF, v[5], v[6], v[7], v[8], v[9]])
    A(table(["metric", "just-solve", "cohesion", "gated", "formula", "spread"], rows))
    A(f'<p style="{S["cap"]}">Table 2. Complexity added by the sixty change requests, '
      f'computed per run as the final phase mean minus that run\'s own value at change '
      f'request 1. Spread is within an architecture, across the four conditions.</p>')

    A(f'<p>The conservation claim survives the stricter test and picks up a qualifier. '
      f'The spread widens from 7% on totals to between 20% and 29% on what was added, so '
      f'the honest statement is that the amount is <i>steady</i> rather than fixed. And '
      f'the additive architecture added more complexity than the mutative one in every '
      f'condition. That is the price of a composed pipeline. It is a real cost, and it is '
      f'visible before any argument about placement begins. The additive arm\'s advantage '
      f'is not that it carries less. It is that its baseline was lower and it stayed where '
      f'it was put.</p>')

    A(f'<h3 style="{S["h3"]}">5.2 The placement is not</h3>')
    A(f'<p>Table 3 gives the intervention spread for both architectures and the '
      f'plasticity ratio between them, for twelve placement metrics and, for contrast, '
      f'the amount metrics from Table 1. Figure 1 shows the same result.</p>')
    A(table(["metric", "S(Spring)", "S(OfficeFloor)", "R"], SPREAD))
    A(f'<p style="{S["cap"]}">Table 3. Intervention spread S per architecture, and the '
      f'plasticity ratio R. Final phase. A ratio near 1 means the four conditions moved '
      f'both architectures equally.</p>')
    A(fig("plasticity.png",
          "Figure 1. Every condition's final phase value divided by the same "
          "architecture's own control, so 1.0 means the intervention changed nothing. Top "
          "panel is amount, where neither architecture moves. Bottom panel is placement, "
          "where one does. Normalising to each architecture's own control is deliberate, "
          "because the question is how far each moved rather than where it started. "
          "Absolute levels are in Tables 1 and 4. Click for full size."))
    A(f'<p>The separation is clean. On amount, R lies between 0.6 and 1.1: both '
      f'architectures are equally immovable, which is the conservation result restated. '
      f'On the twelve placement metrics, R lies between 2.9 and 10.0, and in every case '
      f'it is the mutative architecture that moved.</p>')

    A(f'<h3 style="{S["h3"]}">5.3 The mutative arm converges on the additive arm\'s '
      f'starting point</h3>')
    A(f'<p>The interventions worked. Table 4 shows what "worked" converged on.</p>')
    A(table(["metric", "Spring control", "Spring best", "OfficeFloor control"], CONVERGE))
    A(f'<p style="{S["cap"]}">Table 4. Final phase placement. "Best" is whichever of the '
      f'three interventions scored best on that metric for the mutative arm. The '
      f'rightmost column is the additive arm under the plain control, with no '
      f'intervention at all.</p>')
    A(f'<p>Three rounds of coaching bring the mutative architecture to the placement the '
      f'additive architecture occupies with none. The mutative arm can be made to '
      f'distribute its complexity. It has to be asked.</p>')

    A(f'<h3 style="{S["h3"]}">5.4 What the interventions cost</h3>')
    A(f'<p><b>Correctness.</b> The strict pass rate, meaning every test of every rule so '
      f'far is green, fell under every intervention in both architectures. The mutative '
      f'arm went from 0.267 under the control to 0.108 under the cohesion prompt and '
      f'0.033 under the formula; the additive arm went from 0.325 to 0.050 under the '
      f'cohesion prompt. Both architectures are plastic here, R is 1.1, and structural '
      f'stability did not buy safety.</p>')
    A(f'<p>These particular means need more care than the rest of the paper, because the '
      f'underlying distribution is bimodal and the mean falls in a gap where almost no run '
      f'lands. In every one of the eight cells most runs finish at 0 or 0.167 and two or '
      f'three finish near 0.9. The mutative control mean of 0.267 is three runs at 0, five '
      f'at 0.167 and two at 0.917. The ordering between conditions survives, because the '
      f'count of runs stuck at 0 moves the same way the mean does, from 3 of 10 under the '
      f'control to 8 of 10 under the formula. The level does not.</p>')
    A(fig("strict_pass.png",
          "Figure 2. Strict pass rate. The four panels are the trajectory over the sixty "
          "change requests. The row beneath puts the eight final phase means side by side "
          "with one dot per run, which is where the bimodality is visible. Click for full "
          "size."))
    A(f'<p><b>Escape from the call graph.</b> Under the formula condition the mutative '
      f'arm\'s count of container dispatched classes, meaning advice, aspects, filters and '
      f'entity listeners, rose from 3.0 (SD 0) to 11.2 (SD 9.4) per run. That is '
      f'complexity leaving the call graph rather than leaving the codebase, and it is why '
      f'we do not treat any single call graph scoped metric as decisive. The additive '
      f'arm\'s count is exactly 1.0 in all four conditions.</p>')
    A(f'<p><b>Duplication.</b> Verbosity rose in the mutative arm from 0.851 to 1.002 '
      f'under the cohesion prompt and 0.991 under the formula, on a codebase that did not '
      f'grow. Distributing logic across more units creates the opportunity to copy between '
      f'them, and it was taken.</p>')
    A(f'<p><b>Money.</b> Cost per run rose under the cohesion prompt, from $78.40 to '
      f'$96.73 in the mutative arm and $86.51 to $101.18 in the additive arm, and fell '
      f'slightly under the formula.</p>')

    # ---- 6
    A(f'<h2 style="{S["h2"]}">6 Discussion</h2>')
    A(f'<p>A Spring endpoint is a method, and a rule is a statement added to it. Nothing '
      f'in the framework says where that statement goes, so each of the sixty rules is a '
      f'fresh decision. Sixty decisions are sixty opportunities for the surrounding '
      f'instruction to change the answer, which is what Table 3 measures: one '
      f'architecture, four instructions, four materially different shapes.</p>')
    A(f'<p>An OfficeFloor endpoint is a graph of wired functions, and a rule is a new '
      f'function and a new edge. The composition is the restriction. There is no version '
      f'of "add a rule" that concentrates it, so a prompt asking for cohesion is asking '
      f'for something already done. That is why the additive arm\'s placement metrics '
      f'barely register the interventions, and it is a structural explanation rather than '
      f'a claim of superiority: Table 2 shows the additive arm paying more total '
      f'complexity for the same sixty rules.</p>')
    A(f'<p>The practical reading is about durability rather than quality. A structure '
      f'that depends on prompting, review and metrics depends on the discipline of whoever '
      f'is holding them, on every change, indefinitely. With an agent making the change '
      f'sixty times over, the structure is whatever someone remembered to ask for. A '
      f'structure that is a property of the composition holds when nobody is watching. '
      f'Both architectures in this study reached a good placement under the right '
      f'conditions. Only one of them reached it without being told.</p>')

    # ---- 7
    A(f'<h2 style="{S["h2"]}">7 Threats to validity</h2>')
    for head, body in [
        ("The statistic is exploratory and was not preregistered.",
         "S and R were defined after the four runs existed. S is a range over four "
         "points, so it is sensitive to a single outlying condition by construction, and "
         "no interval is attached to it. The metric set in Table 3 was chosen to span the "
         "concentration, change and coupling families rather than by a preregistered "
         "rule, and a different defensible selection would give different ratios. We "
         "mitigate this by reporting every metric in the study publicly, by including the "
         "two placement metrics that show no effect, and by reporting the amount metrics "
         "under the identical statistic as an internal control. The result should be read "
         "as an observation that warrants a preregistered replication, not as a test."),
        ("R is unstable when its denominator is small.",
         "A ratio of two spreads inflates when the additive arm barely moves, which is "
         "precisely the condition the thesis predicts. The ratio is therefore reported "
         "beside both spreads rather than alone. Two metrics scoped to the entry handler "
         "illustrate the failure mode and are excluded from Table 3: "
         + c("wmc_handler") + " has S of 154% and 135%, which reads as a tie, while the "
         "underlying move is 126.5 to 22.6 in one arm and 1.4 to 5.5 in the other."),
        ("Construct validity of \"amount\".",
         "Two metrics published in the amount family do not conserve and are excluded "
         "from Table 1: " + c("pmd_npath_total") + " and " + c("halstead_effort") +
         " compose super linearly within a method and therefore fall when a method is "
         "split, which makes them arrangement sensitive. " + c("total_fns") + " is "
         "retained but is the weakest member, since three of the four conditions were in "
         "effect asking for more functions. " + c("halstead_vocab") + " is summed per "
         "file and so tracks file count rather than amount; it is not used."),
        ("One application, one endpoint, one model.",
         "All results are from a single application, a single endpoint, and " +
         c("claude-opus-4-8") + ". Whether the plasticity gap holds for other frameworks, "
         "other domains or other models is open. The harness supports a model override "
         "for exactly this replication."),
        ("Conditions were not run concurrently.",
         "The four runs were executed between 2026-08-10 and 2026-09-16 against the same "
         "pinned model identifier. A silent provider side model change within that window "
         "would confound the condition effect. The task plan and acceptance suite were "
         "frozen before all four runs, so that source of drift is excluded, but the model "
         "one cannot be excluded from the data alone."),
        ("Two conditions optimise a score we defined.",
         "The gated and formula conditions were built to move the structural impact "
         "score, so that score cannot be evidence for any claim about this experiment. It "
         "is excluded from every table here. Every metric we do use is either a published "
         "definition or a whole codebase count."),
        ("One measurement instrument was silently inert.",
         "The CK cohesion ratios " + c("tcc") + " and " + c("lcc") + " read exactly 0.0 "
         "in all 1,200 records of all four runs, because CK was invoked with its field "
         "level metrics disabled and those ratios require field access data. No result "
         "here depends on them, but they are published in the study's metric gallery and "
         "should be disregarded there until the tool invocation is fixed and the runs "
         "re-analysed. LCOM, a count rather than a ratio, is unaffected."),
        ("Normalisation hides levels.",
         "Figure 1 normalises each architecture to its own control, which is what makes "
         "the two comparable on one axis, but it necessarily conceals the large absolute "
         "gap between them. Tables 1 and 4 carry the levels."),
    ]:
        A(f'<p><b>{head}</b> {body}</p>')

    # ---- 8
    A(f'<h2 style="{S["h2"]}">8 Reproducibility and data availability</h2>')
    A(f'<p>The harness, the frozen change request plan, the acceptance suite and the '
      f'analysis code are public {r("repo")}. Every checkpoint of every run is a commit '
      f'carrying its own raw capture, and every metric in this paper is recomputed from '
      f'those commits by the analysis pass rather than read back from any file the agent '
      f'wrote. The four runs are identified as follows.</p>')
    A(table(["condition", "run"],
            [[c("just-solve"), c("blind-202608100006")],
             [c("cohesion-prompt"), c("blind-202609160027")],
             [c("impact-gated") + " (advisory enforcement)", c("blind-202609031757")],
             [c("formula-provided"), c("blind-202609010045")]],
            aligns=["l", "l"]))
    A(f'<p>Per metric figures for all eight series, across every metric in the study and '
      f'not only those reported here, are produced by the analysis code in that '
      f'repository, each with its definition and formula.</p>')

    # ---- 9
    A(f'<h2 style="{S["h2"]}">9 Conclusion</h2>')
    A(f'<p>Across eight independent attempts at the same sixty change requests, the '
      f'amount of complexity in the finished system varied by 7% on Halstead volume, and '
      f'the amount the change requests added varied by at most 29% within an architecture. '
      f'Against placement metrics that moved by 100% and more under the same '
      f'interventions, that is a quantity refusing to be argued with. Tesler\'s law and '
      f'Brooks\' essential complexity survive the test.</p>')
    A(f'<p>What follows is that architecture is a question of arrangement, and that the '
      f'durable property of an architecture is how little its arrangement depends on '
      f'anything else. On that measure the two architectures here are not comparable. A '
      f'prompt, a tool and a disclosed formula each moved the mutative architecture\'s '
      f'placement by between a third and a factor of two, and the best of them landed it '
      f'where the additive architecture sits untouched. The same three interventions moved '
      f'the additive architecture by 3% to 29%, because there was no slack for them to '
      f'take up.</p>')
    A(f'<p>Neither architecture was safe under coaching: correctness fell in both, and '
      f'the additive arm paid more total complexity for the same rules. The claim is '
      f'narrower than an endorsement. It is that one of these two structures is negotiable '
      f'and the other is not, and that whether a structure is negotiable is itself a '
      f'measurable property worth knowing before an agent writes sixty changes into '
      f'it.</p>')

    # ---- refs
    A(f'<h2 style="{S["h2"]}">References and notes</h2>')
    for i, (_key, _sur, ref) in enumerate(REFS_SORTED, 1):
        A(f'<p style="{S["ref"]}">[{i}] {ref}</p>')

    return "\n\n".join(o) + "\n"


def main() -> int:
    sys.stdout.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

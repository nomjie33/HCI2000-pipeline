"""Builds the analysis notebooks in notebooks/ (kept as code so they diff cleanly and stay in sync with pipeline/).
Re-run after editing this file:  python scripts/build_notebooks.py
Notebooks are saved WITHOUT outputs; run them (Run All) to see tables and figures."""
from pathlib import Path

import nbformat as nbf

OUT = Path("notebooks")

SETUP = '''import sys
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import pandas as pd
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 40)

DATA_DIR = ROOT / "data" / "dummy"      # <- point this at data/raw/<your export folder> for real data
OUT_DIR = ROOT / "outputs"
'''


def nb(cells):
    n = nbf.v4.new_notebook()
    n.cells = [nbf.v4.new_markdown_cell(c) if k == "md" else nbf.v4.new_code_cell(c) for k, c in cells]
    for i, cell in enumerate(n.cells):
        cell["id"] = f"cell{i:03d}"          # deterministic ids so rebuilds don't create noisy diffs
    n.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    return n


FIG_NOTES = {
    "F1_tfind_by_pattern": ("H1: item-finding time", "Compare the boxes (median and spread) and whether the grey participant lines mostly slope the same way. Many crossing lines mean participants differ more than patterns do."),
    "F2_errors_by_pattern": ("H2: errors", "Left: how often trials were error-free. Right: mean errors with 95% CI; overlapping intervals mean the pattern difference is uncertain."),
    "F3_recovery_time": ("H3 / RQ3: recovery time", "Only trials with at least one error contribute. Check the n under each pattern; small n means a wide, unreliable box."),
    "F4_clean_vs_recovery": ("Eq. 2: recovery or slower correct navigation?", "If the hatched (recovery) part differs a lot between patterns but the solid part does not, recovery drives the gap; if the solid part differs, correct navigation itself is slower."),
    "F5_success": ("Task success", "Failures (give-up, time-out) are excluded from the time and error analyses, so check that they are not concentrated in one pattern."),
    "F6_difficulty_ratings": ("Perceived difficulty (SEQ)", "More blue = easier. Secondary outcome, supports rather than tests a hypothesis."),
    "F7_preference_ranking": ("Preference ranking", "Counts of participants giving each rank. Secondary outcome."),
    "F8_order_and_task_pair": ("Order / task-pair check", "Block position and task pair are the same factor in this design (Table 3), so a drop over blocks could be either learning or an easier task pair. Large gaps here are a limitation to report."),
    "F9_errors_by_tree_level": ("Path analysis: where errors happen", "Which level of the tree causes the wrong selections for each pattern."),
    "F10_most_chosen_wrong_items": ("Path analysis: misleading items", "Items that were repeatedly chosen by mistake are candidates for unclear labels; use this in the Discussion."),
}


def notebook_03():
    cells = [
        ("md", "# 03. Descriptives and figures\n\nTables and figures for the Results section, built from the cleaned trial table "
               "(`pipeline.prepare`). **Dummy data by default; nothing here is a finding until `DATA_DIR` points at real data.**\n\n"
               "Basis: T_find, T_clean, E and R use successful trials only (proposal 4.7); success, failure type and SEQ use all analysed trials."),
        ("code", SETUP + '''
from IPython.display import Image, display
from pipeline.prepare import prepare
from pipeline.describe import describe_all
from pipeline.plots import make_all_figures, FIGURES

prep = prepare(DATA_DIR)          # validate -> clean -> derive (stops on hard validation errors)
print(f"{len(prep.trials)} analysed trials, {prep.trials.participant_id.nunique()} participants")'''),
        ("md", "## Tables\nEach is also saved to `outputs/tables/desc_*.csv`."),
        ("code", "tables = describe_all(prep, OUT_DIR)\ntables['sample']"),
        ("md", "### Per-pattern summary\n`T_find_*`, `T_clean_*`, `E_*` and `R_*` are on successful trials; `R_*` additionally needs E >= 1; `SEQ_mean` uses all trials."),
        ("code", "tables['pattern_summary'].set_index('pattern').round(2).T"),
        ("code", "tables['preference']"),
        ("md", "### Path analyses\nFrom the recorded selection path: how far from the minimum path participants wandered, and which wrong items they chose."),
        ("code", "tables['path_efficiency'].round(2)"),
        ("code", "tables['errors_by_level'].round(2)"),
        ("code", "tables['top_wrong_nodes']"),
        ("md", "Full table of which wrong item was picked for which target (`desc_confusion_by_target.csv`):"),
        ("code", "tables['confusion_by_target'].head(15)"),
        ("md", "## Figures\nSaved as PNG and SVG in `outputs/figures/`; the numbers behind each figure are in `outputs/tables/fig_data_*.csv`."),
        ("code", "paths = make_all_figures(prep, OUT_DIR)"),
    ]
    for name, (title, note) in FIG_NOTES.items():
        cells.append(("md", f"### {name.split('_', 1)[0]}: {title}\n{note}"))
        cells.append(("code", f"display(Image(filename=str(paths['{name}'])))"))
    return nb(cells)


def notebook_04():
    cells = [
        ("md", "# 04. Inferential models\n\nTests H1 to H3 (and secondary outcomes) following Table 4 of the proposal. "
               "**Dummy data by default; nothing here is a finding until `DATA_DIR` points at real data.**\n\n"
               "| Outcome | Primary model | Basis |\n| :-- | :-- | :-- |\n"
               "| T_find (H1) | linear mixed model on log time, participant random intercept | successful trials |\n"
               "| E (H2) | Poisson GEE (negative-binomial if overdispersed), clustered on participant | successful trials |\n"
               "| R (H3) | linear mixed model on log time | successful trials with E >= 1 |\n"
               "| success | logistic GEE | all trials |\n"
               "| T_clean, SEQ | linear mixed model | secondary |\n\n"
               "All include a block-position term (block position and task pair are the same factor in this design). "
               "Omnibus pattern effect: Wald test; pairwise contrasts with Holm correction; reference pattern DH.\n\n"
               "**Fallback rule (fixed in advance):** if the primary model is not estimable or did not converge, or its residuals "
               "fail Shapiro or Levene at p < .01, the decision uses the Friedman test (Wilcoxon follow-ups) instead. Both are always computed."),
        ("code", SETUP + '''
from IPython.display import Image, display
from pipeline.prepare import prepare
from pipeline.models import run_models
from pipeline.plots import make_model_figures

prep = prepare(DATA_DIR)
suite = run_models(prep)
suite.write(OUT_DIR)
paths = make_model_figures(suite, OUT_DIR)'''),
        ("md", "## Decision table\nOne row per outcome. `decision_source` says which test the decision uses; `flag_reasons` explains any fallback. "
               "`omnibus_p` is the primary model; `friedman_p` is the fallback."),
        ("code", "cols = ['outcome','hypothesis','primary_model','n_obs','omnibus_p','friedman_p','flagged_for_fallback','decision_source','decision_p','significant']\n"
                 "suite.summary()[cols].round(4)"),
        ("code", "suite.summary()[['outcome','flag_reasons','notes']]"),
        ("md", "## Pairwise contrasts and effect sizes\n`effect` is a ratio of geometric means (times), a rate ratio (E) or an odds ratio (success) for the primary model, "
               "and a median paired ratio/difference for the Friedman fallback. Read `MM vs DH` as MM relative to DH. Only report pairwise results when the omnibus test is significant."),
        ("code", "pw = suite.pairwise()\npw[pw.is_decision_source].drop(columns='is_decision_source').round(3)"),
        ("md", "### All primary and fallback contrasts"),
        ("code", "pw.drop(columns='is_decision_source').round(3)"),
        ("md", "## Sensitivity analyses\nDo the conclusions hold when block 1 is dropped, when familiarity and prior use are added, and "
               "when failures are treated as censored (Cox model)? `agrees_with_primary` compares significance only. Disagreement is a limitation to report."),
        ("code", "suite.sensitivity[['outcome','analysis','n_obs','omnibus_p','significant','agrees_with_primary','note']].round(4)"),
        ("md", "## Preference ranking (secondary)"),
        ("code", "pf = suite.preference\nprint(f'Friedman chi2 = {pf.chi2:.2f}, p = {pf.p:.3f}, Kendall W = {pf.kendall_w:.2f}, n = {pf.n_participants}')\npf.pairwise.round(3)"),
        ("md", "## Figures"),
        ("md", "### F12: pairwise effect sizes\nFilled dot = significant after Holm correction. If an interval crosses 1, that pair is not distinguishable."),
        ("code", "display(Image(filename=str(paths['F12_pairwise_effects'])))"),
        ("md", "### F11: model diagnostics\nQ-Q points should follow the line; residuals should show no funnel or pattern against fitted values. "
               "Strong departures trigger the fallback."),
        ("code", "display(Image(filename=str(paths['F11_model_diagnostics'])))"),
        ("md", "## Reading these results honestly\n"
               "- With N = 15 (30 trials per pattern) power is limited: \"not significant\" means *not detected*, not *no difference*.\n"
               "- GEE effects are population-averaged, not participant-specific (a deviation from Table 4's mixed models).\n"
               "- Block position and task pair are aliased, so a block effect may be learning or task difficulty.\n"
               "- Failures are excluded from the time and error models; check the sensitivity table and the success rates.\n"
               "- R uses only trials with errors, so n is small; check `n_obs` before interpreting it."),
    ]
    return nb(cells)


def main():
    OUT.mkdir(exist_ok=True)
    nbf.write(notebook_03(), OUT / "03_descriptives_and_figures.ipynb")
    nbf.write(notebook_04(), OUT / "04_inferential_models.ipynb")
    print("wrote notebooks 03 and 04 to", OUT)


if __name__ == "__main__":
    main()

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


def notebook_01():
    cells = [
        ("md", "# 01. Load, validate and clean\n\nFirst step for every new export. It reads the CSVs, runs every validation check, "
               "and shows exactly what the cleaning step removes. **Dummy data by default.**\n\n"
               "Checks are *hard* (the analysis refuses to run: the derived numbers would be untrustworthy) or *soft* (reported and handled explicitly). "
               "Try `DATA_DIR = ROOT / 'data' / 'dummy_dirty'` below to see the validator catch 8 injected faults."),
        ("code", SETUP + '''
from pipeline.io import load_dataset
from pipeline.validate import validate
from pipeline.clean import clean

ds = load_dataset(DATA_DIR)
print({"events": len(ds.events), "trials": ds.events.trial_id.nunique(),
       "participants": ds.participants.participant_id.nunique(), "excluded in exclusions.csv": len(ds.exclusions)})
ds.events.head(10)'''),
        ("md", "## Validation report"),
        ("code", "report = validate(ds)\nr = report.to_frame()\nr"),
        ("code", "print('HARD failures:', [x.name for x in report.hard_failures])\nprint('soft failures:', [x.name for x in report.soft_failures])"),
        ("md", "### Offending rows\nEmpty when everything passes. Fix hard failures in the raw export (and note the fix in the cleaning log) before continuing."),
        ("code", "report.details_frame()"),
        ("md", "## Cleaning\nOnly three things are ever removed, each logged: exact duplicate event rows, practice trials, and trials listed in "
               "`exclusions.csv` (device/app faults, decided without looking at the pattern). **No statistical outlier removal.**"),
        ("code", "report.raise_if_hard()        # stops here if the data has hard problems\n"
                 "clean_ds, log = clean(ds)\n"
                 "print(f'{ds.events.trial_id.nunique()} trials before, {clean_ds.events.trial_id.nunique()} after')\nlog"),
        ("code", "log.groupby('step').agg(trials=('trial_id', 'nunique'), event_rows=('n_event_rows', 'sum'))"),
    ]
    return nb(cells)


def notebook_02():
    cells = [
        ("md", "# 02. Derive trial metrics\n\nTurns the event log into one row per trial using the proposal's definitions (3.2-3.3). "
               "**Dummy data by default.**\n\n"
               "- A *selection* is a tap on a menu item; it is an **error** if the item is not on the correct path P*.\n"
               "- An *error episode* starts at an error and ends when the current node is back on P* (an on-path tap, or a Back/collapse landing on-path); "
               "if the trial ends first, it ends at the trial end.\n"
               "- **R** = sum of episode durations (Eq. 1); **T_find** = time of the terminal event; **T_clean = T_find - R** (Eq. 2).\n"
               "- Give-up and time-out trials keep T_find = trial end but `success = 0`."),
        ("code", SETUP + '''
from pipeline.prepare import prepare

prep = prepare(DATA_DIR)
trials, episodes = prep.trials, prep.episodes
trials.head()'''),
        ("md", "## Sanity checks\nEq. 2 must hold exactly, and the logged `on_path` flag should agree with the tree."),
        ("code", "import numpy as np\n"
                 "print('T_find = T_clean + R for every trial:', bool(np.allclose(trials.T_find, trials.T_clean + trials.R)))\n"
                 "print('trials:', len(trials), '| with errors:', int((trials.E > 0).sum()), '| failed:', int((trials.success == 0).sum()))\n"
                 "print('validation: logged on_path mismatches =', 0 if 'on_path_matches_tree' not in prep.report.failed_names else 'see notebook 01')"),
        ("md", "## Look at one trial\nChange `TRIAL_ID`. The table shows each tap and whether it was on the correct path; the episodes below it are what R is built from."),
        ("code", "TRIAL_ID = trials[trials.E > 0].trial_id.iloc[0]\n"
                 "tree = prep.clean.tree\n"
                 "ev = prep.clean.events[prep.clean.events.trial_id == TRIAL_ID][['t_ms', 'event_type', 'node_id', 'current_node_after']].copy()\n"
                 "target = trials.loc[trials.trial_id == TRIAL_ID, 'target_node'].iloc[0]\n"
                 "ev['on_path_now'] = ev.current_node_after.isin(tree.path(target))\n"
                 "print('correct path:', ' > '.join(tree.path(target)))\n"
                 "ev"),
        ("code", "print(trials.loc[trials.trial_id == TRIAL_ID, ['trial_id', 'pattern', 'E', 'R', 'T_find', 'T_clean', 'selection_path']].to_string(index=False))\n"
                 "episodes[episodes.trial_id == TRIAL_ID]"),
        ("md", "## Check against the generator's ground truth (dummy data only)\nThe dummy generator records the true E, R and T_find for each trial; the pipeline must reproduce them exactly."),
        ("code", "gt_path = DATA_DIR / '_ground_truth_trials.csv'\n"
                 "if gt_path.exists():\n"
                 "    gt = pd.read_csv(gt_path)\n"
                 "    m = trials.merge(gt, on='trial_id', suffixes=('', '_true'))\n"
                 "    print('trials compared:', len(m))\n"
                 "    print('E equal:', bool((m.E == m.E_true).all()), '| R equal:', bool(np.allclose(m.R, m.R_true)), '| T_find equal:', bool(np.allclose(m.T_find, m.T_find_true)))\n"
                 "else:\n"
                 "    print('No ground-truth file (expected for real data).')"),
    ]
    return nb(cells)


def notebook_05():
    cells = [
        ("md", "# 05. Conclusions and draft Results text\n\nRuns the whole pipeline in one call and applies the pre-set decision rules "
               "(`pipeline/conclude.py`, plan step 7). **Dummy data by default: none of this may be cited until `DATA_DIR` points at real data.**\n\n"
               "Rules: H1 to H3 are the *null* hypotheses (proposal 4.1). A null is rejected only when the omnibus test of the decision source "
               "(the primary model, or the Friedman fallback when the primary is flagged) has p < .05; otherwise we *fail to reject* (never 'no difference'). "
               "Pairwise contrasts are reported only after a significant omnibus test and only if they survive Holm correction."),
        ("code", SETUP + '''
from IPython.display import Markdown, display
from pipeline.run import run_all
from pipeline.conclude import mechanism

res = run_all(DATA_DIR, OUT_DIR)
print(f"{len(res.prep.trials)} trials, {res.prep.trials.participant_id.nunique()} participants -> {OUT_DIR}")'''),
        ("md", "## Hypothesis decisions"),
        ("code", "res.decisions[['hypothesis','outcome','test','statistic','df','p','decision','significant_contrasts','caution']].round(4)"),
        ("md", "## Where does the time go? (RQ3)\nThe gap in mean T_find between two patterns splits exactly into a recovery part and a clean-navigation part."),
        ("code", "tab, verdict = mechanism(res.prep, res.suite)\nprint(verdict)\ntab.round(2)"),
        ("md", "## Limitations checklist\n`check` items need discussion in the paper; `note` items are standing design caveats."),
        ("code", "res.limitations"),
        ("md", "## Draft Results and Discussion text\nAlso saved to `outputs/results_draft.md`. It is a starting point: verify every number against the tables and write the interpretation yourselves."),
        ("code", "display(Markdown(res.draft_path.read_text(encoding='utf-8')))"),
    ]
    return nb(cells)


def main():
    OUT.mkdir(exist_ok=True)
    books = {"01_load_validate_clean": notebook_01(), "02_derive_trial_metrics": notebook_02(),
             "03_descriptives_and_figures": notebook_03(), "04_inferential_models": notebook_04(),
             "05_conclusions": notebook_05()}
    for name, book in books.items():
        nbf.write(book, OUT / f"{name}.ipynb")
    print("wrote", ", ".join(books), "to", OUT)


if __name__ == "__main__":
    main()

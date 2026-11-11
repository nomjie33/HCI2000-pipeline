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


def main():
    OUT.mkdir(exist_ok=True)
    nbf.write(notebook_03(), OUT / "03_descriptives_and_figures.ipynb")
    print("wrote", OUT / "03_descriptives_and_figures.ipynb")


if __name__ == "__main__":
    main()

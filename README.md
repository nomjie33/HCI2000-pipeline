# HCI2000-pipeline

**Effects of Nested Navigation Patterns on Item-Finding Speed and Error Recovery**
Group 6: Gerylyn Guiller, Qinpei Lu, Naomi Reyes, Lyrshe Weng

This repo holds the data-analysis pipeline for the within-subjects usability test (Phase 3) in the proposal
`MCO1_Research_Proposal_GROUP6 (1).md`. It takes the CSVs exported after each session and produces cleaned
trial data, tables, figures, hypothesis decisions (H1–H3) and draft text for the Results and Discussion sections.

## What the study measures
Three navigation patterns (deep hierarchical **DH**, mega-menu **MM**, nested dropdown **ND**), six timed tasks per
participant, N = 15. Outcomes: item-finding time `T_find`, error count `E`, recovery time `R`
(`T_find = T_clean + R`), plus success, perceived difficulty (SEQ) and preference ranking.

## Pipeline

```
raw CSVs → validate → clean → derive (E, R, T_find, T_clean) → describe → visualize → infer → conclude
```

Full step-by-step plan, data dictionary, validation rules, analysis models, conclusion rules, and the list of gaps
in the proposal: **[docs/ANALYSIS_PLAN.md](docs/ANALYSIS_PLAN.md)**.

## Inputs (one folder per dataset)
| File | Contents |
| :-- | :-- |
| `events.csv` | one row per tap/navigation action (primary data) |
| `ratings.csv` | SEQ difficulty rating per trial |
| `participants.csv` | demographics, familiarity, preference ranking |
| `exclusions.csv` | trials removed for device/app faults |
| `reference/tree.csv`, `reference/tasks.csv` | content tree and task targets |

## Dummy data
`python scripts/make_dummy_data.py` writes clean synthetic data to `data/dummy/` (15 participants, 105 trials incl.
practice, a few give-ups/timeouts, one excluded trial). `--dirty` writes `data/dummy_dirty/` with 8 known faults listed in
`_injected_faults.csv`, used to test the validator. `_ground_truth_trials.csv` holds the generator's true E, R, T_find
for checking the pipeline. The dummy tree uses placeholder labels; replace `reference/tree.csv` once Phase 2 fixes the real tree.

## Planned layout and status
Built in milestones; each is reviewed before it is committed.

| # | Milestone | Status |
| :-- | :-- | :-- |
| M1 | Docs: README and analysis plan | done |
| M2 | Scaffolding and dummy data | done |
| M3 | Load, validate, clean, derive | done |
| M4 | Descriptives and visualization | in review |
| M5 | Inferential models | not started |
| M6 | Conclusions and end-to-end run | not started |
| M7 | (optional) Phase 1 survey analysis | not started |

## Try it now (M3 + M4)
```bash
.venv\Scripts\python -m pytest -q                                       # 23 tests
.venv\Scripts\python -m pipeline.prepare --data-dir data/dummy --out outputs
.venv\Scripts\python scripts/build_notebooks.py                         # (re)builds notebooks/
.venv\Scripts\jupyter lab notebooks/03_descriptives_and_figures.ipynb   # Run All
```
`pipeline.prepare` writes `validation_report.csv`, `cleaning_log.csv`, `trials.csv` and `episodes.csv` to `outputs/tables/`.
Pointing it at `data/dummy_dirty` stops with the list of hard failures. Notebook 03 writes the descriptive tables
(`desc_*.csv`), ten figures (PNG + SVG in `outputs/figures/`) and the data behind each figure (`fig_data_*.csv`).

## Quickstart (after M6)
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python scripts/make_dummy_data.py                         # synthetic data → data/dummy/
python scripts/run_pipeline.py --data-dir data/dummy --out outputs
```
Then open the notebooks in `notebooks/` for the narrated version. For real data, put the exports in `data/raw/`
and point `--data-dir` there.

## Data privacy
Participants are identified by ID only. Real data is git-ignored and kept on the team Google Drive.
Everything in `data/dummy/` is synthetic and must never be cited as a result.

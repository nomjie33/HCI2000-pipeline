# HCI2000-pipeline

**Effects of Nested Navigation Patterns on Item-Finding Speed and Error Recovery**
Group 6: Gerylyn Guiller, Qinpei Lu, Naomi Reyes, Lyrshe Weng

This repo holds the data-analysis pipeline for the within-subjects usability test (Phase 3) in the proposal
`MCO1_Research_Proposal_GROUP6 (1).md`. It takes the CSVs exported after each session and produces cleaned
trial data, tables, figures, hypothesis decisions (H1–H3) and draft text for the Results and Discussion sections.

## One-time setup:
`python -m venv .venv`
`.venv\Scripts\activate`
`pip install -r requirements.txt`
`python -m ipykernel install --user --name hci2000 --display-name "HCI2000 (.venv)"`

## Run the whole analysis (validate, clean, derive, describe, plots, models, conclusions):
`python scripts/run_pipeline.py --data-dir hci2000_export_merged_N18 --out outputs`
This writes all tables, figures F1–F12 and outputs/results_draft.md. It prints the H1–H3 decisions.

## Run the notebooks in VS Code: open one, pick the HCI2000 (.venv) kernel, then Run All. 
To run all five from the terminal and save the results with outputs:
`jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb`

## Prototype (Phase 2/3 test app)
`prototype/` is the offline web app used in the sessions. It covers:
- researcher setup with the 3×3 Latin square;
- a fixed practice task;
- timed tasks with automatic event logging;
- SEQ ratings;
- a ZIP export that is already a pipeline dataset folder.

It is installed on the study phone from GitHub Pages. The guide is **[docs/PROTOTYPE_GUIDE.md](docs/PROTOTYPE_GUIDE.md)**,
and the guide for adding the DH/ND patterns is **[prototype/PATTERN_API.md](prototype/PATTERN_API.md)**.
To try it on a computer: `python -m http.server 8000 -d prototype`, then open <http://localhost:8000>.

## What the study measures
Three navigation patterns (deep hierarchical **DH**, mega-menu **MM**, nested dropdown **ND**), six timed tasks per
participant, N = 18 (6 per Latin-square sequence). Outcomes: item-finding time `T_find`, error count `E`, recovery time `R`
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

## Quickstart
```bash
python -m venv .venv
.venv\Scripts\activate                                    # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m ipykernel install --user --name hci2000 --display-name "HCI2000 (.venv)"   # once: makes the venv a Jupyter kernel
python scripts/build_real_dataset.py --exports <export folder 1> <export folder 2> ... --form "<Google Form responses>.csv" --out hci2000_export_merged_N18
python scripts/run_pipeline.py --data-dir hci2000_export_merged_N18 --out outputs
```
The current dataset is `hci2000_export_merged_N18/`: 18 participants (6 each in S1, S2, S3) merged from five phone exports
(`id_mapping.csv` lists the original export and ID of each participant).
`build_real_dataset.py` merges exports from several phones (participant IDs that repeat across exports are renumbered, mapping in
`id_mapping.csv`) and fills `participants.csv` from the Google Form by matching each response to the session that finished just before it
(`form_match.csv`). A session with no form response keeps blank demographics and ranks, and the builder prints a warning
(currently P16, P17 and P18: add their form responses and rebuild to fill them in). The pipeline then validates, cleans, derives, describes, plots, fits the models and writes the conclusions. It prints the H1 to H3
decisions and exits with code 1 (analysing nothing) if the data has hard problems. Run the tests with `pytest -q` (hand-built unit tests only).

Note: the form did not collect `gov_familiarity` or `used_reference_site`, so those stay blank and the covariate sensitivity model is reported as skipped.

## Notebooks (`notebooks/`, saved without outputs: open and Run All)
They use the **HCI2000 (.venv)** kernel registered above. In VS Code, open a notebook, choose *Select Kernel* and pick that kernel or `.venv`
(`.vscode/settings.json` already points VS Code at `.venv`). From a terminal: activate the venv, then `jupyter lab notebooks`.

| Notebook | What it shows |
| :-- | :-- |
| `01_load_validate_clean` | validation report with offending rows; what cleaning removes |
| `02_derive_trial_metrics` | how E, R, T_find, T_clean come from the log; one trial traced tap by tap |
| `03_descriptives_and_figures` | descriptive tables, path analyses, figures F1 to F10 |
| `04_inferential_models` | models, pairwise contrasts, fallback, sensitivity analyses, figures F11 to F12 |
| `05_conclusions` | hypothesis decisions, mechanism, limitations, draft Results text |

They are generated by `python scripts/build_notebooks.py`; edit that script, not the `.ipynb` files.

## What the pipeline writes (`outputs/`, git-ignored)
| Path | Contents |
| :-- | :-- |
| `tables/validation_report.csv`, `validation_details.csv`, `cleaning_log.csv` | data checks and every removed row |
| `tables/trials.csv`, `episodes.csv` | one row per trial (App. B fields + path descriptors); error episodes behind R |
| `tables/desc_*.csv`, `fig_data_*.csv` | descriptive tables; the numbers behind each figure |
| `tables/model_summary.csv`, `model_pairwise.csv`, `model_sensitivity.csv`, `model_preference.csv` | inferential results |
| `tables/hypothesis_decisions.csv`, `limitations_checklist.csv`, `mechanism_decomposition.csv` | conclusions |
| `figures/F1 ... F12` (PNG + SVG) | figures for the paper |
| `results_draft.md` | auto-generated Results/Discussion starting text |

## Status
Built in milestones; each was reviewed before it was committed.

| # | Milestone | Status |
| :-- | :-- | :-- |
| M1 | Docs: README and analysis plan | done |
| M2 | Scaffolding | done |
| M3 | Load, validate, clean, derive | done |
| M4 | Descriptives and visualization | done |
| M5 | Inferential models | done |
| M6 | Conclusions and end-to-end run | in review |
| M7 | (optional) Phase 1 survey analysis | not started |
| P1 | Prototype shell: setup, Latin square, practice, logging, SEQ, export, PWA | done |
| P2 | Prototype: mega-menu (MM) | done |
| P3 | Prototype: deep hierarchical (DH) | done |
| P4 | Prototype: nested dropdown (ND) | done |

Open decisions for the group (details in the plan, section 3): 6 participants per sequence (N = 18), block position and task pair
being the same factor, GEE instead of GLMM, and the censoring of failed trials.

## Data privacy
Participants are identified by ID only. Real data is git-ignored and kept on the team Google Drive.

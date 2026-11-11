# Data and Analysis Plan

Companion to `MCO1_Research_Proposal_GROUP6 (1).md`. The proposal defines *what* we measure (§3, §4.6, App. B)
and the statistical tests (§4.7, Table 4). This document fills in the parts it leaves open: the raw data
layout, cleaning rules, derivation, visualization, and how results become conclusions.
Section references (§) point to the proposal.

## 0. Pipeline at a glance

```
raw CSVs ──► 1 Validate ──► 2 Clean ──► 3 Derive ──► 4 Describe ──► 5 Visualize ──► 6 Infer ──► 7 Conclude
(events,      (checks,       (drop        (episodes,    (tables)       (figures)       (models,     (H1–H3
 ratings,      report)        practice,    E, R, T_find,                               contrasts,   decisions,
 participants)                 exclusions)  T_clean)                                    fallbacks)   draft text)
```

## 1. What we collect (per proposal §4.4–4.6, App. B)

| Source | Collected by | Raw file |
| :-- | :-- | :-- |
| Automated tap/event log (primary data) | Prototype logger, exported after each session | `events.csv` |
| Post-task Single Ease Question, 1–7 | On-device, after every task | `ratings.csv` |
| Demographics, familiarity, prior use, final preference ranking, comments | Questionnaires | `participants.csv` |
| Device/app faults found when checking screen recordings | Researcher | `exclusions.csv` |
| Content tree and task targets | Phase 2 prototype build | `reference/tree.csv`, `reference/tasks.csv` |

Screen recordings are only a backup used to spot-check the log and to justify exclusions; they are not analysed.

### 1.1 Data dictionary

**`events.csv`**: one row per tap or navigation action.

| Column | Description |
| :-- | :-- |
| participant_id | e.g. `P01` |
| trial_id | unique per trial, e.g. `P01_T3` (practice trials: `P01_PR1`) |
| sequence | S1, S2, S3 (Table 3) |
| block_position | 1–3 (0 for practice) |
| trial_order | 1–6 order of the trial within the session (0 for practice); needed because the two tasks in a block alternate between participants |
| pattern | DH, MM, ND |
| task_id, task_pair | T1–T6 / `PR*`; pair A–C |
| target_node | leaf node the participant must reach |
| min_selections | 2 (MM) or 3 (DH, ND) |
| t_ms | ms since the Start tap |
| event_type | `start`, `select`, `back`, `collapse`, `menu_open`, `menu_close`, `logo`, `give_up`, `target_reached`, `timeout` |
| node_id | node tapped (blank for non-node actions) |
| current_node_after | node whose children/page are displayed after the action (§3.2 "current node") |
| on_path | logged flag: 1 if `current_node_after` is on P\* (App. B) |

A `select` is a tap on a menu node (§3.2). `menu_open`/`menu_close`, `back`, `collapse` and `logo` are navigation
actions: logged, not selections. Every trial has one `start` and exactly one terminal event
(`target_reached`, `give_up` or `timeout`).

**`ratings.csv`**: `participant_id, trial_id, difficulty_rating` (1 very difficult … 7 very easy).

**`participants.csv`**: `participant_id, sequence, age, gender, gov_familiarity (1–5), used_reference_site (Y/N), rank_DH, rank_MM, rank_ND (1 = most preferred), comments`.

**`exclusions.csv`**: `trial_id, reason`. Device or app fault only, decided before looking at the trial's pattern (§4.7).

**`reference/tree.csv`**: `node_id, parent_id, level (1–3), label`. **`reference/tasks.csv`**: `task_id, task_pair, target_node`.
The tree lets the pipeline recompute `on_path` independently instead of trusting the logged flag.

Each dataset lives in one folder (`data/dummy/`, `data/raw/`, …) holding the four CSVs above plus a `reference/` subfolder
with `tree.csv` and `tasks.csv`. The practice tree (`PR*` nodes, a public-library topic) is included in `tree.csv`.
A `target_reached` row is logged at the same `t_ms` as the `select` of the target.

### 1.2 Derived trial table (App. B fields)

`participant_id, trial_id, sequence, block_position, pattern, task_id, task_pair, target_node, min_selections,
t_end_s, end_reason, success, E, R, T_find, T_clean, difficulty_rating`, plus `trial_order`, covariates
(`age, gender, gov_familiarity, used_reference_site`) and path descriptors: `n_selections`, `n_back_actions`
(Back/collapse/logo) and `selection_path` (the ordered nodes the participant selected).
An `episodes` table (one row per error episode: `trial_id, episode, start_s, end_s, duration_s, open_at_end`) is kept for auditing R.

## 2. Step-by-step plan

### Step 1. Load and validate
Read the CSVs with explicit dtypes. Checks (each reported as pass/fail with the offending rows; the pipeline
stops on hard failures, warns on soft ones):

| Check | Severity |
| :-- | :-- |
| Required columns present, no unexpected `pattern`/`event_type` values | hard |
| Each trial has exactly one `start` (t_ms = 0) and exactly one terminal event | hard |
| `t_ms` non-decreasing within a trial; terminal event ≤ 180 000 ms (timeout = 180 000) | hard |
| Every `node_id` / `current_node_after` / `target_node` exists in `tree.csv` | hard |
| Trial targets match `tasks.csv`; `min_selections` consistent with pattern | hard |
| 6 experimental trials per participant; 5 participants per sequence (N = 15) | soft (expected counts shown) |
| Pattern/pair per sequence and block match the Latin square in Table 3 | soft |
| Logged `on_path` equals tree-derived on-path flag | soft (mismatch table; the tree-derived value is used) |
| No duplicate `(trial_id, t_ms, event_type, node_id)` rows | soft |
| Every experimental trial has a rating; every participant has a complete preference ranking (permutation of 1–3) | soft |

### Step 2. Clean
1. Drop exact duplicate event rows (same trial, time, event, node), a logging artefact that would otherwise double-count errors.
2. Drop practice trials (`PR*`).
3. Drop trials listed in `exclusions.csv`. Nothing is removed by a statistical rule (§4.7: no outlier removal).
4. Write every drop and its reason to `outputs/tables/cleaning_log.csv`.
5. Never drop or edit rows silently; any manual fix to the raw CSV must be noted in the cleaning log.

### Step 3. Derive (§3.2–3.3)
For each trial, with P\* = root→target path from the tree:
1. Recompute on-path for each action from `current_node_after`.
2. A `select` of a node not on P\* is an **error**; E = number of errors.
3. An **error episode** starts at the time of the incorrect selection, ends when the current node is next on P\*
   (by an on-path selection, or a `back`/`collapse` landing on-path). If the trial ends first, the episode ends at the trial end time.
4. R = Σ(e_j − s_j) (Eq. 1), in seconds.
5. T_find = time of `target_reached` (seconds); for `give_up`/`timeout` trials, T_find is set to the trial end time but
   `success = 0` (these trials are excluded from T_find/E/R inference, §4.7, and kept for descriptive and success analyses).
6. T_clean = T_find − R (Eq. 2). Join SEQ ratings and participant-level covariates.

Selecting a wrong L3 leaf opens the placeholder page, which is an error and also puts the current node off-path; the
episode ends when the participant backs out onto P\*.

### Step 4. Describe
Output tables (CSV + printed in the notebook):
- Sample: N, per-sequence counts, age/gender, familiarity, prior use.
- Per pattern: N trials, success rate and failures (give-up vs timeout), median/IQR and geometric mean of T_find, T_clean, R (E≥1 only), mean and SD of E, share of trials with E ≥ 1, mean SEQ.
- Preference ranking: mean rank and counts of rank 1 per pattern.
- Minimum selections per pattern (reported alongside results, §4.3).

### Step 5. Visualize
Each plot uses the same colour per pattern throughout, has labelled axes with units, and shows individual data where N is small.

| # | Figure | Answers |
| :-- | :-- | :-- |
| F1 | T_find by pattern: box plot over participant points, per-participant means joined by lines, log y-axis | H1 |
| F2 | E by pattern: share of trials by E (0, 1, 2, 3+), plus mean E with 95% CI | H2 |
| F3 | R by pattern (trials with E ≥ 1): strip + box, log axis | H3 / RQ3 |
| F4 | Stacked bar: mean T_clean + R per pattern | Does recovery or slower correct navigation drive differences (Eq. 2)? |
| F5 | Success rate and failure type per pattern | success outcome |
| F6 | SEQ distribution per pattern (diverging stacked bars) | secondary |
| F7 | Preference ranking: stacked bars of rank 1/2/3 | secondary |
| F8 | T_find by block position and by task pair | order and task-difficulty check |
| F9 | Model diagnostics: residual QQ plot and residuals vs fitted for log T_find / log R | assumptions |

Figures are saved as PNG and SVG in `outputs/figures/`.

### Step 6. Infer (Table 4, α = .05 two-sided)

| Outcome | Model (this pipeline) | Notes |
| :-- | :-- | :-- |
| log T_find (H1), successful trials | Linear mixed model: `log T_find ~ pattern + block_position + task_pair`, random intercept for participant | `statsmodels.MixedLM` |
| E (H2), successful trials | Poisson GEE, exchangeable correlation, clustered on participant; switch to negative binomial GEE if Pearson dispersion > 1.5 | deviation, see §3 |
| log R (H3), trials with E ≥ 1 | Same LMM as T_find | participants without errors under a pattern contribute nothing |
| Success (all trials) | Logistic GEE, same terms | |
| log T_clean, SEQ (secondary) | LMM; SEQ also Friedman test across patterns | |

Omnibus pattern effect by Wald test. If significant, the three pairwise contrasts (DH–MM, DH–ND, MM–ND) are tested with Holm
correction. Effect sizes with 95% CI: ratio of geometric means (times), rate ratio (counts), odds ratio (success).

**Fallback** (when the LMM fails to converge, or residuals clearly violate normality/variance assumptions on log scale):
Friedman test on each participant's per-pattern values, with Wilcoxon signed-rank follow-ups (Holm). Per-participant values for R
require a participant to have E ≥ 1 under every pattern; otherwise Friedman is not run for R and this is stated.

**Sensitivity analyses** (reported, not used for the primary decision):
1. All trials, with failures treated as right-censored at 180 s (Cox model on time-to-target, participant-clustered).
2. Excluding block position 1 (practice/warm-up effect).
3. Adding `gov_familiarity` and `used_reference_site` as covariates.

### Step 7. Draw conclusions
Rules are fixed in advance so conclusions do not depend on how the results look:

1. **Per hypothesis (H1–H3):** reject H0 if the omnibus pattern test has p < .05 *and* the primary model is not flagged by the fallback rule.
   Otherwise "fail to reject" (never "no difference"; with N = 15 we may lack power).
2. **Direction and size:** name the pairwise contrasts that survive Holm correction, with effect size and 95% CI. If only the omnibus is significant, say so.
3. **Mechanism (RQ3):** compare F4 and the T_clean model: if R differences account for most of the T_find gap, attribute it to recovery;
   if T_clean also differs, attribute it to slower correct navigation.
4. **Robustness:** state whether the sensitivity analyses agree with the primary decision. Disagreement is reported as a limitation.
5. **Secondary outcomes:** success, SEQ, preference reported as supporting, not confirmatory.
6. **Limitations auto-checklist:** N, number of failed trials per pattern (censoring), single reference site, mega-menu needing 2 vs 3 selections
   (a feature of the pattern, §4.3), one device model, convenience sample of friends and family.

The conclusion step produces `outputs/tables/hypothesis_decisions.csv` and `outputs/results_draft.md`
(templated sentences plus tables and figure references) as starting text for the Results and Discussion sections. The group edits and owns the interpretation.

## 3. Gaps and deviations from the proposal (decisions needed)

1. **N per sequence.** §4.4 says N = 15 with "ten (10) per sequence"; 15 ÷ 3 = 5. Fix in the paper (the pipeline expects 5 per sequence).
2. **min_selections covariate.** §4.6 lists it as a covariate, but it is perfectly collinear with pattern (MM = 2, others = 3), so it can't be estimated alongside the pattern effect. The pipeline reports it descriptively only.
3. **GEE instead of GLMM.** Table 4 specifies mixed models for E and success. Python's `statsmodels` has no negative-binomial or logistic GLMM, so the pipeline uses participant-clustered GEE.
   GEE estimates population-averaged rather than participant-specific effects; this should be stated in the paper. (R `lme4`/`glmmTMB` would match Table 4 exactly if the group prefers.)
4. **Censoring.** Analysing only successful trials can bias times downward for the harder patterns. The proposal reports failure counts; we add the censored sensitivity analysis above.
5. **Rule from analysis to conclusion** was missing; Step 7 supplies it.
6. **Phase 1 survey (RQ1/RQ2)** analysis is only described as frequencies. A pattern-frequency and inter-coder-agreement (Cohen's κ) notebook is an optional add-on.
7. **Power analysis** depends on the pilot; the pipeline's variance estimates can be reused once pilot data exists (not built yet).

## 4. Reproducibility
- All thresholds (180 s limit, α = .05, dispersion cutoff) live in `pipeline/config.py`.
- Random seeds are fixed in the dummy-data generator only; the analysis itself is deterministic.
- Dummy data lives in `data/dummy/` and is synthetic. Real exports go in `data/raw/` (git-ignored: participant data stays on Google Drive).

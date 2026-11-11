"""Step 7: turn model output into hypothesis decisions and draft Results/Discussion text.

Rules (fixed in advance, docs/ANALYSIS_PLAN.md step 7):
 1. H0 is rejected when the omnibus test of the DECISION SOURCE has p < .05. The decision source is the primary
    model unless the fallback rule switched it to the Friedman test (models.py). Otherwise we "fail to reject":
    never "no difference", because N = 15 may lack power.
 2. Pairwise contrasts are reported only when the omnibus test is significant, and only those that survive Holm correction.
 3. Mechanism (RQ3): the difference in mean T_find between two patterns is split exactly into a recovery part (R) and a
    clean-navigation part (T_clean), because T_find = T_clean + R. The gap is "mainly recovery" if the T_clean model is not
    significant and recovery is at least half of the absolute gap; "mainly clean navigation" if T_clean is significant and
    recovery is under half; otherwise "both".
 4. Robustness: the number of sensitivity analyses that agree with the primary significance is stated.
 5. Secondary outcomes (success, SEQ, preference) are reported as supporting, not confirmatory.
 6. A limitations checklist is generated from the data (failures, fallbacks, sample size, small R, ...) plus fixed design caveats.
The text is a starting draft: the group owns the interpretation.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ALPHA, CONTRASTS, N_PARTICIPANTS, PATTERNS
from .describe import NAMES, pattern_summary, preference_summary, successful
from .models import ModelSuite

HYP = {
    "T_find": ("H1", "item-finding time", "There is no significant difference in item-finding time across the three navigation patterns."),
    "E": ("H2", "error count", "There is no significant difference in error count across the three navigation patterns."),
    "R": ("H3", "recovery time", "There is no significant difference in recovery time across the three navigation patterns."),
}
MECHANISM_SHARE = 0.5


# --- formatting helpers --------------------------------------------------------------------------
def fmt_p(p: float) -> str:
    if p is None or np.isnan(p):
        return "p = n/a"
    return "p < .001" if p < 0.001 else "p = " + f"{p:.3f}".lstrip("0")


def _pct(r: float, up: str, down: str) -> str:
    return f"{abs(r - 1) * 100:.0f}% {up if r >= 1 else down}"


def _times(r: float, noun_up: str, adj_up: str, adj_down: str) -> str:
    """'2.6 times as many' for large ratios, else '27% more/longer', '23% fewer/shorter'."""
    if r >= 2:
        return f"{r:.1f} times as {noun_up}"
    return _pct(r, adj_up, adj_down)


def _source_label(a) -> str:
    return "Friedman test" if a.chosen == "fallback" else a.primary.model


def _test_stat(a) -> tuple[str, float, int]:
    if a.chosen == "fallback":
        return "Friedman", a.fallback.chi2, 2
    return "Wald", a.primary.omnibus_stat, a.primary.omnibus_df


def omnibus_phrase(a) -> str:
    name, stat, df = _test_stat(a)
    p = fmt_p(a.p_chosen)
    if name == "Friedman":
        return f"Friedman χ²(2) = {stat:.2f}, {p}, Kendall's W = {a.fallback.kendall_w:.2f}, n = {a.fallback.n_participants} participants"
    return f"Wald χ²({df}) = {stat:.2f}, {p}"


def contrast_sentence(key: str, row, a) -> str:
    """One sentence for one pairwise contrast that survived Holm correction."""
    ca, cb = row.contrast.split(" vs ")
    A, B = NAMES[ca], NAMES[cb]
    fb = a.chosen == "fallback"
    holm = f"Holm-adjusted {fmt_p(row.p_holm)}"
    ci = "" if fb or np.isnan(row.ci_low) else f", 95% CI [{row.ci_low:.2f}, {row.ci_high:.2f}]"
    kind = a.spec.kind
    if kind == "lmm_log":
        noun = {"T_find": "item-finding time", "R": "recovery time", "T_clean": "clean navigation time"}[key]
        what = "median paired ratio" if fb else "ratio of geometric means"
        amount = f"{row.effect:.1f} times as long" if row.effect >= 2 else _pct(row.effect, "longer", "shorter")
        return f"{A} {noun} was {amount} than {B}".replace("long than", "long as") + f" ({what} {row.effect:.2f}{ci}; {holm})"
    if kind == "count" and not fb:
        amount = f"{row.effect:.1f} times as many errors as" if row.effect >= 2 else \
            f"{_pct(row.effect, 'more', 'fewer')} errors than"
        return f"{A} trials had {amount} {B} (rate ratio {row.effect:.2f}{ci}; {holm})"
    if kind == "count":
        return f"{A} differed from {B} by a median of {row.effect:+.2f} errors per participant ({holm})"
    d = row.effect
    unit = "mean difference" if not fb else "median paired difference"
    side = "easier" if d > 0 else "harder"
    return f"{A} was rated {abs(d):.2f} points {side} than {B} ({unit} {d:+.2f}{ci}; {holm})"


def significant_contrasts(a) -> pd.DataFrame:
    pw = a.pairwise_chosen
    return pw[pw.significant_holm] if (len(pw) and a.significant) else pw.iloc[0:0]


# --- decisions -----------------------------------------------------------------------------------
def hypothesis_decisions(suite: ModelSuite) -> pd.DataFrame:
    rows = []
    for key, (h, label, null) in HYP.items():
        a = suite.analyses[key]
        name, stat, df = _test_stat(a)
        sig = a.significant
        sc = significant_contrasts(a)
        caution = " | ".join(a.reasons) if (a.flagged and a.chosen == "primary") else ""
        rows.append(dict(
            hypothesis=h, outcome=key, null_hypothesis=null, decision_source=a.chosen, test=_source_label(a),
            statistic=stat, df=df, p=a.p_chosen, reject_null=sig,
            decision=f"Reject {h}" if sig else f"Fail to reject {h}",     # H1-H3 are the null hypotheses (proposal 4.1)
            significant_contrasts="; ".join(sc.contrast) if len(sc) else "",
            n_obs=a.primary.n_obs, caution=caution))
    return pd.DataFrame(rows)


def mechanism(prep, suite: ModelSuite) -> tuple[pd.DataFrame, str]:
    """Exact decomposition of mean T_find gaps into recovery and clean-navigation parts (Eq. 2)."""
    s = successful(prep.trials)
    m = s.groupby("pattern")[["T_find", "T_clean", "R"]].mean().reindex(list(PATTERNS))
    rows = []
    for a, b in CONTRASTS:
        dT, dC, dR = (m.loc[a, c] - m.loc[b, c] for c in ("T_find", "T_clean", "R"))
        rows.append(dict(contrast=f"{a} vs {b}", delta_T_find=dT, delta_T_clean=dC, delta_R=dR,
                         share_recovery=abs(dR) / (abs(dR) + abs(dC)) if (abs(dR) + abs(dC)) > 0 else np.nan))
    tab = pd.DataFrame(rows)
    h1 = suite.analyses["T_find"]
    if not h1.significant:
        return tab, "No pattern difference in item-finding time was detected, so there is no gap to attribute."
    sig = significant_contrasts(h1).contrast.tolist() or tab.contrast.tolist()
    t = tab[tab.contrast.isin(sig)]
    share = float(t.delta_R.abs().sum() / (t.delta_R.abs().sum() + t.delta_T_clean.abs().sum()))
    clean_sig = suite.analyses["T_clean"].significant
    if clean_sig and share < MECHANISM_SHARE:
        v = "mainly clean navigation (the time spent scanning and making correct selections), not recovery"
    elif not clean_sig and share >= MECHANISM_SHARE:
        v = "mainly recovery from wrong-path selections"
    else:
        v = "both recovery and clean navigation"
    return tab, (f"For the contrasts that differ ({', '.join(sig)}), recovery accounts for {share:.0%} of the absolute gap in mean "
                 f"time; clean navigation time itself {'also differs' if clean_sig else 'does not differ'} across patterns "
                 f"({omnibus_phrase(suite.analyses['T_clean'])}). The differences are therefore {v}.")


# --- limitations ---------------------------------------------------------------------------------
def limitations(prep, suite: ModelSuite) -> pd.DataFrame:
    t = prep.trials
    rows = []

    def add(item, status, detail):
        rows.append(dict(item=item, status=status, detail=detail))

    n = t.participant_id.nunique()
    add("Sample size", "flag" if n < N_PARTICIPANTS else "note",
        f"{n} participants analysed (planned {N_PARTICIPANTS}); the size is provisional pending the pilot power analysis. "
        "A non-significant result means 'not detected', not 'no difference'.")
    fails = t[t.success == 0].groupby("pattern").size().reindex(list(PATTERNS), fill_value=0)
    add("Failed trials", "flag" if fails.sum() else "note",
        "Give-up/time-out trials by pattern: " + ", ".join(f"{p} {int(fails[p])}" for p in PATTERNS) +
        ". They are excluded from the time and error models (proposal 4.7), which can understate the slowest patterns; see the censored sensitivity analysis.")
    fb = [k for k, a in suite.analyses.items() if a.chosen == "fallback"]
    if fb:
        add("Fallback tests used", "flag", "Decision uses the Friedman test for: " + ", ".join(fb) +
            " (reasons in model_summary.csv). Friedman has less power and gives no covariate adjustment.")
    flagged_kept = [k for k, a in suite.analyses.items() if a.flagged and a.chosen == "primary"]
    if flagged_kept:
        add("Model assumptions", "flag", "Assumption flags with no usable fallback for: " + ", ".join(flagged_kept) + ".")
    r = t[(t.success == 1) & (t.E >= 1)]
    rc = r.groupby("pattern").size().reindex(list(PATTERNS), fill_value=0)
    add("Recovery-time sample", "flag" if (rc < 8).any() else "note",
        "Trials with at least one error: " + ", ".join(f"{p} {int(rc[p])}" for p in PATTERNS) +
        ". Recovery time (H3) rests only on these trials, so its estimates are less stable.")
    sens = suite.sensitivity
    if len(sens) and "agrees_with_primary" in sens:
        dis = sens[sens.agrees_with_primary == False]                    # noqa: E712
        add("Sensitivity analyses", "flag" if len(dis) else "note",
            f"{int(sens.agrees_with_primary.fillna(False).sum())} of {int(sens.agrees_with_primary.notna().sum())} "
            "analyses (including the primary) agree with the primary significance." +
            (" Disagreeing: " + "; ".join(f"{r.outcome} ({r.analysis})" for r in dis.itertuples()) + "." if len(dis) else ""))
    add("Multiple hypotheses", "note", "H1 to H3 are each tested at α = .05 with no correction across the three hypotheses (Holm is applied only to pairwise contrasts within each).")
    add("Population-averaged effects", "note", "Error and success effects come from GEE and are population-averaged rather than participant-specific (Table 4 proposed mixed models).")
    add("Block position and task pair", "flag", "These are the same factor in the Latin square (Table 3), so a block effect cannot be separated from task-pair difficulty.")
    add("Minimum selections", "note", "The mega-menu needs 2 selections and the other patterns 3; this is part of what the pattern is (proposal 4.3), not removed.")
    add("Generalisability", "note", "One reference website, one device model, and a convenience sample (friends and family recruited via Facebook/Messenger).")
    return pd.DataFrame(rows)


# --- draft text ----------------------------------------------------------------------------------
def md_table(df: pd.DataFrame, floatfmt: str = ".2f") -> str:
    cols = list(df.columns)
    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "" if np.isnan(v) else format(v, floatfmt)
        return str(v)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def _iqr(med, q1, q3, n=None) -> str:
    return f"{med:.1f} s (IQR {q1:.1f}–{q3:.1f}" + (f"; n = {n} trials)" if n is not None else ")")


def _pat_list(parts: dict) -> str:
    items = [f"{NAMES[p]} {parts[p]}" for p in PATTERNS]
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _hyp_paragraph(key: str, prep, suite, ps: pd.DataFrame) -> str:
    h, label, _ = HYP[key]
    a = suite.analyses[key]
    ps = ps.set_index("pattern")
    if key == "T_find":
        desc = "Median item-finding time was " + _pat_list({p: _iqr(ps.loc[p, "T_find_median"], ps.loc[p, "T_find_q1"], ps.loc[p, "T_find_q3"]) for p in PATTERNS}) + " (successful trials)."
    elif key == "E":
        desc = ("Mean errors per trial were " + _pat_list({p: f"{ps.loc[p, 'E_mean']:.2f} (SD {ps.loc[p, 'E_sd']:.2f})" for p in PATTERNS}) +
                "; the share of trials with at least one error was " + _pat_list({p: f"{ps.loc[p, 'share_E_ge1']:.0%}" for p in PATTERNS}) + ".")
    else:
        desc = ("Among trials with at least one error, median recovery time was " +
                _pat_list({p: _iqr(ps.loc[p, "R_median"], ps.loc[p, "R_q1"], ps.loc[p, "R_q3"], int(ps.loc[p, "n_trials_E_ge1"])) for p in PATTERNS}) + ".")
    how = f"We tested this with a {_source_label(a)}"
    if a.chosen == "fallback":
        how += " (the primary model was flagged: " + "; ".join(a.reasons) + ")"
    out = [f"### {h}: {label}", "", desc, ""]
    if a.significant:
        out.append(f"{label.capitalize()} differed across navigation patterns ({omnibus_phrase(a)}). {how}.")
        sc = significant_contrasts(a)
        if len(sc):
            out += ["", "After Holm correction: " + "; ".join(contrast_sentence(key, r, a) for r in sc.itertuples()) + "."]
        else:
            out += ["", "No individual pairwise contrast survived Holm correction."]
        out += ["", f"We therefore reject the null hypothesis {h} in favour of {h}a."]
    else:
        out.append(f"We did not detect a difference in {label} across navigation patterns ({omnibus_phrase(a)}). {how}.")
        out += ["", f"We fail to reject the null hypothesis {h}. This does not show the patterns are equivalent: with {a.primary.n_participants} participants the study may lack power for small differences."]
    if a.flagged and a.chosen == "primary":
        out += ["", "*Caution: " + "; ".join(a.reasons) + ".*"]
    return "\n".join(out)


def results_draft(prep, suite: ModelSuite, synthetic: bool | None = None) -> str:
    t, ds = prep.trials, prep.clean
    if synthetic is None:
        synthetic = any("dummy" in part.lower() for part in prep.raw.data_dir.parts)
    ps = pattern_summary(t)
    psi = ps.set_index("pattern")
    pf = preference_summary(ds.participants).set_index("pattern")
    dec = hypothesis_decisions(suite)
    _, mech = mechanism(prep, suite)
    p = ds.participants
    L = ["# Results and Discussion: auto-generated draft", ""]
    if synthetic:
        L += ["> **SYNTHETIC DATA.** This draft was generated from dummy data to test the pipeline. None of it is a finding and none of it may be cited.", ""]
    L += ["> Starting text only: check every number against the tables, and write the interpretation yourselves. "
          "Generated by `pipeline/conclude.py`.", "",
          "## Participants and trials", "",
          f"{len(p)} participants (age {p.age.mean():.1f} ± {p.age.std():.1f} years, range {int(p.age.min())}–{int(p.age.max())}) completed "
          f"{len(t)} analysed experimental trials ({int(t.success.sum())} successful). {int((p.used_reference_site == 'Y').sum())} had used the reference website before; "
          f"mean familiarity with government websites was {p.gov_familiarity.mean():.2f} on a 1–5 scale. "
          f"Practice trials and {int((prep.cleaning_log.step == 'exclusion').sum())} trial(s) excluded for device or app faults were removed before analysis.", "",
          "## Task success", "",
          "Success rates were " + _pat_list({q: f"{psi.loc[q, 'success_rate']:.0%} ({int(psi.loc[q, 'n_success'])}/{int(psi.loc[q, 'n_trials'])})" for q in PATTERNS}) +
          f". Failures were give-ups ({int(ps.n_give_up.sum())}) and time-outs ({int(ps.n_timeout.sum())}). ", ""]
    sa = suite.analyses["success"]
    L += [f"Success rates did {'' if sa.significant else 'not '}differ across patterns ({omnibus_phrase(sa)}"
          + (f"; the primary model was flagged: {'; '.join(sa.reasons)}" if sa.flagged else "")
          + "). Failed trials are excluded from the time and error analyses below.", "",
          "## Hypothesis tests", ""]
    for key in HYP:
        L += [_hyp_paragraph(key, prep, suite, ps), ""]
    L += ["### Where does the time go? (RQ3, Eq. 2)", "", mech, ""]
    sq = suite.analyses["SEQ"]
    L += ["## Secondary outcomes", "",
          "Mean perceived difficulty (Single Ease Question, 1 = very difficult, 7 = very easy) was " +
          _pat_list({q: f"{psi.loc[q, 'SEQ_mean']:.2f}" for q in PATTERNS}) +
          f"; ratings did {'' if sq.significant else 'not '}differ across patterns ({omnibus_phrase(sq)}). ", "",
          "Mean preference rank (1 = most preferred) was " + _pat_list({q: f"{pf.loc[q, 'mean_rank']:.2f}" for q in PATTERNS}) +
          f"; first choices: " + _pat_list({q: str(int(pf.loc[q, 'n_rank1'])) for q in PATTERNS}) +
          f" (Friedman χ²(2) = {suite.preference.chi2:.2f}, {fmt_p(suite.preference.p)}). These outcomes support, rather than test, the hypotheses.", "",
          "## Robustness", ""]
    sens = suite.sensitivity
    ok = sens[sens.agrees_with_primary.notna()] if "agrees_with_primary" in sens else sens.iloc[0:0]
    L += [f"{int(ok.agrees_with_primary.sum())} of {len(ok)} analyses agree with the primary significance (primary models, excluding block 1, "
          "adding covariates, and a Cox model treating failures as censored). Disagreements: " +
          ("; ".join(f"{r.outcome} ({r.analysis})" for r in ok[ok.agrees_with_primary == False].itertuples()) or "none") + ".", "",   # noqa: E712
          "## Limitations to discuss", ""]
    lim = limitations(prep, suite)
    L += [f"- **{r.item}** ({'check' if r.status == 'flag' else 'note'}): {r.detail}" for r in lim.itertuples()]
    L += ["", "## Tables", "", "### Hypothesis decisions", "",
          md_table(dec[["hypothesis", "outcome", "test", "statistic", "df", "p", "decision", "significant_contrasts"]], ".3f"), "",
          "### Per-pattern summary (successful trials unless stated)", "",
          md_table(ps[["pattern", "n_trials", "success_rate", "T_find_median", "E_mean", "share_E_ge1", "n_trials_E_ge1", "R_median", "SEQ_mean"]]), "",
          "## Figures", "",
          "F1 T_find by pattern (H1); F2 errors (H2); F3 recovery time (H3); F4 clean navigation vs recovery (RQ3); F5 success; "
          "F6 difficulty ratings; F7 preference; F8 block/task pair check; F9-F10 path analyses; F11 model diagnostics; F12 pairwise effect sizes. "
          "All in `outputs/figures/`, with the data behind each in `outputs/tables/fig_data_*.csv`.", ""]
    return "\n".join(L)


def write_conclusions(prep, suite: ModelSuite, out_dir) -> dict[str, Path]:
    out = Path(out_dir)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    paths = {"decisions": out / "tables" / "hypothesis_decisions.csv",
             "limitations": out / "tables" / "limitations_checklist.csv",
             "mechanism": out / "tables" / "mechanism_decomposition.csv",
             "draft": out / "results_draft.md"}
    hypothesis_decisions(suite).to_csv(paths["decisions"], index=False)
    limitations(prep, suite).to_csv(paths["limitations"], index=False)
    mechanism(prep, suite)[0].to_csv(paths["mechanism"], index=False)
    paths["draft"].write_text(results_draft(prep, suite), encoding="utf-8")
    return paths

"""Step 6: inferential models (proposal 4.7, Table 4). See docs/ANALYSIS_PLAN.md step 6.

Primary models (pattern fixed effect, block position as covariate; reference level DH):
  T_find (H1)   linear mixed model on log time, participant random intercept   [successful trials]
  E      (H2)   Poisson GEE (negative-binomial GEE if overdispersed), clustered on participant [successful]
  R      (H3)   linear mixed model on log time, trials with E >= 1             [successful]
  success       logistic GEE                                                   [all trials]
  T_clean, SEQ  secondary: same LMM form
Omnibus pattern effect: Wald chi-square (2 df). Pairwise contrasts MM-DH, ND-DH, ND-MM with Holm correction.
Effect sizes with 95% CI: ratio of geometric means (times), rate ratio (counts), odds ratio (success).

Fallback: Friedman test on participant-level values with Wilcoxon signed-rank follow-ups (Holm). It is USED
for the decision when the primary model is not estimable / did not converge, or its residuals clearly violate the
assumptions (Shapiro or Levene p < config.RESID_P). It is always computed so both can be reported.
GEE gives population-averaged effects (a deviation from Table 4's mixed models, see the plan).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.stats.multitest import multipletests

from .config import ALPHA, CONTRASTS, DISPERSION_MAX, PATTERNS, REF_PATTERN, RESID_P
from .describe import geomean

PAT = f"C(pattern, Treatment('{REF_PATTERN}'))"
BLOCK = "C(block_position)"
Z95 = stats.norm.ppf(0.975)


# --- specs ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    hypothesis: str
    response: str
    kind: str                                   # lmm_log | lmm | count | binary
    subset: Callable[[pd.DataFrame], pd.DataFrame]
    agg: str                                    # participant-level aggregate for the Friedman fallback


SPECS = {
    "T_find": Spec("T_find", "Item-finding time", "H1", "T_find", "lmm_log", lambda t: t[t.success == 1], "geomean"),
    "E": Spec("E", "Error count", "H2", "E", "count", lambda t: t[t.success == 1], "mean"),
    "R": Spec("R", "Recovery time", "H3", "R", "lmm_log",
              lambda t: t[(t.success == 1) & (t.E >= 1) & (t.R > 0)], "geomean"),
    "success": Spec("success", "Task success", "", "success", "binary", lambda t: t, "mean"),
    "T_clean": Spec("T_clean", "Clean navigation time", "", "T_clean", "lmm_log",
                    lambda t: t[(t.success == 1) & (t.T_clean > 0)], "geomean"),
    "SEQ": Spec("SEQ", "Perceived difficulty (SEQ)", "", "difficulty_rating", "lmm",
                lambda t: t[t.difficulty_rating.notna()], "mean"),
}


# --- result containers ---------------------------------------------------------------------------
@dataclass
class PrimaryResult:
    model: str
    ok: bool
    n_obs: int = 0
    n_participants: int = 0
    effect_type: str = ""
    omnibus_stat: float = np.nan
    omnibus_df: int = 0
    omnibus_p: float = np.nan
    pairwise: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)
    resid: pd.Series | None = None
    fitted: pd.Series | None = None
    patterns_resid: pd.Series | None = None

    @property
    def significant(self) -> bool:
        return bool(self.ok and self.omnibus_p < ALPHA)


@dataclass
class FallbackResult:
    ok: bool
    n_participants: int = 0
    effect_type: str = ""
    chi2: float = np.nan
    p: float = np.nan
    kendall_w: float = np.nan
    medians: pd.Series | None = None
    pairwise: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)

    @property
    def significant(self) -> bool:
        return bool(self.ok and self.p < ALPHA)


@dataclass
class OutcomeAnalysis:
    spec: Spec
    primary: PrimaryResult
    fallback: FallbackResult
    flagged: bool
    reasons: list[str]
    chosen: str                                  # "primary" | "fallback"

    @property
    def p_chosen(self) -> float:
        return self.primary.omnibus_p if self.chosen == "primary" else self.fallback.p

    @property
    def significant(self) -> bool:
        return bool(self.p_chosen < ALPHA) if not np.isnan(self.p_chosen) else False

    @property
    def pairwise_chosen(self) -> pd.DataFrame:
        return self.primary.pairwise if self.chosen == "primary" else self.fallback.pairwise


# --- inference from fitted parameters ------------------------------------------------------------
def _pname(p: str) -> str:
    return f"{PAT}[T.{p}]"


def inference(params: pd.Series, cov: pd.DataFrame, exp: bool) -> tuple[float, int, float, pd.DataFrame]:
    """Omnibus Wald chi-square for the pattern terms plus Holm-corrected pairwise contrasts.
    exp=True reports exp(estimate) (ratio); exp=False reports the raw difference."""
    nonref = [p for p in PATTERNS if p != REF_PATTERN]
    idx = [_pname(p) for p in nonref]
    b = params[idx].to_numpy(float)
    V = cov.loc[idx, idx].to_numpy(float)
    W = float(b @ np.linalg.solve(V, b))
    df = len(idx)
    rows = []
    for a, c in CONTRASTS:
        L = np.zeros(len(idx))
        if a != REF_PATTERN:
            L[nonref.index(a)] += 1
        if c != REF_PATTERN:
            L[nonref.index(c)] -= 1
        est, se = float(L @ b), float(np.sqrt(L @ V @ L))
        lo, hi = est - Z95 * se, est + Z95 * se
        f = np.exp if exp else (lambda x: x)
        rows.append(dict(contrast=f"{a} vs {c}", effect=f(est), ci_low=f(lo), ci_high=f(hi),
                         p_raw=float(2 * stats.norm.sf(abs(est / se))) if se > 0 else np.nan))
    pw = pd.DataFrame(rows)
    pw["p_holm"] = multipletests(pw.p_raw.fillna(1.0), method="holm")[1]
    pw["significant_holm"] = pw.p_holm < ALPHA
    return W, df, float(stats.chi2.sf(W, df)), pw


def check_residuals(resid: pd.Series, groups: pd.Series) -> list[str]:
    """Assumption flags for the fallback rule: clear non-normality or unequal spread across patterns."""
    reasons = []
    r = pd.Series(resid).dropna()
    if len(r) >= 8:
        p = stats.shapiro(r).pvalue
        if p < RESID_P:
            reasons.append(f"residuals non-normal (Shapiro p = {p:.4f})")
    parts = [r[groups.reindex(r.index) == g] for g in PATTERNS]
    parts = [x for x in parts if len(x) >= 3]
    if len(parts) >= 2:
        p = stats.levene(*parts).pvalue
        if p < RESID_P:
            reasons.append(f"unequal residual spread across patterns (Levene p = {p:.4f})")
    return reasons


# --- fitting -------------------------------------------------------------------------------------
def _fit_lmm(d: pd.DataFrame, y: str, rhs: str):
    notes = []
    for kw in ({}, {"method": "bfgs"}, {"method": "powell"}, {"method": "nm"}):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = smf.mixedlm(f"{y} ~ {rhs}", d, groups=d["participant_id"]).fit(reml=True, **kw)
            if res.converged:
                if float(res.cov_re.iloc[0, 0]) < 1e-6:
                    notes.append("participant variance estimated at ~0 (singular fit): model behaves like ordinary regression")
                return res, notes
            notes.append(f"optimizer {kw.get('method', 'default')} did not converge")
        except Exception as e:                                  # noqa: BLE001
            notes.append(f"optimizer {kw.get('method', 'default')} failed: {type(e).__name__}")
    return None, notes


def _fit_gee(d: pd.DataFrame, y: str, rhs: str, family):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        res = smf.gee(f"{y} ~ {rhs}", "participant_id", d, family=family,
                      cov_struct=sm.cov_struct.Exchangeable()).fit()
    notes = sorted({str(x.message)[:90] for x in w if "converge" in str(x.message).lower()})
    return res, notes


def analyze_primary(spec: Spec, d: pd.DataFrame, rhs: str = BLOCK) -> PrimaryResult:
    d = d.copy().reset_index(drop=True)
    n_obs, n_part = len(d), d.participant_id.nunique()
    if n_obs < 6 or d.pattern.nunique() < 3:
        return PrimaryResult("not fitted", False, n_obs, n_part, notes=["fewer than 6 observations or a pattern is missing"])
    try:
        if spec.kind in ("lmm_log", "lmm"):
            d["_y"] = np.log(d[spec.response]) if spec.kind == "lmm_log" else d[spec.response].astype(float)
            res, notes = _fit_lmm(d, "_y", f"{PAT} + {rhs}")
            if res is None:
                return PrimaryResult("linear mixed model", False, n_obs, n_part, notes=notes)
            fe = res.fe_params.index
            exp = spec.kind == "lmm_log"
            W, df, p, pw = inference(res.fe_params, res.cov_params().loc[fe, fe], exp=exp)
            name = "linear mixed model on log " + spec.response if exp else "linear mixed model (rating treated as continuous)"
            etype = "ratio of geometric means" if exp else "difference in means"
            return PrimaryResult(name, True, n_obs, n_part, etype, W, df, p, pw, notes,
                                 resid=pd.Series(res.resid.values, index=d.index),
                                 fitted=pd.Series(res.fittedvalues.values, index=d.index),
                                 patterns_resid=d.pattern)
        if spec.kind == "count":
            res, notes = _fit_gee(d, spec.response, f"{PAT} + {rhs}", sm.families.Poisson())
            mu = res.fittedvalues
            disp = float((((d[spec.response] - mu) ** 2) / mu).sum() / (n_obs - len(res.params)))
            name = f"Poisson GEE (dispersion {disp:.2f})"
            if disp > DISPERSION_MAX:
                alpha = max(float((((d[spec.response] - mu) ** 2 - mu).sum()) / (mu ** 2).sum()), 1e-4)
                res, n2 = _fit_gee(d, spec.response, f"{PAT} + {rhs}", sm.families.NegativeBinomial(alpha=alpha))
                notes += n2 + [f"overdispersed (Pearson {disp:.2f} > {DISPERSION_MAX}): negative-binomial GEE, alpha = {alpha:.2f}"]
                name = f"negative-binomial GEE (alpha {alpha:.2f})"
            W, df, p, pw = inference(res.params, res.cov_params(), exp=True)
            return PrimaryResult(name, True, n_obs, n_part, "rate ratio", W, df, p, pw, notes)
        if spec.kind == "binary":
            by = d.groupby("pattern")[spec.response].agg(["sum", "count"])
            sep = by[(by["sum"] == 0) | (by["sum"] == by["count"])]
            if len(sep):
                return PrimaryResult("logistic GEE", False, n_obs, n_part, notes=[
                    "complete separation: every trial in pattern(s) " + ", ".join(sep.index) +
                    " has the same outcome, so odds ratios are not estimable"])
            res, notes = _fit_gee(d, spec.response, f"{PAT} + {rhs}", sm.families.Binomial())
            W, df, p, pw = inference(res.params, res.cov_params(), exp=True)
            return PrimaryResult("logistic GEE", True, n_obs, n_part, "odds ratio", W, df, p, pw, notes)
    except Exception as e:                                       # noqa: BLE001
        return PrimaryResult(spec.kind, False, n_obs, n_part, notes=[f"model failed: {type(e).__name__}: {e}"[:160]])
    raise ValueError(spec.kind)


def friedman_fallback(tab: pd.DataFrame, log_ratio: bool) -> FallbackResult:
    """tab: participant x pattern values. Friedman test + Wilcoxon signed-rank follow-ups with Holm correction.
    log_ratio=True reports the median paired ratio (times), else the median paired difference."""
    tab = tab[list(PATTERNS)].dropna()
    n = len(tab)
    if n < 4:
        return FallbackResult(False, n, notes=[f"only {n} participants have a value under all three patterns"])
    notes = []
    stat, p = stats.friedmanchisquare(*[tab[x] for x in PATTERNS])
    if np.isnan(p):
        notes.append("no variation across patterns")
    rows = []
    for a, c in CONTRASTS:
        d = np.log(tab[a] / tab[c]) if log_ratio else tab[a] - tab[c]
        try:
            pw = float(stats.wilcoxon(d).pvalue)
        except ValueError:                                     # all differences zero
            pw = 1.0
        eff = float(np.exp(d.median())) if log_ratio else float(d.median())
        rows.append(dict(contrast=f"{a} vs {c}", effect=eff, ci_low=np.nan, ci_high=np.nan, p_raw=pw))
    pwdf = pd.DataFrame(rows)
    pwdf["p_holm"] = multipletests(pwdf.p_raw, method="holm")[1]
    pwdf["significant_holm"] = pwdf.p_holm < ALPHA
    return FallbackResult(True, n, "median paired ratio" if log_ratio else "median paired difference",
                          float(stat), float(p), float(stat / (n * (len(PATTERNS) - 1))),
                          tab.median(), pwdf, notes)


def _participant_table(d: pd.DataFrame, response: str, agg: str) -> pd.DataFrame:
    f = geomean if agg == "geomean" else "mean"
    return d.groupby(["participant_id", "pattern"])[response].agg(f).unstack("pattern").reindex(columns=list(PATTERNS))


def analyze(spec: Spec, trials: pd.DataFrame, rhs: str = BLOCK) -> OutcomeAnalysis:
    d = spec.subset(trials)
    primary = analyze_primary(spec, d, rhs)
    fallback = friedman_fallback(_participant_table(d, spec.response, spec.agg), log_ratio=spec.kind == "lmm_log")
    reasons = []
    if not primary.ok:
        reasons.append("primary model not estimable: " + "; ".join(primary.notes))
    elif primary.resid is not None:
        reasons += check_residuals(primary.resid, primary.patterns_resid)
    flagged = bool(reasons)
    chosen = "fallback" if flagged and fallback.ok else "primary"
    if flagged and not fallback.ok:
        reasons.append("fallback also unavailable: " + "; ".join(fallback.notes))
    return OutcomeAnalysis(spec, primary, fallback, flagged, reasons, chosen)


# --- sensitivity analyses ------------------------------------------------------------------------
def analyze_cox(trials: pd.DataFrame, rhs: str = BLOCK) -> PrimaryResult:
    """All trials; failures are right-censored at the trial end (180 s for time-outs). HR > 1 = reaches target sooner."""
    d = trials.reset_index(drop=True)
    X = patsy.dmatrix(f"{PAT} + {rhs}", d, return_type="dataframe").drop(columns="Intercept")
    res = PHReg(d.T_find.values, X.values, status=d.success.values).fit(groups=d.participant_id.values)
    params = pd.Series(np.asarray(res.params), index=X.columns)
    cov = pd.DataFrame(np.asarray(res.cov_params()), index=X.columns, columns=X.columns)
    W, df, p, pw = inference(params, cov, exp=True)
    return PrimaryResult("Cox model, failures censored (cluster-robust)", True, len(d), d.participant_id.nunique(),
                         "hazard ratio (>1 = reaches target sooner)", W, df, p, pw)


VARIANTS = (
    ("excluding block position 1", lambda d: d[d.block_position > 1], BLOCK),
    ("+ familiarity and prior use", lambda d: d, f"{BLOCK} + gov_familiarity + C(used_reference_site)"),
)


def run_sensitivity(trials: pd.DataFrame, analyses: dict[str, OutcomeAnalysis]) -> tuple[pd.DataFrame, PrimaryResult | None]:
    rows = []

    def add(outcome, label, res: PrimaryResult, base_sig: bool):
        rows.append(dict(outcome=outcome, analysis=label, model=res.model, n_obs=res.n_obs, ok=res.ok,
                         omnibus_p=res.omnibus_p, significant=res.significant,
                         agrees_with_primary=(res.significant == base_sig) if res.ok else np.nan,
                         note="; ".join(res.notes)))

    for key in ("T_find", "E", "R"):
        base = analyses[key]
        add(key, "primary model", base.primary, base.primary.significant)
        for label, sel, rhs in VARIANTS:
            add(key, label, analyze_primary(base.spec, sel(base.spec.subset(trials)), rhs), base.primary.significant)
    cox = None
    try:
        cox = analyze_cox(trials)
        add("T_find", "Cox model, failures censored at trial end", cox, analyses["T_find"].primary.significant)
    except Exception as e:                                         # noqa: BLE001
        rows.append(dict(outcome="T_find", analysis="Cox model, failures censored at trial end", ok=False,
                         note=f"{type(e).__name__}: {e}"[:160]))
    return pd.DataFrame(rows), cox


# --- everything ----------------------------------------------------------------------------------
@dataclass
class ModelSuite:
    analyses: dict[str, OutcomeAnalysis]
    preference: FallbackResult
    sensitivity: pd.DataFrame
    cox: PrimaryResult | None

    def summary(self) -> pd.DataFrame:
        rows = []
        for key, a in self.analyses.items():
            pr, fb = a.primary, a.fallback
            rows.append(dict(
                outcome=key, label=a.spec.label, hypothesis=a.spec.hypothesis, primary_model=pr.model,
                n_obs=pr.n_obs, n_participants=pr.n_participants, effect_type=pr.effect_type,
                omnibus_chi2=pr.omnibus_stat, omnibus_df=pr.omnibus_df, omnibus_p=pr.omnibus_p,
                flagged_for_fallback=a.flagged, flag_reasons=" | ".join(a.reasons),
                friedman_chi2=fb.chi2, friedman_p=fb.p, friedman_kendall_w=fb.kendall_w,
                friedman_n=fb.n_participants, decision_source=a.chosen, decision_p=a.p_chosen,
                significant=a.significant, notes=" | ".join(pr.notes)))
        return pd.DataFrame(rows)

    def pairwise(self) -> pd.DataFrame:
        parts = []
        for key, a in self.analyses.items():
            for src, res in (("primary", a.primary), ("fallback", a.fallback)):
                if res.ok and len(res.pairwise):
                    pw = res.pairwise.copy()
                    pw.insert(0, "source", src)
                    pw.insert(0, "outcome", key)
                    pw["effect_type"] = res.effect_type
                    pw["is_decision_source"] = src == a.chosen
                    parts.append(pw)
        if self.cox is not None and len(self.cox.pairwise):
            pw = self.cox.pairwise.copy()
            pw.insert(0, "source", "sensitivity")
            pw.insert(0, "outcome", "T_find (Cox)")
            pw["effect_type"] = self.cox.effect_type
            pw["is_decision_source"] = False
            parts.append(pw)
        return pd.concat(parts, ignore_index=True)

    def write(self, out_dir):
        from pathlib import Path
        d = Path(out_dir) / "tables"
        d.mkdir(parents=True, exist_ok=True)
        self.summary().to_csv(d / "model_summary.csv", index=False)
        self.pairwise().to_csv(d / "model_pairwise.csv", index=False)
        self.sensitivity.to_csv(d / "model_sensitivity.csv", index=False)
        pf = self.preference
        pd.DataFrame([dict(test="Friedman on preference ranks", n=pf.n_participants, chi2=pf.chi2, p=pf.p,
                           kendall_w=pf.kendall_w, **({f"median_rank_{k}": v for k, v in pf.medians.items()}
                                                      if pf.medians is not None else {}))]).to_csv(
            d / "model_preference.csv", index=False)
        return d


def run_models(prep) -> ModelSuite:
    """`prep` is a pipeline.prepare.Prepared."""
    trials = prep.trials
    analyses = {k: analyze(s, trials) for k, s in SPECS.items()}
    pt = prep.clean.participants.set_index("participant_id")
    ranks = pt[[f"rank_{p}" for p in PATTERNS]].set_axis(list(PATTERNS), axis=1)
    pref = friedman_fallback(ranks, log_ratio=False)
    sens, cox = run_sensitivity(trials, analyses)
    return ModelSuite(analyses, pref, sens, cox)

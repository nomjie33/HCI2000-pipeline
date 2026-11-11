"""Step 4: descriptive tables (no inference). All functions take the derived trial table (and, for the
path analyses, the cleaned events + tree) and return DataFrames, so figures and notebooks share one source.

Basis of each table (stated here and in the table names so it is never ambiguous):
  * T_find, T_clean, E, R: successful trials only (proposal 4.7). R additionally needs E >= 1.
  * success, failure type, SEQ rating: all analysed trials.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MIN_SELECTIONS, PATTERNS

NAMES = {"DH": "Deep hierarchical", "MM": "Mega-menu", "ND": "Nested dropdown"}


# --- small helpers ------------------------------------------------------------------------------
def geomean(x) -> float:
    x = np.asarray(x, dtype=float)
    x = x[x > 0]
    return float(np.exp(np.mean(np.log(x)))) if len(x) else np.nan


def _q(x, q: float) -> float:
    return float(np.quantile(x, q)) if len(x) else np.nan


def _mean(x) -> float:
    return float(np.mean(x)) if len(x) else np.nan


def successful(trials: pd.DataFrame) -> pd.DataFrame:
    return trials[trials.success == 1]


def participant_pattern_means(trials: pd.DataFrame, col: str, geometric: bool = False,
                              only_errors: bool = False) -> pd.DataFrame:
    """Participant x pattern table of mean `col` over that participant's successful trials."""
    d = successful(trials)
    if only_errors:
        d = d[d.E >= 1]
    f = geomean if geometric else np.mean
    out = d.groupby(["participant_id", "pattern"])[col].apply(f).unstack("pattern")
    return out.reindex(columns=list(PATTERNS))


# --- sample, per-pattern summary, secondary outcomes ---------------------------------------------
def sample_summary(participants: pd.DataFrame) -> pd.DataFrame:
    p = participants
    rows = [("Participants (N)", len(p))]
    rows += [(f"Sequence {s}", int(n)) for s, n in p.groupby("sequence").size().items()]
    rows += [("Age, mean (SD)", f"{p.age.mean():.1f} ({p.age.std():.1f})"),
             ("Age, range", f"{int(p.age.min())}-{int(p.age.max())}")]
    rows += [(f"Gender: {g}", int(n)) for g, n in p.groupby("gender").size().items()]
    rows += [("Familiarity with gov. websites (1-5), mean (SD)", f"{p.gov_familiarity.mean():.2f} ({p.gov_familiarity.std():.2f})"),
             ("Used the reference website before", int((p.used_reference_site == "Y").sum()))]
    return pd.DataFrame(rows, columns=["variable", "value"])


def pattern_summary(trials: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for p in PATTERNS:
        d = trials[trials.pattern == p]
        s = d[d.success == 1]
        r = s[s.E >= 1]
        rows.append(dict(
            pattern=p, min_selections=MIN_SELECTIONS[p], n_trials=len(d), n_success=len(s),
            success_rate=len(s) / len(d) if len(d) else np.nan,
            n_give_up=int((d.end_reason == "give_up").sum()), n_timeout=int((d.end_reason == "timeout").sum()),
            T_find_median=_q(s.T_find, .5), T_find_q1=_q(s.T_find, .25), T_find_q3=_q(s.T_find, .75),
            T_find_geomean=geomean(s.T_find),
            T_clean_median=_q(s.T_clean, .5), T_clean_geomean=geomean(s.T_clean),
            E_mean=_mean(s.E), E_sd=float(s.E.std()) if len(s) > 1 else np.nan,
            share_E_ge1=float((s.E >= 1).mean()) if len(s) else np.nan,
            n_trials_E_ge1=len(r), R_median=_q(r.R, .5), R_q1=_q(r.R, .25), R_q3=_q(r.R, .75),
            R_geomean=geomean(r.R), R_mean_all_successful=_mean(s.R),
            SEQ_mean=_mean(d.difficulty_rating.dropna()),
        ))
    return pd.DataFrame(rows)


def e_distribution(trials: pd.DataFrame) -> pd.DataFrame:
    """Share of successful trials with E = 0, 1, 2, 3+ per pattern."""
    s = successful(trials).assign(E_cat=lambda d: d.E.clip(upper=3).map({0: "0", 1: "1", 2: "2", 3: "3+"}))
    n = s.groupby(["pattern", "E_cat"]).size().unstack(fill_value=0).reindex(index=list(PATTERNS),
                                                                         columns=["0", "1", "2", "3+"], fill_value=0)
    return n.div(n.sum(axis=1), axis=0)


def seq_distribution(trials: pd.DataFrame) -> pd.DataFrame:
    """Counts of SEQ ratings 1-7 per pattern (all analysed trials)."""
    return (trials.groupby(["pattern", "difficulty_rating"]).size().unstack(fill_value=0)
            .reindex(index=list(PATTERNS), columns=range(1, 8), fill_value=0))


def preference_summary(participants: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for p in PATTERNS:
        r = participants[f"rank_{p}"]
        rows.append(dict(pattern=p, mean_rank=r.mean(), n_rank1=int((r == 1).sum()),
                         n_rank2=int((r == 2).sum()), n_rank3=int((r == 3).sum())))
    return pd.DataFrame(rows)


def order_effects(trials: pd.DataFrame) -> pd.DataFrame:
    """Geometric-mean T_find (successful trials) by pattern x block position and by pattern x task pair.
    Descriptive check only: CI is 1.96 SE of log T_find over trials, ignoring clustering."""
    s = successful(trials)
    out = []
    for factor in ("block_position", "task_pair"):
        for (p, lvl), g in s.groupby(["pattern", factor]):
            lt = np.log(g.T_find)
            se = lt.std(ddof=1) / np.sqrt(len(lt)) if len(lt) > 1 else np.nan
            out.append(dict(factor=factor, level=lvl, pattern=p, n=len(g), T_find_geomean=np.exp(lt.mean()),
                            ci_low=np.exp(lt.mean() - 1.96 * se), ci_high=np.exp(lt.mean() + 1.96 * se)))
    return pd.DataFrame(out)


# --- path analyses (uses the selection path recorded in the event log) --------------------------
def error_selections(events: pd.DataFrame, tree, trials: pd.DataFrame) -> pd.DataFrame:
    """One row per off-path `select` in successful trials: which wrong node was chosen, and where."""
    ok_trials = set(trials.loc[trials.success == 1, "trial_id"])
    sel = events[(events.event_type == "select") & events.trial_id.isin(ok_trials)]
    off = [n not in set(tree.path(t)) for n, t in zip(sel.node_id, sel.target_node)]
    err = sel[off].copy()
    err["level"] = err.node_id.map(tree.level).astype(int)
    return err[["trial_id", "participant_id", "pattern", "target_node", "node_id", "level"]].reset_index(drop=True)


def tree_labels(tree_df: pd.DataFrame) -> dict:
    return dict(zip(tree_df.node_id, tree_df.label))


def errors_by_level(err: pd.DataFrame, trials: pd.DataFrame) -> pd.DataFrame:
    """Mean wrong selections per successful trial at each tree level (L1/L2/L3), by pattern."""
    n_trials = successful(trials).groupby("pattern").size()
    c = err.groupby(["pattern", "level"]).size().unstack(fill_value=0).reindex(index=list(PATTERNS),
                                                                           columns=[1, 2, 3], fill_value=0)
    out = c.div(n_trials.reindex(c.index), axis=0)
    out.columns = ["L1", "L2", "L3"]
    return out


def top_wrong_nodes(err: pd.DataFrame, tree_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    labels = tree_labels(tree_df)
    c = err.groupby(["node_id", "level"]).size().rename("n_errors").reset_index()
    c["label"] = c.node_id.map(labels)
    return c.sort_values(["n_errors", "node_id"], ascending=[False, True]).head(n).reset_index(drop=True)


def confusion_by_target(err: pd.DataFrame, tree_df: pd.DataFrame) -> pd.DataFrame:
    """For each target: which wrong nodes were selected, how often (the misleading-label table)."""
    labels = tree_labels(tree_df)
    c = err.groupby(["target_node", "node_id"]).size().rename("n_errors").reset_index()
    c["wrong_label"] = c.node_id.map(labels)
    c["target_label"] = c.target_node.map(labels)
    return c.sort_values(["target_node", "n_errors"], ascending=[True, False]).reset_index(drop=True)


def path_efficiency(trials: pd.DataFrame) -> pd.DataFrame:
    """Selections vs the minimum, and Back/collapse/logo actions, per pattern (successful trials)."""
    s = successful(trials).assign(excess_selections=lambda d: d.n_selections - d.min_selections)
    g = s.groupby("pattern").agg(n=("trial_id", "size"), min_selections=("min_selections", "first"),
                                 mean_selections=("n_selections", "mean"),
                                 mean_excess_selections=("excess_selections", "mean"),
                                 share_direct_path=("excess_selections", lambda x: float((x == 0).mean())),
                                 mean_back_actions=("n_back_actions", "mean"))
    return g.reindex(list(PATTERNS)).reset_index()


# --- one call that writes every table -----------------------------------------------------------
def describe_all(prep, out_dir) -> dict[str, pd.DataFrame]:
    """`prep` is a pipeline.prepare.Prepared. Writes CSVs under <out_dir>/tables and returns the tables."""
    from pathlib import Path

    t, ds = prep.trials, prep.clean
    err = error_selections(ds.events, ds.tree, t)
    tables = {
        "sample": sample_summary(ds.participants),
        "pattern_summary": pattern_summary(t),
        "e_distribution": e_distribution(t).reset_index(),
        "seq_distribution": seq_distribution(t).reset_index(),
        "preference": preference_summary(ds.participants),
        "order_effects": order_effects(t),
        "path_efficiency": path_efficiency(t),
        "errors_by_level": errors_by_level(err, t).reset_index(),
        "top_wrong_nodes": top_wrong_nodes(err, ds.tree_df, n=15),
        "confusion_by_target": confusion_by_target(err, ds.tree_df),
    }
    d = Path(out_dir) / "tables"
    d.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(d / f"desc_{name}.csv", index=False)
    return tables

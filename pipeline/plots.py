"""Step 5: figures (static PNG + SVG for the paper) and the data table behind each one.

Design (dataviz skill): one fixed colour per navigation pattern in every figure; text in ink tokens, never in
series colour; hairline grid; pattern names on the x-axis so identity is never colour-alone; every figure's
plotted numbers are also written to outputs/tables/fig_data_<name>.csv (the "table view").
Palette = first three categorical slots (blue, orange, aqua); validated for all pairs in light mode.
Aqua is below 3:1 contrast on the light surface, so labels and the data tables carry identity as well.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, NullFormatter, PercentFormatter
from scipy import stats

from .config import PATTERNS
from .describe import (NAMES, e_distribution, error_selections, errors_by_level, order_effects,
                       participant_pattern_means, preference_summary, seq_distribution, successful, top_wrong_nodes)

ORDER = list(PATTERNS)
COLORS = {"DH": "#2a78d6", "MM": "#eb6834", "ND": "#1baf7a"}
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
NEUTRAL = "#f0efec"
RING = 1.5            # ~2px surface ring / gap between fills

RC = {
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"], "font.size": 9.5,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True, "hatch.linewidth": 1.0,
    "legend.frameon": False, "svg.fonttype": "none",
}


def _blend(c: str, w: str, t: float) -> str:
    """Mix colour c toward w by fraction t."""
    a = np.array(matplotlib.colors.to_rgb(c)); b = np.array(matplotlib.colors.to_rgb(w))
    return matplotlib.colors.to_hex(a * (1 - t) + b * t)


def _label(p: str) -> str:
    return f"{NAMES[p]}\n({p})"


def _title(ax, title: str, basis: str) -> None:
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.035, basis, transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom")


def _grid(ax, axis="y") -> None:
    ax.grid(axis=axis, visible=True)
    ax.tick_params(length=0)


def _logaxis(ax, ticks) -> None:
    ax.set_yscale("log")
    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())


def _pattern_ticks(ax, counts: dict | None = None, short: bool = False) -> None:
    ax.set_xticks(range(len(ORDER)))
    labs = [(p if short else _label(p)) + (f"\nn = {counts[p]}" if counts is not None else "") for p in ORDER]
    ax.set_xticklabels(labs)
    ax.set_xlim(-0.6, len(ORDER) - 0.4)


def _legend_patterns(ax, **kw) -> None:
    kw.setdefault("ncol", 3)
    ax.legend(handles=[Patch(facecolor=COLORS[p], label=NAMES[p]) for p in ORDER], **kw)


def _dot(ax, x, y, p, s=46, z=3):
    ax.scatter(x, y, s=s, color=COLORS[p], edgecolor=SURFACE, linewidth=RING, zorder=z)


def _box(ax, vals, pos, p) -> None:
    vals = pd.Series(vals).dropna()
    if len(vals) == 0:
        return
    ax.boxplot(vals, positions=[pos], widths=0.34, showfliers=False,
               boxprops=dict(color=COLORS[p], linewidth=1.4), whiskerprops=dict(color=COLORS[p], linewidth=1.2),
               capprops=dict(color=COLORS[p], linewidth=1.2), medianprops=dict(color=INK, linewidth=2), zorder=2)


# --- figures: each returns (fig, data_frame) -----------------------------------------------------
def f1_tfind(trials, **_):
    pm = participant_pattern_means(trials, "T_find", geometric=True)
    s = successful(trials)
    rng = np.random.default_rng(1)
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    for _, row in pm.dropna().iterrows():
        ax.plot(range(3), row.values, color=AXIS, linewidth=0.8, zorder=1)
    for i, p in enumerate(ORDER):
        d = s[s.pattern == p].T_find
        ax.scatter(i + rng.uniform(-0.12, 0.12, len(d)), d, s=12, color=COLORS[p], alpha=0.35, linewidth=0, zorder=2)
        _box(ax, pm[p], i, p)
        _dot(ax, np.full(pm[p].notna().sum(), i), pm[p].dropna(), p)
    _pattern_ticks(ax, {p: int(pm[p].notna().sum()) for p in ORDER})
    ax.set_ylabel("Item-finding time, T_find (s, log scale)")
    _logaxis(ax, [2, 5, 10, 20, 40, 80, 160])
    ax.set_ylim(s.T_find.min() * 0.8, s.T_find.max() * 1.25)
    _grid(ax)
    _title(ax, "Item-finding time by navigation pattern",
           "Big dots: participant geometric means (n = participants); small dots: trials; grey lines join a participant; box: IQR, bar: median. Successful trials.")
    return fig, pm.reset_index()


def f2_errors(trials, **_):
    dist = e_distribution(trials)
    pm = participant_pattern_means(trials, "E")
    fig, (a, b) = plt.subplots(1, 2, figsize=(8.6, 4.4), gridspec_kw=dict(width_ratios=[1.5, 1], wspace=0.3))
    cats, w = ["0", "1", "2", "3+"], 0.26
    for i, p in enumerate(ORDER):
        xs = np.arange(4) + (i - 1) * (w + 0.02)
        a.bar(xs, dist.loc[p, cats].values, width=w, color=COLORS[p], edgecolor=SURFACE, linewidth=RING, label=NAMES[p])
    a.set_xticks(range(4)); a.set_xticklabels(cats)
    a.set_xlabel("Errors in the trial (E)"); a.set_ylabel("Share of trials")
    a.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0)); _grid(a)
    a.legend(loc="upper right", fontsize=8.5)
    _title(a, "Errors per trial", "Share of successful trials by number of wrong selections.")
    rows = []
    for i, p in enumerate(ORDER):
        v = pm[p].dropna()
        m = v.mean()
        h = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
        b.errorbar(i, m, yerr=h, color=INK2, linewidth=1.2, capsize=3, zorder=2)
        _dot(b, [i], [m], p, s=70)
        rows.append(dict(pattern=p, n_participants=len(v), mean_E=m, ci_low=m - h, ci_high=m + h))
    _pattern_ticks(b, short=True); b.set_ylim(bottom=0); b.set_ylabel("Mean errors per trial (E)"); _grid(b)
    _title(b, "Mean errors", "Participant means, 95% CI.")
    out = dist.reset_index().merge(pd.DataFrame(rows), on="pattern")
    return fig, out


def f3_recovery(trials, **_):
    s = successful(trials)
    d = s[(s.E >= 1) & (s.R > 0)]
    rng = np.random.default_rng(2)
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    for i, p in enumerate(ORDER):
        v = d[d.pattern == p].R
        ax.scatter(i + rng.uniform(-0.12, 0.12, len(v)), v, s=22, color=COLORS[p], edgecolor=SURFACE,
                   linewidth=1.0, zorder=3, alpha=0.9)
        _box(ax, v, i, p)
    _pattern_ticks(ax, {p: int((d.pattern == p).sum()) for p in ORDER})
    ax.set_ylabel("Recovery time, R (s, log scale)")
    _logaxis(ax, [0.5, 1, 2, 5, 10, 20, 40, 80]); _grid(ax)
    _title(ax, "Recovery time after wrong-path selections",
           "Each dot is one successful trial with at least one error (n = trials). Box: IQR, bar: median.")
    return fig, d[["trial_id", "participant_id", "pattern", "E", "R"]]


def f4_decomposition(trials, **_):
    s = successful(trials)
    g = s.groupby("pattern")[["T_clean", "R", "T_find"]].mean().reindex(ORDER)
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    for i, p in enumerate(ORDER):
        c, r = g.loc[p, "T_clean"], g.loc[p, "R"]
        ax.bar(i, c, width=0.5, color=COLORS[p], edgecolor=SURFACE, linewidth=RING, zorder=2)
        ax.bar(i, r, width=0.5, bottom=c, facecolor=_blend(COLORS[p], SURFACE, 0.55), edgecolor=COLORS[p],
               hatch="////", linewidth=0, zorder=2)
        ax.text(i, c / 2, f"{c:.1f} s", ha="center", va="center", color="#ffffff", fontweight="bold", fontsize=9)
        ax.text(i, c + r + 0.3, f"{c + r:.1f} s total", ha="center", va="bottom", color=INK, fontsize=9)
        if r > 1.2:
            ax.text(i, c + r / 2, f"{r:.1f}", ha="center", va="center", color=INK, fontsize=8.5,
                    bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.85))
    _pattern_ticks(ax); ax.set_ylim(0, g.T_find.max() * 1.15)
    ax.set_ylabel("Mean time per trial (s)")
    ax.legend(handles=[Patch(facecolor=MUTED, label="Clean navigation, T_clean"),
                       Patch(facecolor=SURFACE, edgecolor=MUTED, hatch="////", label="Recovery, R")],
              loc="upper left", fontsize=8.5)
    _grid(ax)
    _title(ax, "Where does the time go? T_find = T_clean + R",
           "Mean over successful trials. If the hatched part explains the gap, differences come from recovery.")
    return fig, g.reset_index()


def f5_success(trials, **_):
    rows = []
    for p in ORDER:
        d = trials[trials.pattern == p]
        rows.append(dict(pattern=p, n_trials=len(d), n_success=int(d.success.sum()), success_rate=d.success.mean(),
                         n_give_up=int((d.end_reason == "give_up").sum()), n_timeout=int((d.end_reason == "timeout").sum())))
    t = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    for i, r in t.iterrows():
        ax.bar(i, r.success_rate, width=0.5, color=COLORS[r.pattern], edgecolor=SURFACE, linewidth=RING, zorder=2)
        ax.text(i, r.success_rate + 0.015, f"{r.success_rate:.0%}", ha="center", va="bottom", fontweight="bold")
        ax.text(i, 0.04, f"{r.n_success}/{r.n_trials}", ha="center", va="bottom", color="#ffffff", fontsize=9)
    _pattern_ticks(ax)
    for i, r in t.iterrows():
        ax.annotate(f"{r.n_give_up} give-up, {r.n_timeout} timeout", (i, 0), xytext=(0, -42),
                    textcoords="offset points", ha="center", fontsize=8, color=INK2, annotation_clip=False)
    ax.set_ylim(0, 1.1); ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_ylabel("Trials that reached the target"); _grid(ax)
    _title(ax, "Task success by navigation pattern", "All analysed trials. Failures: Give up tapped, or 180 s time-out.")
    fig.subplots_adjust(bottom=0.25)
    return fig, t


def f6_seq(trials, **_):
    cnt = seq_distribution(trials)
    pct = cnt.div(cnt.sum(axis=1), axis=0) * 100
    blue = {5: "#9ec5f4", 6: "#5598e7", 7: "#256abf"}
    red = {3: _blend("#e34948", "#ffffff", 0.55), 2: _blend("#e34948", "#ffffff", 0.25), 1: "#e34948"}
    col = {**blue, **red, 4: NEUTRAL}
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for y, p in enumerate(ORDER):
        s = pct.loc[p]
        half = s[4] / 2
        segs = [(4, -half, half)]
        left = -half
        for r in (3, 2, 1):
            segs.append((r, left - s[r], left)); left -= s[r]
        right = half
        for r in (5, 6, 7):
            segs.append((r, right, right + s[r])); right += s[r]
        for r, x0, x1 in segs:
            ax.barh(y, x1 - x0, left=x0, height=0.55, color=col[r], edgecolor=SURFACE if r != 4 else AXIS,
                    linewidth=RING if r != 4 else 0.8, zorder=2)
            if x1 - x0 >= 7:
                ax.text((x0 + x1) / 2, y, f"{x1 - x0:.0f}%", ha="center", va="center", fontsize=8.5,
                        color="#ffffff" if r in (1, 7) else INK)
    ax.axvline(0, color=INK2, linewidth=0.8, zorder=1)
    ax.set_yticks(range(3))
    ax.set_yticklabels([f"{NAMES[p]} ({p})\nmean {trials[trials.pattern == p].difficulty_rating.mean():.1f}" for p in ORDER])
    ax.invert_yaxis()
    arm = max((pct[[1, 2, 3]].sum(axis=1) + pct[4] / 2).max(), (pct[[5, 6, 7]].sum(axis=1) + pct[4] / 2).max())
    lim = float(np.ceil(arm / 10) * 10)
    ax.set_xlim(-lim, lim); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):.0f}%"))
    ax.set_xlabel("Share of ratings"); _grid(ax, "x")
    labels = {1: "1 very difficult", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7 very easy"}
    ax.legend(handles=[Patch(facecolor=col[r], edgecolor=AXIS if r == 4 else col[r], label=labels[r]) for r in range(1, 8)],
              ncol=7, loc="upper center", bbox_to_anchor=(0.5, -0.22), fontsize=8, handlelength=1.2, columnspacing=1)
    _title(ax, "Perceived difficulty after each task (Single Ease Question)", "Difficult ratings left of centre, easy ratings right. All analysed trials.")
    return fig, cnt.reset_index()


def f7_preference(participants, **_):
    pref = preference_summary(participants)
    shades = {1: "#1c5cab", 2: "#3987e5", 3: "#86b6ef"}
    names = {1: "1st (most preferred)", 2: "2nd", 3: "3rd"}
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    for y, p in enumerate(ORDER):
        left = 0
        for r in (1, 2, 3):
            n = int(pref.loc[pref.pattern == p, f"n_rank{r}"].iloc[0])
            ax.barh(y, n, left=left, height=0.55, color=shades[r], edgecolor=SURFACE, linewidth=RING, zorder=2)
            if n:
                ax.text(left + n / 2, y, str(n), ha="center", va="center", fontsize=9,
                        color=INK if r == 3 else "#ffffff", fontweight="bold")
            left += n
    ax.set_yticks(range(3)); ax.invert_yaxis()
    ax.set_yticklabels([f"{NAMES[p]} ({p})\nmean rank {pref.loc[pref.pattern == p, 'mean_rank'].iloc[0]:.2f}" for p in ORDER])
    ax.set_xlabel("Participants"); _grid(ax, "x")
    ax.legend(handles=[Patch(facecolor=shades[r], label=names[r]) for r in (1, 2, 3)], ncol=3,
              loc="upper center", bbox_to_anchor=(0.5, -0.25), fontsize=8.5)
    _title(ax, "Preference ranking of the three menu styles", "Number of participants giving each rank (1 = most preferred).")
    return fig, pref


def _line_panel(ax, oe, factor, levels, xlab):
    sub = oe[oe.factor == factor]
    for p in ORDER:
        d = sub[sub.pattern == p].set_index("level").reindex(levels)
        x = np.arange(len(levels))
        ax.plot(x, d.T_find_geomean, color=COLORS[p], linewidth=2, zorder=2)
        ax.errorbar(x, d.T_find_geomean, yerr=[d.T_find_geomean - d.ci_low, d.ci_high - d.T_find_geomean],
                    fmt="none", ecolor=COLORS[p], elinewidth=1, capsize=2.5, zorder=2)
        ax.scatter(x, d.T_find_geomean, s=40, color=COLORS[p], edgecolor=SURFACE, linewidth=RING, zorder=3)
        ax.text(len(levels) - 1 + 0.08, d.T_find_geomean.iloc[-1], p, color=INK2, va="center", fontsize=9)
    ax.set_xticks(range(len(levels))); ax.set_xticklabels([str(l) for l in levels]); ax.set_xlim(-0.3, len(levels) - 0.6)
    ax.set_xlabel(xlab); _logaxis(ax, [5, 10, 20, 40, 80]); _grid(ax)


def f8_order(trials, **_):
    # In the Latin square (Table 3) block 1 is always pair A, block 2 pair B, block 3 pair C, so block position
    # and task pair are the same factor: they cannot be separated, and one panel shows both.
    oe = order_effects(trials)
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    _line_panel(ax, oe, "block_position", [1, 2, 3], "Block position in the session (= task pair A, B, C)")
    ax.set_xticklabels(["1  (pair A)", "2  (pair B)", "3  (pair C)"])
    ax.set_ylabel("Geometric mean T_find (s, log scale)")
    _title(ax, "Block position / task-pair check",
           "Geometric mean T_find, successful trials; whiskers 1.96 SE of log time (ignores clustering).")
    _legend_patterns(ax, loc="upper left", fontsize=8.5, ncol=1)
    return fig, oe


def f9_error_levels(trials, events, tree, **_):
    err = error_selections(events, tree, trials)
    lv = errors_by_level(err, trials)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    w = 0.26
    for i, p in enumerate(ORDER):
        xs = np.arange(3) + (i - 1) * (w + 0.02)
        vals = lv.loc[p, ["L1", "L2", "L3"]].values
        ax.bar(xs, vals, width=w, color=COLORS[p], edgecolor=SURFACE, linewidth=RING, zorder=2)
        for x, v in zip(xs, vals):
            if p == "MM" and x == xs[1]:
                ax.text(x, 0.01, "n/a", ha="center", va="bottom", color=INK2, fontsize=8)
            else:
                ax.text(x, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(range(3)); ax.set_xticklabels(["Level 1\n(categories)", "Level 2\n(subcategories)", "Level 3\n(pages)"])
    ax.set_ylabel("Wrong selections per trial"); ax.set_ylim(0, lv.values.max() * 1.3); _grid(ax)
    _legend_patterns(ax, loc="upper left", fontsize=8.5)
    _title(ax, "Where do wrong selections happen?",
           "Mean wrong selections per successful trial at each tree level. Mega-menu L2 headings are not selectable (n/a).")
    return fig, lv.reset_index()


def f10_wrong_nodes(trials, events, tree, tree_df, **_):
    err = error_selections(events, tree, trials)
    top = top_wrong_nodes(err, tree_df, n=10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    y = np.arange(len(top))
    ax.barh(y, top.n_errors, height=0.55, color=COLORS["DH"], edgecolor=SURFACE, linewidth=RING, zorder=2)
    for yi, n in zip(y, top.n_errors):
        ax.text(n + 0.1, yi, str(n), va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels([f"{r.node_id}  {r.label}" for r in top.itertuples()], fontsize=8.5)
    ax.set_xlabel("Times selected by mistake (all patterns pooled)"); _grid(ax, "x")
    _title(ax, "Most frequently chosen wrong items", "Off-path selections in successful trials; candidates for misleading labels.")
    return fig, top.iloc[::-1]


FIGURES = {
    "F1_tfind_by_pattern": f1_tfind,
    "F2_errors_by_pattern": f2_errors,
    "F3_recovery_time": f3_recovery,
    "F4_clean_vs_recovery": f4_decomposition,
    "F5_success": f5_success,
    "F6_difficulty_ratings": f6_seq,
    "F7_preference_ranking": f7_preference,
    "F8_order_and_task_pair": f8_order,
    "F9_errors_by_tree_level": f9_error_levels,
    "F10_most_chosen_wrong_items": f10_wrong_nodes,
}


def f11_diagnostics(suite):
    """Residual checks for the two linear mixed models on log time (H1 and H3)."""
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 6.9), gridspec_kw=dict(hspace=0.55, wspace=0.28))
    rows = []
    for r, (key, nm) in enumerate((("T_find", "log T_find (H1)"), ("R", "log R (H3)"))):
        a = suite.analyses[key].primary
        aq, ar = axes[r]
        if a.resid is None:
            for ax in (aq, ar):
                ax.text(0.5, 0.5, "model not fitted", ha="center", va="center", color=INK2, transform=ax.transAxes)
                ax.set_axis_off()
            continue
        res = a.resid.dropna()
        (osm, osr), _ = stats.probplot(res, dist="norm")
        aq.scatter(osm, osr, s=16, color=INK2, linewidth=0)
        aq.plot(osm, res.mean() + res.std() * osm, color=AXIS, linewidth=1, zorder=1)
        aq.set_xlabel("Theoretical normal quantile"); aq.set_ylabel("Residual")
        sh = stats.shapiro(res).pvalue if len(res) >= 3 else np.nan
        aq.set_title(f"{nm}: normal Q-Q (Shapiro p = {sh:.3f})", loc="left", fontsize=9.5, fontweight="bold")
        for p in ORDER:
            m = (a.patterns_resid == p).reindex(res.index).fillna(False)
            ar.scatter(a.fitted[res.index][m], res[m], s=22, color=COLORS[p], edgecolor=SURFACE, linewidth=1,
                       label=NAMES[p], zorder=3)
        ar.axhline(0, color=AXIS, linewidth=1, zorder=1)
        ar.set_xlabel("Fitted value"); ar.set_ylabel("Residual")
        ar.set_title(f"{nm}: residuals vs fitted", loc="left", fontsize=9.5, fontweight="bold")
        for ax in (aq, ar):
            _grid(ax, "both")
        rows.append(pd.DataFrame(dict(outcome=key, fitted=a.fitted[res.index], resid=res, pattern=a.patterns_resid[res.index])))
    fig.legend(handles=[Patch(facecolor=COLORS[p], label=NAMES[p]) for p in ORDER], loc="lower center", ncol=3,
               fontsize=8.5, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Model diagnostics (primary linear mixed models)", x=0.01, ha="left", fontsize=11, fontweight="bold")
    return fig, (pd.concat(rows) if rows else pd.DataFrame())


def f12_effects(suite):
    """Pairwise effect sizes (primary models) with 95% CI; filled = significant after Holm correction."""
    keys = [k for k in ("T_find", "E", "R") if suite.analyses[k].primary.ok]
    fig, ax = plt.subplots(figsize=(7.6, 1.2 + 1.35 * len(keys)))
    ypos, ylabels, rows, y = [], [], [], 0
    for key in keys:
        a = suite.analyses[key]
        pw = a.primary.pairwise
        unit = {"T_find": "ratio of geometric means", "E": "rate ratio", "R": "ratio of geometric means"}[key]
        ax.text(0.0, y, f"{a.spec.hypothesis}  {a.spec.label}  ({unit})" + ("  [decision uses Friedman]" if a.chosen == "fallback" else ""),
                transform=ax.get_yaxis_transform(), ha="left", va="center", fontsize=9, fontweight="bold", color=INK)
        y += 1
        for r in pw.itertuples():
            ax.plot([r.ci_low, r.ci_high], [y, y], color=INK2, linewidth=1.4, zorder=2)
            ax.scatter([r.effect], [y], s=52, facecolor=INK if r.significant_holm else SURFACE, edgecolor=INK,
                       linewidth=1.4, zorder=3)
            ax.text(1.02, y, f"{r.effect:.2f} [{r.ci_low:.2f}, {r.ci_high:.2f}]   p(Holm) = {r.p_holm:.3f}",
                    transform=ax.get_yaxis_transform(), va="center", fontsize=8, color=INK2)
            ypos.append(y); ylabels.append(r.contrast)
            rows.append(dict(outcome=key, contrast=r.contrast, effect=r.effect, ci_low=r.ci_low, ci_high=r.ci_high,
                             p_holm=r.p_holm, significant_holm=r.significant_holm))
            y += 1
        y += 0.6
    ax.axvline(1, color=AXIS, linewidth=1, zorder=1)
    ax.set_xscale("log"); ax.set_xticks([0.25, 0.5, 1, 2, 4]); ax.get_xaxis().set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks(ypos); ax.set_yticklabels(ylabels, fontsize=8.5)
    ax.set_ylim(y - 0.6, -0.9)             # inverted axis with headroom for the first group heading
    ax.set_xlabel("Effect size (1 = no difference); first pattern relative to second")
    _grid(ax, "x")
    ax.set_title("Pairwise pattern effects", loc="left", fontsize=11, fontweight="bold", pad=14)
    ax.text(0, 1.015, "Primary models, 95% CI. Filled dot: significant after Holm correction (3 contrasts per outcome).",
            transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom")
    fig.subplots_adjust(right=0.62)
    return fig, pd.DataFrame(rows)


def make_model_figures(suite, out_dir) -> dict[str, Path]:
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    paths = {}
    with plt.rc_context(RC):
        for name, fn in (("F11_model_diagnostics", f11_diagnostics), ("F12_pairwise_effects", f12_effects)):
            fig, data = fn(suite)
            fig.savefig(out / "figures" / f"{name}.png", dpi=200, bbox_inches="tight")
            fig.savefig(out / "figures" / f"{name}.svg", bbox_inches="tight")
            plt.close(fig)
            data.to_csv(out / "tables" / f"fig_data_{name}.csv", index=False)
            paths[name] = out / "figures" / f"{name}.png"
    return paths


def make_all_figures(prep, out_dir) -> dict[str, Path]:
    """`prep` is a pipeline.prepare.Prepared. Writes PNG + SVG to <out_dir>/figures and each figure's data to
    <out_dir>/tables/fig_data_<name>.csv. Returns {name: png path}."""
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    ds = prep.clean
    ctx = dict(trials=prep.trials, participants=ds.participants, events=ds.events, tree=ds.tree, tree_df=ds.tree_df)
    paths = {}
    with plt.rc_context(RC):
        for name, fn in FIGURES.items():
            fig, data = fn(**ctx)
            fig.savefig(out / "figures" / f"{name}.png", dpi=200, bbox_inches="tight")
            fig.savefig(out / "figures" / f"{name}.svg", bbox_inches="tight")
            plt.close(fig)
            data.to_csv(out / "tables" / f"fig_data_{name}.csv", index=False)
            paths[name] = out / "figures" / f"{name}.png"
    return paths

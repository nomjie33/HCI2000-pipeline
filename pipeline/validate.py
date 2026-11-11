"""Step 1: validate raw data. Each check returns pass/fail plus the offending rows.

Severity: "hard" failures make the derived numbers untrustworthy, so the pipeline stops;
"soft" failures are reported (and handled explicitly later) but do not stop the run.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import (
    EVENT_TYPES, EXPERIMENTAL_TRIALS, LATIN_SQUARE, MIN_SELECTIONS, N_PARTICIPANTS, PATTERNS,
    PER_SEQUENCE, PRACTICE_PREFIX, REQUIRED_COLUMNS, SEQ_RANGE, TERMINAL_EVENTS, TIME_LIMIT_MS,
)
from .io import Dataset


@dataclass
class CheckResult:
    name: str
    severity: str                  # "hard" | "soft"
    passed: bool
    message: str
    details: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def n_issues(self) -> int:
        return 0 if self.passed else len(self.details)


class ValidationError(Exception):
    pass


@dataclass
class ValidationReport:
    results: list[CheckResult]

    @property
    def hard_failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "hard"]

    @property
    def soft_failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "soft"]

    @property
    def failed_names(self) -> set[str]:
        return {r.name for r in self.results if not r.passed}

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [dict(check=r.name, severity=r.severity, passed=r.passed, n_issues=r.n_issues, message=r.message)
             for r in self.results]
        )

    def details_frame(self) -> pd.DataFrame:
        """All offending rows in one long table (check, then the row's columns as text)."""
        parts = []
        for r in self.results:
            if not r.passed and len(r.details):
                d = r.details.astype(str).copy()
                d.insert(0, "check", r.name)
                parts.append(d)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def raise_if_hard(self) -> None:
        if self.hard_failures:
            lines = [f"  - {r.name}: {r.message}" for r in self.hard_failures]
            raise ValidationError("Hard validation failures; fix the raw data before analysis:\n" + "\n".join(lines))


def _result(name, severity, bad: pd.DataFrame, ok_msg: str, bad_msg: str) -> CheckResult:
    if len(bad) == 0:
        return CheckResult(name, severity, True, ok_msg)
    return CheckResult(name, severity, False, f"{len(bad)} issue(s): {bad_msg}", bad.reset_index(drop=True))


def _is_practice(task_id: pd.Series) -> pd.Series:
    return task_id.str.startswith(PRACTICE_PREFIX)


def _trial_table(ev: pd.DataFrame) -> pd.DataFrame:
    cols = ["participant_id", "trial_id", "sequence", "block_position", "trial_order", "pattern",
            "task_id", "task_pair", "target_node", "min_selections"]
    return ev.drop_duplicates("trial_id")[cols].reset_index(drop=True)


# --- individual checks -------------------------------------------------------------------------
def check_schema(ds: Dataset) -> CheckResult:
    issues = []
    tables = {"events": ds.events, "ratings": ds.ratings, "participants": ds.participants,
              "exclusions": ds.exclusions, "tree": ds.tree_df, "tasks": ds.tasks}
    for name, df in tables.items():
        for col in REQUIRED_COLUMNS[name]:
            if col not in df.columns:
                issues.append((name, col, "missing column"))
    if not issues:                    # value checks only make sense once the columns exist
        ev = ds.events
        for col in ("block_position", "trial_order", "min_selections", "t_ms", "on_path"):
            for tid in ev.loc[ev[col].isna(), "trial_id"].unique():
                issues.append(("events", col, f"non-numeric or blank value in trial {tid}"))
        for col, allowed in (("pattern", PATTERNS), ("event_type", EVENT_TYPES), ("sequence", tuple(LATIN_SQUARE))):
            for v in sorted(set(ev[col]) - set(allowed)):
                issues.append(("events", col, f"unexpected value {v!r}"))
        for col in ("trial_id", "participant_id", "task_id", "target_node"):
            if (ev[col] == "").any():
                issues.append(("events", col, "blank value"))
        try:
            ds.tree
        except ValueError as e:
            issues.append(("tree", "parent_id", str(e)))
    return _result("schema", "hard", pd.DataFrame(issues, columns=["file", "column", "issue"]),
                   "required columns and values present", "required columns/values missing or invalid")


def check_one_start_and_terminal(ds: Dataset) -> list[CheckResult]:
    ev = ds.events
    g = ev.groupby("trial_id", sort=False)
    n_start = g["event_type"].apply(lambda s: (s == "start").sum())
    start_t = ev[ev.event_type == "start"].groupby("trial_id")["t_ms"].apply(lambda s: (s != 0).any())
    n_term = g["event_type"].apply(lambda s: s.isin(TERMINAL_EVENTS).sum())
    last_is_term = g["event_type"].apply(lambda s: s.iloc[-1] in TERMINAL_EVENTS)
    bad_start = pd.DataFrame({"trial_id": n_start.index[(n_start != 1)], "issue": "not exactly one start event"})
    bad_t0 = pd.DataFrame({"trial_id": start_t.index[start_t], "issue": "start event not at t_ms = 0"})
    bad_term = pd.DataFrame({
        "trial_id": n_term.index[(n_term != 1) | (~last_is_term.reindex(n_term.index))],
        "issue": "not exactly one terminal event, or terminal event is not the last row",
    })
    return [
        _result("one_start", "hard", pd.concat([bad_start, bad_t0], ignore_index=True),
                "every trial has one start at t = 0", "start event missing, repeated, or not at 0"),
        _result("one_terminal_event", "hard", bad_term,
                "every trial ends with exactly one target_reached/give_up/timeout",
                "terminal event missing, repeated, or not last"),
    ]


def check_time(ds: Dataset) -> list[CheckResult]:
    ev = ds.events
    back = ev.groupby("trial_id", sort=False)["t_ms"].apply(lambda s: (s.diff() < 0).any())
    bad_mono = pd.DataFrame({"trial_id": back.index[back], "issue": "t_ms decreases within the trial"})
    bad_lim = ev.loc[(ev.t_ms > TIME_LIMIT_MS) | (ev.t_ms < 0), ["trial_id", "t_ms", "event_type"]]
    return [
        _result("monotonic_time", "hard", bad_mono, "t_ms non-decreasing in every trial", "timestamps go backwards"),
        _result("time_limit", "hard", bad_lim, f"all events within 0-{TIME_LIMIT_MS} ms",
                f"events outside 0-{TIME_LIMIT_MS} ms"),
    ]


def check_nodes(ds: Dataset) -> CheckResult:
    ev, tree = ds.events, ds.tree
    rows = []
    for col, allow_blank in (("node_id", True), ("current_node_after", False), ("target_node", False)):
        vals = ev[col]
        bad = ev[~vals.map(lambda v: v in tree) & ~((vals == "") & allow_blank)]
        rows.append(bad.assign(column=col, value=bad[col])[["trial_id", "t_ms", "event_type", "column", "value"]])
    return _result("nodes_in_tree", "hard", pd.concat(rows, ignore_index=True),
                   "every node id exists in tree.csv", "node ids not found in tree.csv")


def check_tasks_and_min_selections(ds: Dataset) -> list[CheckResult]:
    trials = _trial_table(ds.events)
    t = trials.merge(ds.tasks.rename(columns={"target_node": "expected_target", "task_pair": "expected_pair"}),
                     on="task_id", how="left")
    bad_task = t[(t.expected_target != t.target_node) | (t.expected_pair != t.task_pair)]
    exp_min = trials.pattern.map(MIN_SELECTIONS)
    bad_min = trials[exp_min != trials.min_selections][["trial_id", "pattern", "min_selections"]]
    return [
        _result("targets_match_tasks", "hard", bad_task[["trial_id", "task_id", "target_node", "expected_target"]],
                "trial targets and pairs match tasks.csv", "target/pair differs from tasks.csv or task unknown"),
        _result("min_selections_match_pattern", "hard", bad_min,
                "min_selections is 2 for MM and 3 for DH/ND", "min_selections inconsistent with pattern"),
    ]


def check_design(ds: Dataset) -> list[CheckResult]:
    trials = _trial_table(ds.events)
    exp = trials[~_is_practice(trials.task_id)]
    pt = ds.participants

    all_ids = sorted(set(pt.participant_id) | set(exp.participant_id))
    per_p = exp.groupby("participant_id").size().reindex(all_ids, fill_value=0)
    bad_n = per_p[per_p != EXPERIMENTAL_TRIALS].rename("n_trials").reset_index()
    bad_n.columns = ["participant_id", "n_trials"]

    per_seq = pt.groupby("sequence").size().reindex(list(LATIN_SQUARE), fill_value=0)
    seq_issue = per_seq[per_seq != PER_SEQUENCE].rename("n_participants").reset_index()
    if len(pt) != N_PARTICIPANTS:
        seq_issue = pd.concat(
            [seq_issue, pd.DataFrame({"sequence": ["(all)"], "n_participants": [len(pt)]})], ignore_index=True)

    expected = {(s, b, pat, pair) for s, blocks in LATIN_SQUARE.items()
                for b, (pat, pair) in enumerate(blocks, start=1)}
    got = list(zip(exp.sequence, exp.block_position.astype(int), exp.pattern, exp.task_pair))
    bad_ls = exp[[g not in expected for g in got]][["trial_id", "sequence", "block_position", "pattern", "task_pair"]]

    ev_seq = ds.events.drop_duplicates("participant_id")[["participant_id", "sequence"]]
    m = ev_seq.merge(pt[["participant_id", "sequence"]], on="participant_id", how="outer",
                     suffixes=("_events", "_participants"), indicator=True)
    bad_part = m[(m._merge != "both") | (m.sequence_events != m.sequence_participants)].drop(columns="_merge")

    return [
        _result("trials_per_participant", "soft", bad_n, f"every participant has {EXPERIMENTAL_TRIALS} experimental trials",
                f"participants without exactly {EXPERIMENTAL_TRIALS} experimental trials"),
        _result("participants_per_sequence", "soft", seq_issue,
                f"{N_PARTICIPANTS} participants, {PER_SEQUENCE} per sequence", "sample size differs from the plan"),
        _result("latin_square", "soft", bad_ls, "pattern/pair per sequence and block match Table 3",
                "trials deviate from the Latin square"),
        _result("participants_match_events", "soft", bad_part, "participants.csv and events.csv agree on IDs and sequence",
                "participant IDs or sequences differ between files"),
    ]


def check_on_path(ds: Dataset) -> CheckResult:
    ev, tree = ds.events, ds.tree
    computed = [int(c in set(tree.path(t))) if (t in tree) else 0
                for c, t in zip(ev.current_node_after, ev.target_node)]
    bad = ev.assign(on_path_tree=computed)
    bad = bad[bad.on_path != bad.on_path_tree][["trial_id", "t_ms", "event_type", "current_node_after", "on_path", "on_path_tree"]]
    return _result("on_path_matches_tree", "soft", bad, "logged on_path equals tree-derived flag",
                   "logged on_path disagrees with the tree (the tree-derived value is used)")


def check_duplicates(ds: Dataset) -> CheckResult:
    ev = ds.events
    dup = ev[ev.duplicated(["trial_id", "t_ms", "event_type", "node_id", "current_node_after"], keep="first")]
    return _result("duplicate_rows", "soft", dup[["trial_id", "t_ms", "event_type", "node_id"]],
                   "no duplicate event rows", "duplicate event rows (the cleaning step drops them and logs it)")


def check_ratings(ds: Dataset) -> CheckResult:
    trials = _trial_table(ds.events)
    exp_trials = set(trials.loc[~_is_practice(trials.task_id), "trial_id"])
    r = ds.ratings
    issues = [(t, "no rating") for t in sorted(exp_trials - set(r.trial_id))]
    issues += [(t, "rating for unknown/practice trial") for t in sorted(set(r.trial_id) - exp_trials)]
    issues += [(t, "duplicate rating") for t in r.trial_id[r.trial_id.duplicated()].unique()]
    lo, hi = SEQ_RANGE
    issues += [(t, f"rating outside {lo}-{hi}") for t in r.trial_id[~r.difficulty_rating.between(lo, hi)]]
    return _result("ratings_complete", "soft", pd.DataFrame(issues, columns=["trial_id", "issue"]),
                   "one valid 1-7 rating per experimental trial", "missing, extra, duplicate or invalid ratings")


def check_rankings(ds: Dataset) -> CheckResult:
    pt = ds.participants
    ranks = pt[["rank_DH", "rank_MM", "rank_ND"]]
    ok = ranks.apply(lambda row: sorted(row.tolist()) == [1, 2, 3], axis=1)
    return _result("ranking_permutation", "soft", pt.loc[~ok, ["participant_id", "rank_DH", "rank_MM", "rank_ND"]],
                   "every preference ranking is a permutation of 1-3", "preference ranks are not 1,2,3")


def check_exclusions(ds: Dataset) -> CheckResult:
    unknown = ds.exclusions[~ds.exclusions.trial_id.isin(ds.events.trial_id)]
    blank = ds.exclusions[ds.exclusions.reason == ""]
    return _result("exclusions_valid", "soft", pd.concat([unknown, blank]).drop_duplicates(),
                   "every exclusion names a known trial and a reason", "exclusions with unknown trial or no reason")


# --- entry point -------------------------------------------------------------------------------
def validate(ds: Dataset) -> ValidationReport:
    """Run all checks. If the schema check fails nothing else can run, so only it is returned."""
    schema = check_schema(ds)
    if not schema.passed:
        return ValidationReport([schema])
    results = [schema]
    results += check_one_start_and_terminal(ds)
    results += check_time(ds)
    results.append(check_nodes(ds))
    results += check_tasks_and_min_selections(ds)
    results += check_design(ds)
    results.append(check_on_path(ds))
    results += [check_duplicates(ds), check_ratings(ds), check_rankings(ds), check_exclusions(ds)]
    return ValidationReport(results)

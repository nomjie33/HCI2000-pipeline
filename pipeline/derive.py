"""Step 3: derive E, R, T_find, T_clean per trial from the event log (proposal 3.2-3.3).

Definitions, with P* the root-to-target path in the tree:
  * selection  = a `select` event; it is an ERROR if the selected node is not on P*.
  * on path    = the current node after the action is a node of P* (recomputed from the tree here,
                 the logged on_path flag is not used).
  * error episode starts at the first error while on path, ends when the current node next returns
    to P*; an episode still open at the end of the trial ends at the trial end time.
  * E = number of error selections, R = sum of episode durations, T_find = time of the terminal event,
    T_clean = T_find - R. For give-up/timeout trials T_find is the trial end time and success = 0.
"""
from __future__ import annotations

import pandas as pd

from .config import TERMINAL_EVENTS
from .io import Dataset, Tree

BACK_ACTIONS = ("back", "collapse", "logo")


def compute_trial_metrics(events: pd.DataFrame, tree: Tree) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Needs columns: trial_id, target_node, t_ms, event_type, node_id, current_node_after (in time order).
    Returns (one row per trial, one row per error episode)."""
    trial_rows, ep_rows = [], []
    for tid, g in events.groupby("trial_id", sort=False):
        on_path = set(tree.path(g["target_node"].iloc[0]))
        E, R_ms, ep_start, ep_n = 0, 0, None, 0
        sel_nodes, n_back = [], 0
        end_reason, t_end = None, None
        for t, et, node, cur in zip(g.t_ms, g.event_type, g.node_id, g.current_node_after):
            t = int(t)
            if et == "select":
                sel_nodes.append(node)
                if node not in on_path:
                    E += 1
                    if ep_start is None:
                        ep_start = t
            elif et in BACK_ACTIONS:
                n_back += 1
            if ep_start is not None and cur in on_path:
                ep_n += 1
                ep_rows.append(dict(trial_id=tid, episode=ep_n, start_s=ep_start / 1000, end_s=t / 1000,
                                    duration_s=(t - ep_start) / 1000, open_at_end=False))
                R_ms += t - ep_start
                ep_start = None
            if et in TERMINAL_EVENTS:
                end_reason, t_end = TERMINAL_EVENTS[et], t
        if t_end is None:
            raise ValueError(f"trial {tid} has no terminal event (run validate() first)")
        if ep_start is not None:                                    # episode open at trial end
            ep_n += 1
            ep_rows.append(dict(trial_id=tid, episode=ep_n, start_s=ep_start / 1000, end_s=t_end / 1000,
                                duration_s=(t_end - ep_start) / 1000, open_at_end=True))
            R_ms += t_end - ep_start
        T_find, R = t_end / 1000, R_ms / 1000
        trial_rows.append(dict(
            trial_id=tid, t_end_s=T_find, end_reason=end_reason, success=int(end_reason == "target"),
            E=E, R=R, T_find=T_find, T_clean=T_find - R,
            n_selections=len(sel_nodes), n_back_actions=n_back, selection_path=" > ".join(sel_nodes),
        ))
    episodes = pd.DataFrame(ep_rows, columns=["trial_id", "episode", "start_s", "end_s", "duration_s", "open_at_end"])
    return pd.DataFrame(trial_rows), episodes


TRIAL_META = ["participant_id", "trial_id", "sequence", "block_position", "trial_order", "pattern",
              "task_id", "task_pair", "target_node", "min_selections"]
COVARIATES = ["age", "gender", "gov_familiarity", "used_reference_site"]


def derive_trials(ds: Dataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trial table with App. B fields (+ covariates) and the error-episode table, from CLEANED data."""
    metrics, episodes = compute_trial_metrics(ds.events, ds.tree)
    meta = ds.events.drop_duplicates("trial_id")[TRIAL_META]
    trials = meta.merge(metrics, on="trial_id", how="left")
    trials = trials.merge(ds.ratings[["trial_id", "difficulty_rating"]], on="trial_id", how="left")
    trials = trials.merge(ds.participants[["participant_id"] + COVARIATES], on="participant_id", how="left")
    trials["failure_type"] = trials.end_reason.where(trials.success == 0, "")
    return trials.sort_values(["participant_id", "trial_order"]).reset_index(drop=True), episodes

"""Step 2: clean. Only three things are ever removed, and every removal is written to the cleaning log:
exact duplicate event rows, practice trials, and trials excluded for a device/app fault (exclusions.csv).
No statistical outlier rule is used (proposal 4.7)."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .config import PRACTICE_PREFIX
from .io import Dataset

DUP_KEY = ["trial_id", "t_ms", "event_type", "node_id", "current_node_after"]
LOG_COLUMNS = ["step", "trial_id", "n_event_rows", "reason"]


def clean(ds: Dataset) -> tuple[Dataset, pd.DataFrame]:
    log: list[dict] = []
    ev, ratings = ds.events, ds.ratings

    dup = ev.duplicated(DUP_KEY, keep="first")
    for tid, n in ev[dup].groupby("trial_id").size().items():
        log.append(dict(step="duplicate_rows", trial_id=tid, n_event_rows=int(n),
                        reason="exact duplicate event row (logging artefact)"))
    ev = ev[~dup]

    is_practice = ev.task_id.str.startswith(PRACTICE_PREFIX)
    for tid, n in ev[is_practice].groupby("trial_id").size().items():
        log.append(dict(step="practice", trial_id=tid, n_event_rows=int(n), reason="practice trial, not analysed"))
    ev = ev[~is_practice]

    excl = dict(zip(ds.exclusions.trial_id, ds.exclusions.reason))
    for tid, n in ev[ev.trial_id.isin(excl)].groupby("trial_id").size().items():
        log.append(dict(step="exclusion", trial_id=tid, n_event_rows=int(n), reason=excl[tid]))
    ev = ev[~ev.trial_id.isin(excl)]

    kept = set(ev.trial_id)
    ratings = ratings[ratings.trial_id.isin(kept)]
    out = replace(ds, events=ev.reset_index(drop=True), ratings=ratings.reset_index(drop=True))
    return out, pd.DataFrame(log, columns=LOG_COLUMNS)

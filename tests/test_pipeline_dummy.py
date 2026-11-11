"""End-to-end checks on the synthetic datasets: derived values must equal the generator's ground truth,
and the validator must catch every fault injected into data/dummy_dirty."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.clean import clean
from pipeline.io import load_dataset
from pipeline.prepare import prepare
from pipeline.validate import ValidationError, validate

DUMMY = Path("data/dummy")
DIRTY = Path("data/dummy_dirty")


@pytest.fixture(scope="module")
def prepared():
    return prepare(DUMMY)


def test_clean_data_passes_all_checks(prepared):
    assert prepared.report.failed_names == set(), prepared.report.to_frame().query("not passed")


def test_derived_values_match_ground_truth(prepared):
    truth = pd.read_csv(DUMMY / "_ground_truth_trials.csv")
    t = prepared.trials.merge(truth, on="trial_id", suffixes=("", "_true"))
    assert len(t) == len(prepared.trials) == 89         # 15 x 6 trials minus 1 excluded
    assert (t.E == t.E_true).all()
    for col in ("R", "T_find", "T_clean"):
        assert np.allclose(t[col], t[f"{col}_true"]), col
    assert (t.end_reason == t.end_reason_true).all() and (t.success == t.success_true).all()


def test_cleaning_log_accounts_for_every_drop(prepared):
    log = prepared.cleaning_log
    assert set(log.step) == {"practice", "exclusion"}
    assert (log[log.step == "practice"].shape[0]) == 15
    assert log[log.step == "exclusion"].trial_id.tolist() == ["P07_T4"]
    assert not prepared.trials.trial_id.str.contains("PR").any()
    assert "P07_T4" not in set(prepared.trials.trial_id)


def test_trial_table_has_appendix_b_fields(prepared):
    needed = {"participant_id", "trial_id", "sequence", "block_position", "pattern", "task_id", "task_pair",
              "target_node", "min_selections", "t_end_s", "end_reason", "success", "E", "R", "T_find", "T_clean",
              "difficulty_rating"}
    assert needed <= set(prepared.trials.columns)
    assert (prepared.trials.groupby("participant_id").size() <= 6).all()
    assert prepared.trials.difficulty_rating.notna().all()
    assert np.allclose(prepared.trials.T_find, prepared.trials.T_clean + prepared.trials.R)   # Eq. 2


def test_logged_on_path_flags_agree_with_tree(prepared):
    assert "on_path_matches_tree" not in prepared.report.failed_names


def test_dirty_data_faults_are_caught():
    faults = pd.read_csv(DIRTY / "_injected_faults.csv")
    report = validate(load_dataset(DIRTY))
    missing = set(faults.expected_check) - report.failed_names
    assert not missing, f"validator missed: {missing}"
    severity = faults.set_index("expected_check").severity
    hard = {c for c in faults.expected_check if severity[c] == "hard"}
    assert hard <= {r.name for r in report.hard_failures}


def test_strict_prepare_refuses_dirty_data():
    with pytest.raises(ValidationError):
        prepare(DIRTY)


def test_cleaning_drops_duplicate_rows_on_dirty_data():
    ds = load_dataset(DIRTY)
    _, log = clean(ds)
    assert "duplicate_rows" in set(log.step)

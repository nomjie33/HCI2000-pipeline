"""Hand-built traces with known answers for the error-episode logic (proposal 3.3)."""
import pandas as pd
import pytest

from pipeline.derive import compute_trial_metrics
from pipeline.io import Tree

TREE = Tree(pd.DataFrame(
    [("ROOT", "", 0), ("C1", "ROOT", 1), ("C1.1", "C1", 2), ("C1.1.1", "C1.1", 3), ("C1.1.2", "C1.1", 3),
     ("C1.2", "C1", 2), ("C1.2.1", "C1.2", 3), ("C2", "ROOT", 1), ("C2.1", "C2", 2), ("C2.1.1", "C2.1", 3)],
    columns=["node_id", "parent_id", "level"]))
TARGET = "C1.1.2"          # P* = ROOT, C1, C1.1, C1.1.2


def trial(rows, tid="X"):
    """rows: (t_ms, event_type, node_id, current_node_after)"""
    df = pd.DataFrame(rows, columns=["t_ms", "event_type", "node_id", "current_node_after"])
    df["trial_id"], df["target_node"] = tid, TARGET
    return df


def metrics(rows):
    m, ep = compute_trial_metrics(trial(rows), TREE)
    return m.iloc[0], ep


def test_clean_trial_has_no_errors():
    m, ep = metrics([(0, "start", "", "ROOT"), (500, "menu_open", "", "ROOT"),
                     (2000, "select", "C1", "C1"), (4000, "select", "C1.1", "C1.1"),
                     (6000, "select", "C1.1.2", "C1.1.2"), (6000, "target_reached", "C1.1.2", "C1.1.2")])
    assert (m.E, m.R, m.T_find, m.T_clean, m.success, m.end_reason) == (0, 0, 6.0, 6.0, 1, "target")
    assert len(ep) == 0


def test_wrong_top_level_then_back():
    # DH: tap wrong L1 at 3 s (error), Back to root at 4.5 s -> episode of 1.5 s
    m, ep = metrics([(0, "start", "", "ROOT"), (3000, "select", "C2", "C2"), (4500, "back", "", "ROOT"),
                     (6000, "select", "C1", "C1"), (7000, "select", "C1.1", "C1.1"),
                     (8000, "select", "C1.1.2", "C1.1.2"), (8000, "target_reached", "C1.1.2", "C1.1.2")])
    assert m.E == 1 and m.R == pytest.approx(1.5) and m.T_find == 8.0 and m.T_clean == pytest.approx(6.5)
    assert ep.duration_s.tolist() == [1.5] and not ep.open_at_end.any()
    assert m.n_back_actions == 1 and m.selection_path == "C2 > C1 > C1.1 > C1.1.2"


def test_wrong_branch_two_selections_one_episode_back_lands_on_path():
    # right L1, wrong L2 (error, episode opens), wrong leaf (second error, same episode), Back, Back to C1 (on path)
    m, ep = metrics([(0, "start", "", "ROOT"), (1000, "select", "C1", "C1"),
                     (2000, "select", "C1.2", "C1.2"), (3000, "select", "C1.2.1", "C1.2.1"),
                     (4000, "back", "", "C1.2"), (5000, "back", "", "C1"),      # lands on P*: episode ends
                     (6000, "select", "C1.1", "C1.1"), (7000, "select", "C1.1.2", "C1.1.2"),
                     (7000, "target_reached", "C1.1.2", "C1.1.2")])
    assert m.E == 2 and m.R == pytest.approx(3.0)          # 2 s -> 5 s
    assert len(ep) == 1 and ep.start_s[0] == 2.0 and ep.end_s[0] == 5.0


def test_two_separate_episodes_sum():
    m, ep = metrics([(0, "start", "", "ROOT"), (1000, "select", "C2", "C2"), (2000, "back", "", "ROOT"),
                     (3000, "select", "C1", "C1"), (4000, "select", "C1.2", "C1.2"), (5500, "back", "", "C1"),
                     (6000, "select", "C1.1", "C1.1"), (7000, "select", "C1.1.2", "C1.1.2"),
                     (7000, "target_reached", "C1.1.2", "C1.1.2")])
    assert m.E == 2 and m.R == pytest.approx(1.0 + 1.5) and len(ep) == 2


def test_open_episode_at_timeout_ends_at_trial_end():
    m, ep = metrics([(0, "start", "", "ROOT"), (1000, "select", "C1", "C1"),
                     (100_000, "select", "C1.2", "C1.2"), (180_000, "timeout", "", "C1.2")])
    assert m.end_reason == "timeout" and m.success == 0 and m.T_find == 180.0
    assert m.E == 1 and m.R == pytest.approx(80.0) and m.T_clean == pytest.approx(100.0)
    assert ep.open_at_end.tolist() == [True]


def test_open_episode_at_give_up():
    m, _ = metrics([(0, "start", "", "ROOT"), (2000, "select", "C2", "C2"), (9000, "give_up", "", "C2")])
    assert m.end_reason == "give_up" and m.success == 0 and m.R == pytest.approx(7.0) and m.E == 1


def test_same_selection_that_returns_on_path_ends_episode():
    # ND: wrong L1 open, then tapping the correct L1 directly (no Back) returns to P*
    m, _ = metrics([(0, "start", "", "ROOT"), (1000, "select", "C2", "C2"), (2500, "select", "C1", "C1"),
                    (3500, "select", "C1.1", "C1.1"), (4500, "select", "C1.1.2", "C1.1.2"),
                    (4500, "target_reached", "C1.1.2", "C1.1.2")])
    assert m.E == 1 and m.R == pytest.approx(1.5)


def test_mega_menu_wrong_leaf_back_to_panel():
    # MM: right L1 panel, wrong leaf, Back returns to the L1 panel (on P*)
    m, _ = metrics([(0, "start", "", "ROOT"), (1000, "select", "C1", "C1"), (3000, "select", "C1.2.1", "C1.2.1"),
                    (4000, "back", "", "C1"), (6000, "select", "C1.1.2", "C1.1.2"),
                    (6000, "target_reached", "C1.1.2", "C1.1.2")])
    assert m.E == 1 and m.R == pytest.approx(1.0) and m.T_clean == pytest.approx(5.0)


def test_menu_actions_are_not_selections_or_errors():
    m, _ = metrics([(0, "start", "", "ROOT"), (500, "menu_open", "", "ROOT"), (900, "menu_close", "", "ROOT"),
                    (1500, "menu_open", "", "ROOT"), (2000, "select", "C1", "C1"),
                    (3000, "select", "C1.1", "C1.1"), (4000, "select", "C1.1.2", "C1.1.2"),
                    (4000, "target_reached", "C1.1.2", "C1.1.2")])
    assert m.E == 0 and m.n_selections == 3

import numpy as np
import pandas as pd
import pytest

from pipeline.describe import (describe_all, e_distribution, error_selections, errors_by_level, geomean,
                               path_efficiency, pattern_summary, seq_distribution)
from pipeline.plots import FIGURES, make_all_figures
from pipeline.prepare import prepare


@pytest.fixture(scope="module")
def prep():
    return prepare("data/dummy")


def test_geomean_ignores_nonpositive_and_empty():
    assert geomean([1, 100]) == pytest.approx(10)
    assert geomean([0, 4, 4]) == pytest.approx(4)
    assert np.isnan(geomean([]))


def test_pattern_summary_matches_manual_numbers(prep):
    t, s = prep.trials, pattern_summary(prep.trials).set_index("pattern")
    for p in ("DH", "MM", "ND"):
        d = t[t.pattern == p]
        ok = d[d.success == 1]
        assert s.loc[p, "n_trials"] == len(d) and s.loc[p, "n_success"] == len(ok)
        assert s.loc[p, "T_find_median"] == pytest.approx(ok.T_find.median())
        assert s.loc[p, "E_mean"] == pytest.approx(ok.E.mean())
        assert s.loc[p, "n_trials_E_ge1"] == int((ok.E >= 1).sum())
        assert s.loc[p, "n_give_up"] + s.loc[p, "n_timeout"] == len(d) - len(ok)


def test_distributions_are_complete(prep):
    assert np.allclose(e_distribution(prep.trials).sum(axis=1), 1.0)
    assert seq_distribution(prep.trials).values.sum() == prep.trials.difficulty_rating.notna().sum()


def test_error_selections_only_real_off_path_picks(prep):
    err = error_selections(prep.clean.events, prep.clean.tree, prep.trials)
    ok = prep.trials[prep.trials.success == 1]
    assert len(err) == ok.E.sum()                          # same count as the derived E on successful trials
    assert not err.node_id.str.startswith("PR").any()      # no practice-tree nodes in experimental trials
    lv = errors_by_level(err, prep.trials)
    assert lv.loc["MM", "L2"] == 0                          # mega-menu L2 headings are not selectable


def test_path_efficiency_excess_nonnegative(prep):
    pe = path_efficiency(prep.trials)
    assert (pe.mean_excess_selections >= 0).all()


def test_all_figures_and_tables_are_written(prep, tmp_path):
    paths = make_all_figures(prep, tmp_path)
    assert set(paths) == set(FIGURES)
    for name, png in paths.items():
        assert png.stat().st_size > 5_000
        assert png.with_suffix(".svg").exists()
        assert pd.read_csv(tmp_path / "tables" / f"fig_data_{name}.csv").shape[0] > 0
    tables = describe_all(prep, tmp_path)
    assert (tmp_path / "tables" / "desc_pattern_summary.csv").exists() and len(tables) == 10

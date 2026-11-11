import importlib.util
import warnings

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from pipeline.models import (ALPHA, PAT, SPECS, analyze, check_residuals, friedman_fallback, inference,
                             run_models)
from pipeline.plots import make_model_figures
from pipeline.prepare import prepare

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def prep():
    return prepare("data/dummy")


@pytest.fixture(scope="module")
def suite(prep):
    return run_models(prep)


# --- inference maths with hand-computed answers -------------------------------------------------
def test_inference_wald_and_contrasts_match_hand_calculation():
    mm, nd = f"{PAT}[T.MM]", f"{PAT}[T.ND]"
    params = pd.Series({mm: np.log(0.5), nd: np.log(2.0)})
    cov = pd.DataFrame([[0.04, 0.0], [0.0, 0.09]], index=[mm, nd], columns=[mm, nd])
    W, df, p, pw = inference(params, cov, exp=True)
    assert df == 2
    assert W == pytest.approx(np.log(0.5) ** 2 / 0.04 + np.log(2.0) ** 2 / 0.09)
    assert p == pytest.approx(stats.chi2.sf(W, 2))
    r = pw.set_index("contrast")
    assert r.loc["MM vs DH", "effect"] == pytest.approx(0.5)
    assert r.loc["ND vs DH", "effect"] == pytest.approx(2.0)
    assert r.loc["ND vs MM", "effect"] == pytest.approx(4.0)                  # exp(log2 - log0.5)
    se = np.sqrt(0.04 + 0.09)                                                 # independent coefficients
    assert r.loc["ND vs MM", "ci_low"] == pytest.approx(4.0 * np.exp(-1.96 * se), rel=1e-3)
    z = np.log(0.5) / 0.2
    assert r.loc["MM vs DH", "p_raw"] == pytest.approx(2 * stats.norm.sf(abs(z)))
    assert (pw.p_holm >= pw.p_raw - 1e-12).all() and (pw.p_holm <= 1).all()   # Holm never lowers a p-value


def test_inference_difference_scale_for_ratings():
    mm, nd = f"{PAT}[T.MM]", f"{PAT}[T.ND]"
    _, _, _, pw = inference(pd.Series({mm: 0.6, nd: 0.2}), pd.DataFrame(np.eye(2) * 0.01, index=[mm, nd], columns=[mm, nd]), exp=False)
    assert pw.set_index("contrast").loc["ND vs MM", "effect"] == pytest.approx(-0.4)


# --- fallback rule and Friedman -----------------------------------------------------------------
def test_residual_check_flags_only_clear_violations():
    rng = np.random.default_rng(0)
    groups = pd.Series(np.tile(["DH", "MM", "ND"], 30))
    ok = pd.Series(rng.normal(0, 1, 90))
    assert check_residuals(ok, groups) == []
    skewed = pd.Series(np.exp(rng.normal(0, 1.5, 90)))
    assert any("non-normal" in r for r in check_residuals(skewed, groups))
    unequal = pd.Series(np.concatenate([rng.normal(0, 0.2, 30), rng.normal(0, 0.2, 30), rng.normal(0, 3.0, 30)]))
    blocks = pd.Series(np.repeat(["DH", "MM", "ND"], 30))        # matches how `unequal` was built
    assert any("spread" in r for r in check_residuals(unequal, blocks))


def test_friedman_perfect_agreement():
    tab = pd.DataFrame({"DH": [1, 2, 3, 4, 5, 6.0], "MM": [2, 3, 4, 5, 6, 7.0], "ND": [3, 4, 5, 6, 7, 8.0]})
    fb = friedman_fallback(tab, log_ratio=False)
    assert fb.ok and fb.chi2 == pytest.approx(12.0) and fb.p == pytest.approx(np.exp(-6))
    assert fb.kendall_w == pytest.approx(1.0)
    assert fb.pairwise.set_index("contrast").loc["MM vs DH", "effect"] == pytest.approx(1.0)   # median paired difference


def test_friedman_needs_enough_complete_participants():
    tab = pd.DataFrame({"DH": [1.0, 2.0, np.nan], "MM": [2.0, 3.0, 4.0], "ND": [3.0, 4.0, 5.0]})
    assert not friedman_fallback(tab, log_ratio=False).ok


# --- on the dummy data --------------------------------------------------------------------------
def test_suite_covers_all_outcomes_and_writes_tables(suite, tmp_path):
    assert set(suite.analyses) == set(SPECS)
    d = suite.write(tmp_path)
    for f in ("model_summary.csv", "model_pairwise.csv", "model_sensitivity.csv", "model_preference.csv"):
        assert (d / f).exists()
    assert len(suite.sensitivity) == 10                       # 3 outcomes x (primary + 2 variants) + Cox
    paths = make_model_figures(suite, tmp_path)
    assert all(p.stat().st_size > 5_000 for p in paths.values())


def test_complete_separation_switches_to_fallback(suite):
    a = suite.analyses["success"]                             # dummy: every ND trial succeeded
    assert not a.primary.ok and "separation" in a.primary.notes[0]
    assert a.flagged and a.chosen == "fallback" and a.fallback.ok


def test_decision_p_comes_from_the_chosen_source(suite):
    for a in suite.analyses.values():
        expected = a.primary.omnibus_p if a.chosen == "primary" else a.fallback.p
        assert a.p_chosen == expected or (np.isnan(expected) and np.isnan(a.p_chosen))
        assert a.significant == (a.p_chosen < ALPHA)


def test_effect_ratio_directions_match_cell_means(prep, suite):
    s = prep.trials[prep.trials.success == 1]
    gm = s.groupby("pattern").T_find.apply(lambda x: np.exp(np.log(x).mean()))
    r = suite.analyses["T_find"].primary.pairwise.set_index("contrast")
    assert (r.loc["MM vs DH", "effect"] < 1) == (gm["MM"] < gm["DH"])
    assert (r.loc["ND vs DH", "effect"] > 1) == (gm["ND"] > gm["DH"])


# --- recovery of planted effects on a larger simulated sample -----------------------------------
@pytest.fixture(scope="module")
def big_suite(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("make_dummy_data", "scripts/make_dummy_data.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    out = tmp_path_factory.mktemp("big")
    tree, tasks, ev, rt, pt, ex, truth = gen.simulate(60, 11)
    gen.write(out, tree, tasks, ev, rt, pt, ex, truth)
    return run_models(prepare(out))


def test_planted_effects_are_recovered_with_more_data(big_suite):
    h1 = big_suite.analyses["T_find"].primary
    assert h1.ok and h1.omnibus_p < ALPHA
    r = h1.pairwise.set_index("contrast")
    assert r.loc["MM vs DH", "effect"] < 1 < r.loc["ND vs DH", "effect"]           # planted: MM fastest, ND slowest
    assert r.loc["ND vs MM", "significant_holm"]
    h2 = big_suite.analyses["E"].primary.pairwise.set_index("contrast")
    assert h2.loc["ND vs MM", "effect"] > 1 and h2.loc["ND vs MM", "significant_holm"]   # planted: ND most errors

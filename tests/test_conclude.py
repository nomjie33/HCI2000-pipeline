import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from pipeline.conclude import (contrast_sentence, fmt_p, hypothesis_decisions, limitations, mechanism, md_table,
                               results_draft, significant_contrasts)
from pipeline.describe import successful
from pipeline.models import run_models
from pipeline.prepare import prepare
from pipeline.run import run_all


@pytest.fixture(scope="module")
def prep():
    return prepare("data/dummy")


@pytest.fixture(scope="module")
def suite(prep):
    return run_models(prep)


def test_p_value_formatting():
    assert fmt_p(0.0004) == "p < .001"
    assert fmt_p(0.0152) == "p = .015"
    assert fmt_p(1.0) == "p = 1.000"
    assert fmt_p(float("nan")) == "p = n/a"


def test_decisions_follow_the_rule(suite):
    d = hypothesis_decisions(suite).set_index("hypothesis")
    assert list(d.index) == ["H1", "H2", "H3"]
    for h, key in (("H1", "T_find"), ("H2", "E"), ("H3", "R")):
        a = suite.analyses[key]
        assert d.loc[h, "reject_null"] == (a.p_chosen < 0.05)
        assert d.loc[h, "decision"] == (f"Reject {h}" if a.p_chosen < 0.05 else f"Fail to reject {h}")


def test_pairwise_only_after_significant_omnibus(suite):
    for a in suite.analyses.values():
        sc = significant_contrasts(a)
        if not a.significant:
            assert len(sc) == 0
        assert sc.significant_holm.all() if len(sc) else True


def test_mechanism_decomposition_is_exact(prep, suite):
    tab, verdict = mechanism(prep, suite)
    assert np.allclose(tab.delta_T_find, tab.delta_T_clean + tab.delta_R)        # Eq. 2 on mean differences
    assert verdict and "recovery" in verdict or "clean navigation" in verdict or "No pattern difference" in verdict


def test_contrast_sentences_use_plain_language(suite):
    a = suite.analyses["T_find"]
    row = pd.Series(dict(contrast="MM vs DH", effect=0.77, ci_low=0.64, ci_high=0.93, p_holm=0.015))
    s = contrast_sentence("T_find", row, a)
    assert "Mega-menu" in s and "23% shorter" in s and "Deep hierarchical" in s and "Holm-adjusted p = .015" in s
    big = pd.Series(dict(contrast="ND vs MM", effect=2.6, ci_low=1.4, ci_high=4.9, p_holm=0.008))
    assert "2.6 times as many errors as Mega-menu" in contrast_sentence("E", big, suite.analyses["E"])


def test_draft_text_contains_numbers_from_the_models_and_a_synthetic_banner(prep, suite):
    text = results_draft(prep, suite)
    assert "SYNTHETIC DATA" in text                                    # data/dummy is flagged automatically
    a = suite.analyses["T_find"]
    assert f"{a.primary.omnibus_stat:.2f}" in text
    assert "### H1" in text and "### H2" in text and "### H3" in text
    assert "H10" not in text and "H20" not in text                     # H1-H3 are the nulls (no 'H10')
    assert "fail to reject" in text.lower() or "reject the null hypothesis" in text.lower()


def test_limitations_checklist_has_data_driven_and_fixed_items(prep, suite):
    lim = limitations(prep, suite)
    items = set(lim.item)
    assert {"Sample size", "Failed trials", "Block position and task pair", "Generalisability"} <= items
    assert set(lim.status) <= {"flag", "note"}
    fails = lim[lim.item == "Failed trials"].detail.iloc[0]
    assert str(int((prep.trials.success == 0).sum())) in fails or "0" in fails


def test_md_table_renders():
    t = md_table(pd.DataFrame({"a": [1, 2], "b": [0.5, np.nan]}))
    assert t.splitlines()[0] == "| a | b |" and "| 1 | 0.50 |" in t


def test_run_all_writes_every_output(tmp_path):
    res = run_all("data/dummy", tmp_path)
    for rel in ("tables/trials.csv", "tables/desc_pattern_summary.csv", "tables/model_summary.csv",
                "tables/hypothesis_decisions.csv", "tables/limitations_checklist.csv", "tables/mechanism_decomposition.csv",
                "figures/F1_tfind_by_pattern.png", "figures/F12_pairwise_effects.png", "results_draft.md"):
        assert (tmp_path / rel).exists(), rel
    assert len(res.decisions) == 3


def test_command_line_runs_clean_data_and_refuses_dirty_data(tmp_path):
    ok = subprocess.run([sys.executable, "scripts/run_pipeline.py", "--data-dir", "data/dummy", "--out", str(tmp_path / "ok")],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "Hypothesis decisions" in ok.stdout
    bad = subprocess.run([sys.executable, "scripts/run_pipeline.py", "--data-dir", "data/dummy_dirty", "--out", str(tmp_path / "bad")],
                         capture_output=True, text=True)
    assert bad.returncode == 1 and "Hard validation failures" in bad.stderr
    assert not (tmp_path / "bad").exists()                             # nothing is analysed or written

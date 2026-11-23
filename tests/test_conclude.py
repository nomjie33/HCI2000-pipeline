import numpy as np
import pandas as pd

from pipeline.conclude import fmt_p, md_table


def test_p_value_formatting():
    assert fmt_p(0.0004) == "p < .001"
    assert fmt_p(0.0152) == "p = .015"
    assert fmt_p(1.0) == "p = 1.000"
    assert fmt_p(float("nan")) == "p = n/a"


def test_md_table_renders():
    t = md_table(pd.DataFrame({"a": [1, 2], "b": [0.5, np.nan]}))
    assert t.splitlines()[0] == "| a | b |" and "| 1 | 0.50 |" in t

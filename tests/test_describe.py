import numpy as np
import pytest

from pipeline.describe import geomean


def test_geomean_ignores_nonpositive_and_empty():
    assert geomean([1, 100]) == pytest.approx(10)
    assert geomean([0, 4, 4]) == pytest.approx(4)
    assert np.isnan(geomean([]))

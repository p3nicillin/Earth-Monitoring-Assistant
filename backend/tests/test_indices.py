import numpy as np
import pytest

from app.analysis.indices import ndvi, threshold_change


def test_ndvi_is_bounded_and_masks_zero_denominator() -> None:
    result = ndvi(np.array([0.8, 0.0, 0.1]), np.array([0.2, 0.0, 0.3]))
    assert result[0] == pytest.approx(0.6)
    assert np.isnan(result[1])
    assert result[2] == pytest.approx(-0.5)


def test_threshold_change_respects_valid_mask() -> None:
    before = np.array([0.1, 0.5, np.nan])
    after = np.array([0.5, 0.8, 0.9])
    result = threshold_change(
        before, after, minimum_absolute_change=0.25, valid_mask=np.array([True, False, True])
    )
    assert result.tolist() == [True, False, False]


def test_threshold_change_rejects_different_shapes() -> None:
    with pytest.raises(ValueError, match="same shape"):
        threshold_change(np.ones(2), np.ones(3), minimum_absolute_change=0.1)

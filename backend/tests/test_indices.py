import numpy as np
import pytest

from app.analysis.indices import (
    INDEX_REGISTRY,
    compute_index,
    delta_nbr,
    evi,
    mndwi,
    msavi,
    ndvi,
    savi,
    threshold_change,
)


def test_ndvi_is_bounded_and_masks_zero_denominator() -> None:
    result = ndvi(np.array([0.8, 0.0, 0.1]), np.array([0.2, 0.0, 0.3]))
    assert result[0] == pytest.approx(0.6)
    assert np.isnan(result[1])
    assert result[2] == pytest.approx(-0.5)


def test_extended_indices_are_vectorized_and_finite() -> None:
    nir = np.array([0.8, 0.5], dtype=np.float32)
    red = np.array([0.2, 0.3], dtype=np.float32)
    blue = np.array([0.1, 0.2], dtype=np.float32)
    green = np.array([0.3, 0.4], dtype=np.float32)
    swir = np.array([0.2, 0.6], dtype=np.float32)
    assert np.all(np.isfinite(evi(nir, red, blue)))
    assert np.all(np.isfinite(savi(nir, red)))
    assert np.all(np.isfinite(msavi(nir, red)))
    assert mndwi(green, swir).shape == nir.shape


def test_registry_enforces_band_contracts() -> None:
    assert {"ndvi", "evi", "mndwi", "ndmi", "ndbi", "nbr2"} <= INDEX_REGISTRY.keys()
    result = compute_index("ndvi", {"nir": np.array([0.8]), "red": np.array([0.2])})
    assert result[0] == pytest.approx(0.6)
    with pytest.raises(ValueError, match="Missing bands"):
        compute_index("evi", {"nir": np.array([0.8]), "red": np.array([0.2])})
    with pytest.raises(ValueError, match="Unknown"):
        compute_index("not-an-index", {})


def test_delta_nbr_preserves_nodata() -> None:
    result = delta_nbr(np.array([0.7, np.nan]), np.array([0.2, 0.1]))
    assert result[0] == pytest.approx(0.5)
    assert np.isnan(result[1])


def test_threshold_change_respects_valid_mask() -> None:
    before = np.array([0.1, 0.5, np.nan])
    after = np.array([0.5, 0.8, 0.9])
    result = threshold_change(
        before, after, minimum_absolute_change=0.25, valid_mask=np.array([True, False, True])
    )
    assert result.tolist() == [True, False, False]


def test_spectral_operations_reject_misaligned_inputs() -> None:
    with pytest.raises(ValueError, match="same shape"):
        ndvi(np.ones(2), np.ones(3))
    with pytest.raises(ValueError, match="same shape"):
        threshold_change(np.ones(2), np.ones(3), minimum_absolute_change=0.1)
    with pytest.raises(ValueError, match="non-negative"):
        threshold_change(np.ones(2), np.ones(2), minimum_absolute_change=-0.1)

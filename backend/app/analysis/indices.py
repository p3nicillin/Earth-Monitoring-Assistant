from typing import cast

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.floating]


def normalized_difference(a: FloatArray, b: FloatArray) -> FloatArray:
    """Compute a bounded normalized-difference index while masking zero denominators."""
    a_float = np.asarray(a, dtype=np.float32)
    b_float = np.asarray(b, dtype=np.float32)
    denominator = a_float + b_float
    return cast(
        FloatArray,
        np.divide(
            a_float - b_float,
            denominator,
            out=np.full_like(denominator, np.nan),
            where=np.abs(denominator) > 1e-8,
        ),
    )


def ndvi(nir: FloatArray, red: FloatArray) -> FloatArray:
    """Normalized Difference Vegetation Index."""
    return normalized_difference(nir, red)


def ndwi(green: FloatArray, nir: FloatArray) -> FloatArray:
    """McFeeters Normalized Difference Water Index."""
    return normalized_difference(green, nir)


def nbr(nir: FloatArray, swir2: FloatArray) -> FloatArray:
    """Normalized Burn Ratio."""
    return normalized_difference(nir, swir2)


def threshold_change(
    before: FloatArray,
    after: FloatArray,
    *,
    minimum_absolute_change: float,
    valid_mask: npt.NDArray[np.bool_] | None = None,
) -> npt.NDArray[np.bool_]:
    """Return a mask only where both acquisitions are finite and the delta is significant."""
    before_array = np.asarray(before, dtype=np.float32)
    after_array = np.asarray(after, dtype=np.float32)
    if before_array.shape != after_array.shape:
        raise ValueError("Before and after arrays must have the same shape")
    mask = np.isfinite(before_array) & np.isfinite(after_array)
    if valid_mask is not None:
        if valid_mask.shape != mask.shape:
            raise ValueError("valid_mask must have the same shape as the inputs")
        mask &= valid_mask
    return mask & (np.abs(after_array - before_array) >= minimum_absolute_change)

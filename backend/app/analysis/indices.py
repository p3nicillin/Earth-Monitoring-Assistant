from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.floating]
IndexFunction = Callable[..., FloatArray]


def _float_arrays(*arrays: FloatArray) -> tuple[FloatArray, ...]:
    converted = tuple(np.asarray(array, dtype=np.float32) for array in arrays)
    if not converted or any(array.shape != converted[0].shape for array in converted[1:]):
        raise ValueError("All spectral bands must have the same shape")
    return converted


def _safe_ratio(numerator: FloatArray, denominator: FloatArray) -> FloatArray:
    numerator, denominator = _float_arrays(numerator, denominator)
    valid = np.isfinite(numerator) & np.isfinite(denominator) & (np.abs(denominator) > 1e-8)
    return cast(
        FloatArray,
        np.divide(
            numerator,
            denominator,
            out=np.full_like(denominator, np.nan),
            where=valid,
        ),
    )


def normalized_difference(a: FloatArray, b: FloatArray) -> FloatArray:
    """Compute (a-b)/(a+b), preserving nodata as NaN and rejecting misaligned bands."""
    a_float, b_float = _float_arrays(a, b)
    return _safe_ratio(a_float - b_float, a_float + b_float)


def ndvi(nir: FloatArray, red: FloatArray) -> FloatArray:
    """Normalized Difference Vegetation Index (Rouse et al., 1974)."""
    return normalized_difference(nir, red)


def evi(
    nir: FloatArray,
    red: FloatArray,
    blue: FloatArray,
    *,
    gain: float = 2.5,
    c1: float = 6.0,
    c2: float = 7.5,
    canopy_background: float = 1.0,
) -> FloatArray:
    """Enhanced Vegetation Index using the MODIS coefficient convention (Huete et al., 2002)."""
    nir, red, blue = _float_arrays(nir, red, blue)
    return _safe_ratio(
        gain * (nir - red),
        nir + c1 * red - c2 * blue + canopy_background,
    )


def savi(nir: FloatArray, red: FloatArray, *, soil_adjustment: float = 0.5) -> FloatArray:
    """Soil Adjusted Vegetation Index (Huete, 1988); reflectance inputs are unitless."""
    nir, red = _float_arrays(nir, red)
    return _safe_ratio((1 + soil_adjustment) * (nir - red), nir + red + soil_adjustment)


def msavi(nir: FloatArray, red: FloatArray) -> FloatArray:
    """Modified Soil Adjusted Vegetation Index 2 (Qi et al., 1994)."""
    nir, red = _float_arrays(nir, red)
    discriminant = (2 * nir + 1) ** 2 - 8 * (nir - red)
    valid = np.isfinite(nir) & np.isfinite(red) & (discriminant >= 0)
    result = np.full_like(nir, np.nan)
    result[valid] = (2 * nir[valid] + 1 - np.sqrt(discriminant[valid])) / 2
    return result


def ndwi(green: FloatArray, nir: FloatArray) -> FloatArray:
    """McFeeters Normalized Difference Water Index (1996)."""
    return normalized_difference(green, nir)


def mndwi(green: FloatArray, swir1: FloatArray) -> FloatArray:
    """Modified NDWI for open-water enhancement (Xu, 2006)."""
    return normalized_difference(green, swir1)


def ndmi(nir: FloatArray, swir1: FloatArray) -> FloatArray:
    """Normalized Difference Moisture Index (Gao, 1996)."""
    return normalized_difference(nir, swir1)


def ndbi(swir1: FloatArray, nir: FloatArray) -> FloatArray:
    """Normalized Difference Built-up Index (Zha et al., 2003)."""
    return normalized_difference(swir1, nir)


def ndre(nir: FloatArray, red_edge: FloatArray) -> FloatArray:
    """Normalized Difference Red Edge index for chlorophyll-sensitive vegetation response."""
    return normalized_difference(nir, red_edge)


def bsi(swir1: FloatArray, red: FloatArray, nir: FloatArray, blue: FloatArray) -> FloatArray:
    """Bare Soil Index using the common SWIR1/red versus NIR/blue formulation."""
    swir1, red, nir, blue = _float_arrays(swir1, red, nir, blue)
    return _safe_ratio((swir1 + red) - (nir + blue), (swir1 + red) + (nir + blue))


def gci(nir: FloatArray, green: FloatArray) -> FloatArray:
    """Green Chlorophyll Index (Gitelson et al., 2003)."""
    nir, green = _float_arrays(nir, green)
    return _safe_ratio(nir, green) - 1


def arvi(nir: FloatArray, red: FloatArray, blue: FloatArray) -> FloatArray:
    """Atmospherically Resistant Vegetation Index (Kaufman and Tanre, 1992)."""
    nir, red, blue = _float_arrays(nir, red, blue)
    corrected_red = 2 * red - blue
    return _safe_ratio(nir - corrected_red, nir + corrected_red)


def vari(green: FloatArray, red: FloatArray, blue: FloatArray) -> FloatArray:
    """Visible Atmospherically Resistant Index (Gitelson et al., 2002)."""
    green, red, blue = _float_arrays(green, red, blue)
    return _safe_ratio(green - red, green + red - blue)


def nbr(nir: FloatArray, swir2: FloatArray) -> FloatArray:
    """Normalized Burn Ratio (Key and Benson, 2006)."""
    return normalized_difference(nir, swir2)


def nbr2(swir1: FloatArray, swir2: FloatArray) -> FloatArray:
    """Normalized Burn Ratio 2 for post-fire moisture response."""
    return normalized_difference(swir1, swir2)


def delta_nbr(before_nbr: FloatArray, after_nbr: FloatArray) -> FloatArray:
    """Differenced NBR; positive values conventionally indicate burn-related decline."""
    before, after = _float_arrays(before_nbr, after_nbr)
    result = before - after
    result[~(np.isfinite(before) & np.isfinite(after))] = np.nan
    return cast(FloatArray, result)


@dataclass(frozen=True)
class IndexDefinition:
    name: str
    bands: tuple[str, ...]
    function: IndexFunction
    expected_range: tuple[float, float] | None
    reference: str


INDEX_REGISTRY: dict[str, IndexDefinition] = {
    definition.name: definition
    for definition in (
        IndexDefinition("ndvi", ("nir", "red"), ndvi, (-1, 1), "Rouse et al. 1974"),
        IndexDefinition("evi", ("nir", "red", "blue"), evi, None, "Huete et al. 2002"),
        IndexDefinition("savi", ("nir", "red"), savi, None, "Huete 1988"),
        IndexDefinition("msavi", ("nir", "red"), msavi, None, "Qi et al. 1994"),
        IndexDefinition("ndwi", ("green", "nir"), ndwi, (-1, 1), "McFeeters 1996"),
        IndexDefinition("mndwi", ("green", "swir1"), mndwi, (-1, 1), "Xu 2006"),
        IndexDefinition("ndmi", ("nir", "swir1"), ndmi, (-1, 1), "Gao 1996"),
        IndexDefinition("ndbi", ("swir1", "nir"), ndbi, (-1, 1), "Zha et al. 2003"),
        IndexDefinition("ndre", ("nir", "red_edge"), ndre, (-1, 1), "Barnes et al. 2000"),
        IndexDefinition(
            "bsi", ("swir1", "red", "nir", "blue"), bsi, (-1, 1), "Rikimaru et al. 2002"
        ),
        IndexDefinition("gci", ("nir", "green"), gci, None, "Gitelson et al. 2003"),
        IndexDefinition("arvi", ("nir", "red", "blue"), arvi, (-1, 1), "Kaufman and Tanre 1992"),
        IndexDefinition("vari", ("green", "red", "blue"), vari, None, "Gitelson et al. 2002"),
        IndexDefinition("nbr", ("nir", "swir2"), nbr, (-1, 1), "Key and Benson 2006"),
        IndexDefinition(
            "nbr2", ("swir1", "swir2"), nbr2, (-1, 1), "USGS Landsat index specification"
        ),
    )
}


def compute_index(name: str, bands: Mapping[str, FloatArray]) -> FloatArray:
    """Compute a registered index and fail explicitly when required bands are unavailable."""
    try:
        definition = INDEX_REGISTRY[name.lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown spectral index: {name}") from exc
    missing = [band for band in definition.bands if band not in bands]
    if missing:
        raise ValueError(f"Missing bands for {definition.name}: {', '.join(missing)}")
    return definition.function(*(bands[band] for band in definition.bands))


def threshold_change(
    before: FloatArray,
    after: FloatArray,
    *,
    minimum_absolute_change: float,
    valid_mask: npt.NDArray[np.bool_] | None = None,
) -> npt.NDArray[np.bool_]:
    """Return a mask only where both acquisitions are finite and the delta is significant."""
    if minimum_absolute_change < 0:
        raise ValueError("minimum_absolute_change must be non-negative")
    before_array, after_array = _float_arrays(before, after)
    mask = np.isfinite(before_array) & np.isfinite(after_array)
    if valid_mask is not None:
        if valid_mask.shape != mask.shape:
            raise ValueError("valid_mask must have the same shape as the inputs")
        mask &= valid_mask
    return mask & (np.abs(after_array - before_array) >= minimum_absolute_change)

# Scientific methods and validation contract

## Scope

The current analysis package provides vectorized spectral-index and raster-alignment primitives.
They are scientific building blocks, not operational detectors. An index threshold becomes a
detection only after sensor-specific calibration, cloud and shadow masking, co-registration,
regional/seasonal validation, uncertainty analysis, and an approved model card.

## Input contract

- Inputs are co-registered, same-shape arrays of surface reflectance unless a method explicitly
  states otherwise.
- Reflectance values should be scaled to a consistent unitless range before combining bands.
- NaN and explicit nodata pixels are excluded. Zero or non-finite denominators produce NaN.
- Raster pairs must match CRS, width, height, and all six affine coefficients. The validation layer
  rejects singular transforms and nodata values that cannot be represented by the declared dtype.
- Sensor band names are semantic. Provider adapters are responsible for mapping physical bands to
  `blue`, `green`, `red`, `red_edge`, `nir`, `swir1`, and `swir2` after checking spectral response.

## Implemented indices

| Index | Formula | Required bands | Principal use | Key limitation |
| --- | --- | --- | --- | --- |
| NDVI | `(NIR-Red)/(NIR+Red)` | NIR, red | Vegetation greenness | Saturates in dense canopy; soil/atmosphere sensitive |
| EVI | `G(NIR-Red)/(NIR+C1*Red-C2*Blue+L)` | NIR, red, blue | High-biomass vegetation | Coefficients assume MODIS convention and scaled reflectance |
| SAVI | `(1+L)(NIR-Red)/(NIR+Red+L)` | NIR, red | Sparse vegetation | Soil adjustment must match canopy conditions |
| MSAVI2 | Qi et al. quadratic form | NIR, red | Sparse vegetation | Negative discriminants are invalid and masked |
| NDWI | `(Green-NIR)/(Green+NIR)` | green, NIR | Open water | Built surfaces can confuse response |
| MNDWI | `(Green-SWIR1)/(Green+SWIR1)` | green, SWIR1 | Open water in built areas | Turbidity and shadows remain confounders |
| NDMI | `(NIR-SWIR1)/(NIR+SWIR1)` | NIR, SWIR1 | Canopy moisture | Not a direct volumetric-water measurement |
| NDBI | `(SWIR1-NIR)/(SWIR1+NIR)` | SWIR1, NIR | Built-up response | Bare soil often overlaps built surfaces |
| NDRE | `(NIR-RedEdge)/(NIR+RedEdge)` | NIR, red edge | Chlorophyll/crop condition | Sensor-specific red-edge response |
| BSI | `((SWIR1+Red)-(NIR+Blue))/sum` | SWIR1, red, NIR, blue | Bare soil | Sensitive to atmospheric and moisture variation |
| GCI | `NIR/Green-1` | NIR, green | Chlorophyll response | Requires radiometric consistency |
| ARVI | `(NIR-(2Red-Blue))/(NIR+(2Red-Blue))` | NIR, red, blue | Atmosphere-resistant vegetation | Residual aerosol effects remain |
| VARI | `(Green-Red)/(Green+Red-Blue)` | green, red, blue | Visible vegetation | Illumination and camera response sensitive |
| NBR | `(NIR-SWIR2)/(NIR+SWIR2)` | NIR, SWIR2 | Burn response | Fire severity requires pre/post calibration |
| NBR2 | `(SWIR1-SWIR2)/(SWIR1+SWIR2)` | SWIR1, SWIR2 | Post-fire moisture | Not interchangeable across sensors without validation |

`delta_nbr` uses the conventional `before NBR - after NBR` sign. Severity classes are deliberately
not embedded because published thresholds are ecosystem, sensor, season, and preprocessing
dependent.

## References

- Rouse et al. (1974), vegetation monitoring with ERTS.
- Huete (1988), soil-adjusted vegetation index.
- Kaufman and Tanre (1992), atmospherically resistant vegetation index.
- Qi et al. (1994), modified soil-adjusted vegetation index.
- McFeeters (1996), normalized difference water index.
- Gao (1996), vegetation liquid-water remote sensing.
- Gitelson et al. (2002, 2003), visible resistance and chlorophyll indices.
- Huete et al. (2002), MODIS vegetation indices.
- Zha et al. (2003), normalized difference built-up index.
- Xu (2006), modified normalized difference water index.
- Key and Benson (2006), Composite Burn Index and NBR methods.

## Complexity and scale path

Each index is `O(N)` in pixels and currently executes as vectorized NumPy over in-memory arrays.
The formulas are intentionally pure so an execution adapter can apply them through Xarray/Dask
blocks, Zarr chunks, CuPy arrays, or Numba kernels without changing scientific semantics. Before a
distributed adapter is accepted it must prove numerical parity, bounded peak memory, deterministic
nodata propagation, and chunk-boundary correctness against these reference implementations.

## Detector acceptance gate

A detector may write events only when it provides: immutable name/version, source checksums,
preprocessing parameters, quality masks, spatial/temporal resolution, calibration geography and
period, independent validation metrics, uncertainty or calibrated confidence, failure modes, and
reproducible evidence assets. Passing a unit test for an index formula is not sufficient.

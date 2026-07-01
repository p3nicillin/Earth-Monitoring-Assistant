from dataclasses import dataclass
from math import isfinite

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class RasterGrid:
    """Dependency-light raster grid contract used before opening distributed processing paths."""

    width: int
    height: int
    crs: str
    transform: tuple[float, float, float, float, float, float]
    dtype: str
    nodata: float | int | None = None

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Raster dimensions must be positive")
        if not self.crs.strip():
            raise ValueError("Raster CRS must be defined")
        if len(self.transform) != 6 or not all(isfinite(value) for value in self.transform):
            raise ValueError("Affine transform must contain six finite coefficients")
        pixel_width, row_rotation, _, column_rotation, pixel_height, _ = self.transform
        determinant = pixel_width * pixel_height - row_rotation * column_rotation
        if abs(determinant) <= 1e-15:
            raise ValueError("Affine transform is singular")
        dtype = np.dtype(self.dtype)
        if self.nodata is not None:
            try:
                converted = np.asarray(self.nodata, dtype=dtype).item()
            except (OverflowError, TypeError, ValueError) as exc:
                raise ValueError(f"Nodata value is not representable as {dtype}") from exc
            if np.issubdtype(dtype, np.integer) and converted != self.nodata:
                raise ValueError(f"Nodata value is not exactly representable as {dtype}")
            if isfinite(float(self.nodata)) and not isfinite(float(converted)):
                raise ValueError(f"Nodata value is not representable as {dtype}")


def assert_grids_aligned(
    reference: RasterGrid, candidate: RasterGrid, *, atol: float = 1e-9
) -> None:
    """Reject raster pairs that would otherwise produce spatially invalid pixel arithmetic."""
    reference.validate()
    candidate.validate()
    if (reference.width, reference.height) != (candidate.width, candidate.height):
        raise ValueError("Raster dimensions are not aligned")
    if reference.crs.strip().upper() != candidate.crs.strip().upper():
        raise ValueError("Raster CRS values are not aligned")
    if not np.allclose(reference.transform, candidate.transform, atol=atol, rtol=0):
        raise ValueError("Raster affine transforms are not aligned")


def valid_data_mask(
    array: npt.NDArray[np.generic], *, nodata: float | int | None = None
) -> npt.NDArray[np.bool_]:
    """Create a finite-data mask with explicit nodata propagation."""
    mask = np.isfinite(array)
    if nodata is not None:
        mask &= array != nodata
    return mask

import numpy as np
import pytest

from app.analysis.validation import RasterGrid, assert_grids_aligned, valid_data_mask


def grid(**overrides: object) -> RasterGrid:
    values = {
        "width": 100,
        "height": 100,
        "crs": "EPSG:32630",
        "transform": (10.0, 0.0, 500000.0, 0.0, -10.0, 5800000.0),
        "dtype": "float32",
        "nodata": -9999.0,
    }
    values.update(overrides)
    return RasterGrid(**values)  # type: ignore[arg-type]


def test_valid_raster_grid_and_alignment() -> None:
    reference = grid()
    reference.validate()
    assert_grids_aligned(reference, grid())


def test_alignment_rejects_crs_transform_and_shape_mismatches() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        assert_grids_aligned(grid(), grid(width=101))
    with pytest.raises(ValueError, match="CRS"):
        assert_grids_aligned(grid(), grid(crs="EPSG:4326"))
    with pytest.raises(ValueError, match="affine"):
        assert_grids_aligned(grid(), grid(transform=(20.0, 0.0, 500000.0, 0.0, -20.0, 5800000.0)))


def test_invalid_grid_and_nodata_mask() -> None:
    with pytest.raises(ValueError, match="singular"):
        grid(transform=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)).validate()
    array = np.array([1.0, -9999.0, np.nan])
    assert valid_data_mask(array, nodata=-9999.0).tolist() == [True, False, False]

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.warp import transform_bounds

from app.analysis import raster_io
from app.analysis.raster_io import RasterReadError
from app.analysis.validation import assert_grids_aligned

UTM_BOUNDS = (500000, 5651000, 500800, 5651800)  # EPSG:32630, off the English south coast


def _write_utm_geotiff(
    path: str, *, value: float, size: int = 8
) -> tuple[float, float, float, float]:
    """Write a small single-band GeoTIFF in UTM zone 30N and return its true WGS84 bbox."""
    transform = transform_from_bounds(*UTM_BOUNDS, size, size)
    data = np.full((size, size), value, dtype="uint16")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=size,
        height=size,
        count=1,
        dtype="uint16",
        crs="EPSG:32630",
        transform=transform,
        nodata=0,
    ) as dataset:
        dataset.write(data, 1)
    return transform_bounds("EPSG:32630", "EPSG:4326", *UTM_BOUNDS)


def test_read_window_returns_expected_shape_and_grid(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "band.tif")
    bounds = _write_utm_geotiff(path, value=1234.0)
    monkeypatch.setattr(raster_io, "sign_href", lambda href: href)

    array, grid = raster_io.read_window(path, bounds=bounds, max_pixels=1_000_000)

    assert array.shape == (grid.height, grid.width)
    assert np.all(array == pytest.approx(1234.0))
    grid.validate()


def test_sign_href_is_called_before_opening(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "band.tif")
    bounds = _write_utm_geotiff(path, value=42.0)
    calls: list[str] = []

    def fake_sign(href: str) -> str:
        calls.append(href)
        return href

    monkeypatch.setattr(raster_io, "sign_href", fake_sign)
    raster_io.read_window(path, bounds=bounds, max_pixels=1_000_000)

    assert calls == [path]


def test_read_window_downsamples_when_pixel_cap_exceeded(tmp_path, monkeypatch) -> None:
    # A watch area spanning most of a Sentinel-2 tile routinely exceeds max_pixels at
    # native resolution; the correct behavior is a decimated read that fits the budget,
    # not a hard failure (standard practice for large-AOI raster analysis).
    path = str(tmp_path / "band.tif")
    bounds = _write_utm_geotiff(path, value=1234.0, size=64)
    monkeypatch.setattr(raster_io, "sign_href", lambda href: href)

    array, grid = raster_io.read_window(path, bounds=bounds, max_pixels=100)

    assert grid.width * grid.height <= 100
    assert array.shape == (grid.height, grid.width)
    assert np.all(array == pytest.approx(1234.0))  # uniform source survives averaging
    grid.validate()


def test_read_window_honors_explicit_out_shape(tmp_path, monkeypatch) -> None:
    # Regression: combining bands of different native resolution (e.g. Sentinel-2
    # B04/B08 at 10m vs B12 at 20m) requires forcing a shared output grid, not
    # letting each read derive its own shape from its own native resolution.
    path = str(tmp_path / "band.tif")
    bounds = _write_utm_geotiff(path, value=99.0, size=8)
    monkeypatch.setattr(raster_io, "sign_href", lambda href: href)

    array, grid = raster_io.read_window(path, bounds=bounds, max_pixels=1_000_000, out_shape=(3, 5))

    assert grid.height == 3
    assert grid.width == 5
    assert array.shape == (3, 5)


def test_read_window_downsampled_grids_stay_aligned_across_reads(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "band.tif")
    bounds = _write_utm_geotiff(path, value=7.0, size=64)
    monkeypatch.setattr(raster_io, "sign_href", lambda href: href)

    _, grid_a = raster_io.read_window(path, bounds=bounds, max_pixels=100)
    _, grid_b = raster_io.read_window(path, bounds=bounds, max_pixels=100)

    assert_grids_aligned(grid_a, grid_b)


def test_read_window_raises_for_non_overlapping_bounds(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "band.tif")
    _write_utm_geotiff(path, value=1.0)
    monkeypatch.setattr(raster_io, "sign_href", lambda href: href)

    with pytest.raises(RasterReadError, match="do not overlap"):
        raster_io.read_window(path, bounds=(100.0, 10.0, 100.01, 10.01), max_pixels=1_000_000)


def test_read_window_signing_failure_wraps_as_raster_read_error(monkeypatch) -> None:
    def broken_sign(href: str) -> str:
        raise RuntimeError("token service unavailable")

    monkeypatch.setattr(raster_io, "sign_href", broken_sign)

    with pytest.raises(RasterReadError, match="unavailable"):
        raster_io.read_window(
            "https://example.test/band.tif", bounds=(-1, 51, 0, 52), max_pixels=1_000_000
        )


def test_two_reads_of_same_file_are_grid_aligned(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "band.tif")
    bounds = _write_utm_geotiff(path, value=5.0)
    monkeypatch.setattr(raster_io, "sign_href", lambda href: href)

    _, grid_a = raster_io.read_window(path, bounds=bounds, max_pixels=1_000_000)
    _, grid_b = raster_io.read_window(path, bounds=bounds, max_pixels=1_000_000)

    assert_grids_aligned(grid_a, grid_b)


def test_sign_href_wraps_underlying_errors(monkeypatch) -> None:
    import planetary_computer

    def broken(href: str) -> str:
        raise ValueError("bad token request")

    monkeypatch.setattr(planetary_computer, "sign", broken)

    with pytest.raises(RasterReadError, match="Failed to sign"):
        raster_io.sign_href("https://example.test/band.tif")

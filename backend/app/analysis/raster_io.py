"""Windowed COG reads for detector band access.

This is the only module that imports rasterio or planetary_computer, so the
raster-reading dependency's blast radius stays small and mockable in tests
(mirrors how ProviderError bounds acquisition.providers failures).
"""

from __future__ import annotations

import planetary_computer
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.errors import RasterioError, WindowError
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from app.analysis.indices import FloatArray
from app.analysis.validation import RasterGrid


class RasterReadError(RuntimeError):
    """Raised for any failure signing, opening, or windowed-reading a raster asset."""


def sign_href(href: str) -> str:
    """Sign a Microsoft Planetary Computer asset href with a short-lived SAS token."""
    try:
        return str(planetary_computer.sign(href))
    except Exception as exc:  # planetary_computer raises varied exception types
        raise RasterReadError(f"Failed to sign asset href: {exc}") from exc


def _vsi_path(href: str) -> str:
    """Route real http(s) asset URLs through GDAL's ranged-read curl handler.

    Local/file paths (used in tests, and useful for local COGs outside Planetary
    Computer) are opened directly -- /vsicurl/ only makes sense for network URLs.
    """
    if href.startswith(("http://", "https://")):
        return f"/vsicurl/{href}"
    return href


def read_window(
    href: str,
    *,
    bounds: tuple[float, float, float, float],
    max_pixels: int,
    out_shape: tuple[int, int] | None = None,
) -> tuple[FloatArray, RasterGrid]:
    """Read the pixel window covering `bounds` (WGS84 lon/lat: west, south, east, north)
    from a signed COG asset.

    Only the window overlapping `bounds` is read, never the full scene. The result stays
    in the raster's native CRS -- reprojecting pixel data would require warping between
    coordinate systems and could subtly alter values, which a detector must never do to
    its evidence. If the native-resolution window would exceed `max_pixels` (routine for
    a watch area spanning most or all of a Sentinel-2 tile), the read is downsampled to
    fit the budget using GDAL's overview-aware decimated read with average resampling --
    standard practice for large-AOI raster analysis, not a correctness compromise, since
    both the before and after read always request the identical output shape.

    Pass `out_shape` explicitly (height, width) to force a specific output grid rather
    than deriving one from this asset's own native resolution -- necessary when combining
    bands that are not all the same native resolution (e.g. Sentinel-2 B04/B08 at 10m vs
    B12 at 20m): reading "the same geographic bounds" independently from each would
    otherwise produce different-sized arrays for the identical area.
    """
    try:
        signed = sign_href(href)
        with rasterio.open(_vsi_path(signed)) as dataset:
            if dataset.crs is None:
                raise RasterReadError(f"Raster asset has no CRS: {href}")
            native_bounds = transform_bounds("EPSG:4326", dataset.crs, *bounds)
            window = from_bounds(*native_bounds, transform=dataset.transform)
            window = window.round_offsets().round_lengths()
            if window.width <= 0 or window.height <= 0:
                raise RasterReadError(f"Requested bounds produce an empty window: {href}")
            try:
                window.intersection(Window(0, 0, dataset.width, dataset.height))
            except WindowError as exc:
                raise RasterReadError(f"Requested bounds do not overlap raster: {href}") from exc

            if out_shape is not None:
                out_height, out_width = out_shape
            else:
                native_pixels = int(window.width) * int(window.height)
                if native_pixels > max_pixels:
                    downscale = (max_pixels / native_pixels) ** 0.5
                    out_width = max(1, round(window.width * downscale))
                    out_height = max(1, round(window.height * downscale))
                else:
                    out_width, out_height = int(window.width), int(window.height)

            array: FloatArray = dataset.read(
                1,
                window=window,
                out_shape=(out_height, out_width),
                out_dtype="float64",
                boundless=True,
                fill_value=dataset.nodata if dataset.nodata is not None else 0.0,
                resampling=Resampling.average,
            )
            window_transform = dataset.window_transform(window)
            output_transform = window_transform * Affine.scale(
                window.width / out_width, window.height / out_height
            )
            grid = RasterGrid(
                width=out_width,
                height=out_height,
                crs=dataset.crs.to_string(),
                transform=tuple(output_transform)[:6],
                dtype="float64",
                nodata=float(dataset.nodata) if dataset.nodata is not None else None,
            )
            return array, grid
    except RasterReadError:
        raise
    except (RasterioError, OSError, ValueError) as exc:
        raise RasterReadError(f"Failed to read raster window from {href}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - this boundary must never leak a raw exception
        raise RasterReadError(
            f"Unexpected failure reading raster window from {href}: {exc}"
        ) from exc

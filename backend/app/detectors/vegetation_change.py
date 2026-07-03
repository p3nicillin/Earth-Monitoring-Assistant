"""Vegetation loss / burn-severity detector for Sentinel-2 watch areas.

Compares the two most recent qualifying Sentinel-2 observations for a watch
area (cloud-filtered, far enough apart to avoid near-duplicate overpasses) and
flags a real, evidence-backed change when either signal clears its threshold:

- Burn severity via dNBR (Key & Benson 2006 breakpoints, already used in
  app.analysis.indices).
- Vegetation loss via an NDVI drop, gated to pixels that were actually
  vegetated beforehand (excludes bare soil/water noise).

All numbers on a flagged Event's evidence are reproducible from the stored
before/after item ids and thresholds -- nothing here is a fabricated score.
"""

from __future__ import annotations

import asyncio
import functools
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from app.analysis.indices import FloatArray, compute_index, delta_nbr, threshold_change
from app.analysis.raster_io import read_window
from app.analysis.validation import RasterGrid, assert_grids_aligned, valid_data_mask
from app.detectors.base import DetectionResult, DetectorContext
from app.models.entities import EventCategory, Observation, Severity
from app.utils.geo import approximate_area_sq_km, polygon_bbox, spatial_to_geojson

DETECTOR_NAME = "sentinel2-vegetation-burn-change"
DETECTOR_VERSION = "1.0.0"

_REQUIRED_BANDS = ("B04", "B08", "B12")  # red, NIR, SWIR2
_TARGET_CHANGE_FRACTION = 0.05  # AOI-changed-fraction at which confidence saturates to 1.0
_MGRS_TILE_RE = re.compile(r"^T\d{2}[A-Z]{3}$")
# Bound on real band reads per detector run: several same-gap tiles are tried
# in order (best gap first) until one has real vegetated overlap to analyse,
# rather than betting everything on a single, possibly-degenerate tile.
_MAX_TILE_ATTEMPTS = 5


def _mgrs_tile(source_item_id: str) -> str | None:
    """Extract the Sentinel-2 MGRS tile token (e.g. "T30UVB") from a standard
    L2A item id (S2{A|B}_MSIL2A_{datetime}_R{orbit}_{tile}_{datetime}).

    A watch area spanning more than one Sentinel-2 tile can have several
    "most recent" observations that cover *different ground* on the same day.
    Pairing across tiles would silently compare unrelated locations, so the
    detector must only ever pair two observations of the same tile -- same
    tile means an identical CRS/pixel grid across dates, so the watch area's
    own bounding box reads the same ground both times.
    """
    for token in source_item_id.split("_"):
        if _MGRS_TILE_RE.match(token):
            return token
    return None


@dataclass(frozen=True)
class ChangeThresholds:
    dnbr_burn_threshold: float = 0.27
    ndvi_drop_threshold: float = 0.15
    min_change_fraction: float = 0.005
    min_vegetated_ndvi: float = 0.2


def _dnbr_severity(mean_dnbr: float) -> Severity:
    """Key & Benson (2006) burn-severity classes, floored at medium: only pixels
    already past the flagging gate reach this function."""
    if mean_dnbr >= 0.66:
        return Severity.critical
    if mean_dnbr >= 0.44:
        return Severity.high
    return Severity.medium


def evaluate_change(
    *,
    before_bands: dict[str, FloatArray],
    after_bands: dict[str, FloatArray],
    thresholds: ChangeThresholds,
    geometry: dict[str, Any],
    watch_area_name: str,
    area_sq_km: float | None,
    observation_id: uuid.UUID,
    before_item_id: str,
    after_item_id: str,
    before_captured_at: datetime,
    after_captured_at: datetime,
    band_hrefs: dict[str, str],
) -> DetectionResult | None:
    """Pure decision function: no I/O, deterministic given its inputs."""
    ndvi_before = compute_index("ndvi", {"nir": before_bands["nir"], "red": before_bands["red"]})
    ndvi_after = compute_index("ndvi", {"nir": after_bands["nir"], "red": after_bands["red"]})
    nbr_before = compute_index("nbr", {"nir": before_bands["nir"], "swir2": before_bands["swir2"]})
    nbr_after = compute_index("nbr", {"nir": after_bands["nir"], "swir2": after_bands["swir2"]})
    dnbr = delta_nbr(nbr_before, nbr_after)

    was_vegetated = ndvi_before > thresholds.min_vegetated_ndvi
    valid = valid_data_mask(dnbr) & was_vegetated
    total_valid = int(np.count_nonzero(valid))
    if total_valid == 0:
        return None

    burn_mask = valid & (dnbr >= thresholds.dnbr_burn_threshold)
    ndvi_dropped = threshold_change(
        ndvi_before,
        ndvi_after,
        minimum_absolute_change=thresholds.ndvi_drop_threshold,
        valid_mask=valid,
    ) & (ndvi_after < ndvi_before)
    changed_mask = burn_mask | ndvi_dropped
    changed_fraction = float(np.count_nonzero(changed_mask)) / total_valid

    if changed_fraction < thresholds.min_change_fraction:
        return None

    mean_dnbr = float(np.mean(dnbr[changed_mask]))
    max_dnbr = float(np.max(dnbr[changed_mask]))
    mean_ndvi_delta = float(np.mean((ndvi_before - ndvi_after)[changed_mask]))
    confidence = min(1.0, changed_fraction / _TARGET_CHANGE_FRACTION)
    severity = _dnbr_severity(mean_dnbr)

    return DetectionResult(
        flagged=True,
        title=f"Vegetation change detected in {watch_area_name}",
        summary=(
            f"Change detected across ~{changed_fraction * 100:.1f}% of this watch area's valid "
            f"pixels between {before_captured_at.date().isoformat()} and "
            f"{after_captured_at.date().isoformat()} (mean dNBR {mean_dnbr:.2f}, mean NDVI drop "
            f"{mean_ndvi_delta:.2f}). Event geometry is the full watch-area polygon, not the "
            "precise changed-pixel shape."
        ),
        event_type="vegetation_burn_change",
        category=EventCategory.environment,
        severity=severity,
        confidence=confidence,
        geometry=geometry,
        area_sq_km=area_sq_km,
        evidence={
            "detector_name": DETECTOR_NAME,
            "detector_version": DETECTOR_VERSION,
            "before_item_id": before_item_id,
            "after_item_id": after_item_id,
            "before_captured_at": before_captured_at.isoformat(),
            "after_captured_at": after_captured_at.isoformat(),
            "mean_dnbr": mean_dnbr,
            "max_dnbr": max_dnbr,
            "mean_ndvi_delta": mean_ndvi_delta,
            "changed_pixel_fraction": changed_fraction,
            "valid_pixel_count": total_valid,
            "bands_used": ["B04", "B08", "B12"],
            "thresholds": {
                "dnbr_burn_threshold": thresholds.dnbr_burn_threshold,
                "ndvi_drop_threshold": thresholds.ndvi_drop_threshold,
                "min_change_fraction": thresholds.min_change_fraction,
                "min_vegetated_ndvi": thresholds.min_vegetated_ndvi,
            },
            "band_hrefs": band_hrefs,
        },
        observation_id=observation_id,
    )


@dataclass(frozen=True)
class _BandSet:
    red: FloatArray
    nir: FloatArray
    swir2: FloatArray
    grids: dict[str, RasterGrid]
    hrefs: dict[str, str]


async def _read_bands(
    observation: Observation, bounds: tuple[float, float, float, float], max_pixels: int
) -> _BandSet:
    loop = asyncio.get_running_loop()
    hrefs = {band: observation.assets[band]["href"] for band in _REQUIRED_BANDS}

    # B04 (red, 10m) is the resolution reference -- B08 (NIR) shares its 10m
    # native resolution, but B12 (SWIR2) is native 20m. Reading "the same
    # geographic bounds" from each independently would produce different-sized
    # arrays for the identical area, so every other band is explicitly resampled
    # onto B04's output grid to keep all three bands pixel-aligned.
    reference_array, reference_grid = await loop.run_in_executor(
        None,
        functools.partial(read_window, hrefs["B04"], bounds=bounds, max_pixels=max_pixels),
    )
    out_shape = (reference_grid.height, reference_grid.width)
    remaining = {band: href for band, href in hrefs.items() if band != "B04"}
    reads = {
        band: loop.run_in_executor(
            None,
            functools.partial(
                read_window, href, bounds=bounds, max_pixels=max_pixels, out_shape=out_shape
            ),
        )
        for band, href in remaining.items()
    }
    results: dict[str, tuple[FloatArray, RasterGrid]] = dict(
        zip(reads.keys(), await asyncio.gather(*reads.values()), strict=True)
    )
    results["B04"] = (reference_array, reference_grid)
    return _BandSet(
        red=results["B04"][0],
        nir=results["B08"][0],
        swir2=results["B12"][0],
        grids={"red": results["B04"][1], "nir": results["B08"][1], "swir2": results["B12"][1]},
        hrefs=hrefs,
    )


def select_pairs(
    candidates: list[Observation], *, min_gap: timedelta
) -> list[tuple[str, Observation, Observation]]:
    """Find every same-tile before/after pair, best temporal spread first.

    Pure and I/O-free (no raster reads), so this is directly unit-testable
    with plain Observation objects -- unlike a real change decision, pairing
    depends only on metadata (captured_at, source_item_id, cloud_cover),
    never pixel data.

    Returns all qualifying tiles rather than a single "best" one: a watch
    area spanning many tiles often has most of them sharing the same pair of
    overpass dates (same gap), and an arbitrary tie-break can land on a tile
    that is mostly outside the watch area or mostly water/urban -- a
    degenerate pick with nothing to analyse, even though other same-gap
    tiles have substantial real vegetated coverage. The caller tries
    candidates in order until one actually has something to say.
    """
    by_tile: dict[str, list[Observation]] = {}
    for observation in candidates:
        tile = _mgrs_tile(observation.source_item_id)
        if tile is not None:
            by_tile.setdefault(tile, []).append(observation)

    pairs: list[tuple[str, Observation, Observation, timedelta]] = []
    for tile, tile_observations in by_tile.items():
        tile_observations.sort(key=lambda obs: obs.captured_at, reverse=True)
        after_obs = tile_observations[0]
        before_obs = next(
            (
                obs
                for obs in tile_observations[1:]
                if after_obs.captured_at - obs.captured_at >= min_gap
            ),
            None,
        )
        if before_obs is None:
            continue
        gap = after_obs.captured_at - before_obs.captured_at
        pairs.append((tile, before_obs, after_obs, gap))

    # Most temporal spread first (more time for a real change to be visible);
    # tile name as a deterministic, arbitrary-but-stable tie-break.
    pairs.sort(key=lambda item: (-item[3], item[0]))
    return [(tile, before_obs, after_obs) for tile, before_obs, after_obs, _gap in pairs]


class VegetationChangeDetector:
    name = DETECTOR_NAME
    version = DETECTOR_VERSION

    async def detect(self, context: DetectorContext) -> list[DetectionResult]:
        settings = context.settings
        max_cloud = settings.detector_cloud_cover_max
        candidates = [
            observation
            for observation in context.observations
            if (observation.cloud_cover is None or observation.cloud_cover <= max_cloud)
            and all(band in observation.assets for band in _REQUIRED_BANDS)
        ]
        if len(candidates) < 2:
            return []

        min_gap = timedelta(days=settings.detector_min_days_between_pair)
        pairs = select_pairs(candidates, min_gap=min_gap)
        watch_bounds = polygon_bbox(context.geometry)

        for _tile, before_obs, after_obs in pairs[:_MAX_TILE_ATTEMPTS]:
            # Read bounds = watch area (bbox) ^ this tile's own footprint, not
            # the watch area's bbox alone. A watch area is routinely much
            # larger than one Sentinel-2 tile; reading its full bbox from a
            # single tile's COG wastes most of the pixel budget on
            # nodata-filled area outside the tile and downsamples the real
            # signal into the noise floor.
            tile_bounds = polygon_bbox(spatial_to_geojson(after_obs.footprint))
            west, south = max(watch_bounds[0], tile_bounds[0]), max(watch_bounds[1], tile_bounds[1])
            east, north = min(watch_bounds[2], tile_bounds[2]), min(watch_bounds[3], tile_bounds[3])
            if west >= east or south >= north:
                continue
            bounds = (west, south, east, north)

            before_set, after_set = await asyncio.gather(
                _read_bands(before_obs, bounds, settings.detector_max_window_pixels),
                _read_bands(after_obs, bounds, settings.detector_max_window_pixels),
            )
            for band_name in ("red", "nir", "swir2"):
                assert_grids_aligned(before_set.grids[band_name], after_set.grids[band_name])

            result = evaluate_change(
                before_bands={
                    "red": before_set.red,
                    "nir": before_set.nir,
                    "swir2": before_set.swir2,
                },
                after_bands={"red": after_set.red, "nir": after_set.nir, "swir2": after_set.swir2},
                thresholds=ChangeThresholds(
                    ndvi_drop_threshold=settings.detector_ndvi_threshold,
                    min_change_fraction=settings.detector_min_change_fraction,
                ),
                geometry=context.geometry,
                watch_area_name=context.watch_area.name,
                area_sq_km=approximate_area_sq_km(context.geometry),
                observation_id=after_obs.id,
                before_item_id=before_obs.source_item_id,
                after_item_id=after_obs.source_item_id,
                before_captured_at=before_obs.captured_at,
                after_captured_at=after_obs.captured_at,
                band_hrefs={
                    **{f"before_{k}": v for k, v in before_set.hrefs.items()},
                    **{f"after_{k}": v for k, v in after_set.hrefs.items()},
                },
            )
            # A tile with nothing vegetated to analyse (e.g. mostly water/urban
            # in the watch-area overlap) is a degenerate pick, not a "no
            # change" answer -- try the next best-gap tile instead of stopping.
            if result is not None:
                return [result]
        return []


__all__ = [
    "DETECTOR_NAME",
    "DETECTOR_VERSION",
    "ChangeThresholds",
    "VegetationChangeDetector",
    "evaluate_change",
    "select_pairs",
]

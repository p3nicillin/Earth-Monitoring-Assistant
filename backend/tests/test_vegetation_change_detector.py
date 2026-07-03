import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.detectors.vegetation_change import ChangeThresholds, evaluate_change, select_pairs
from app.models.entities import Observation

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-1.0, 51.0], [0.0, 51.0], [0.0, 52.0], [-1.0, 52.0], [-1.0, 51.0]]],
}

_COMMON_KWARGS = {
    "geometry": GEOMETRY,
    "watch_area_name": "Test Watch Area",
    "area_sq_km": 123.4,
    "observation_id": uuid.uuid4(),
    "before_item_id": "before-item",
    "after_item_id": "after-item",
    "before_captured_at": datetime(2026, 1, 1, tzinfo=UTC),
    "after_captured_at": datetime(2026, 1, 10, tzinfo=UTC),
    "band_hrefs": {"before_red": "https://example.test/before-b04.tif"},
}


def _healthy_bands(size: int = 10) -> dict[str, np.ndarray]:
    return {
        "red": np.full((size, size), 0.1, dtype=np.float32),
        "nir": np.full((size, size), 0.5, dtype=np.float32),
        "swir2": np.full((size, size), 0.1, dtype=np.float32),
    }


def test_no_change_pair_produces_no_detection() -> None:
    before = _healthy_bands()
    after = _healthy_bands()

    result = evaluate_change(
        before_bands=before, after_bands=after, thresholds=ChangeThresholds(), **_COMMON_KWARGS
    )

    assert result is None


def test_burn_patch_above_threshold_flags_with_expected_evidence() -> None:
    before = _healthy_bands()
    after = _healthy_bands()
    # Burn signature in a known 4x4 sub-region: NIR collapses, SWIR2 rises (char/ash/soil).
    after["nir"][0:4, 0:4] = 0.15
    after["red"][0:4, 0:4] = 0.2
    after["swir2"][0:4, 0:4] = 0.35

    result = evaluate_change(
        before_bands=before, after_bands=after, thresholds=ChangeThresholds(), **_COMMON_KWARGS
    )

    assert result is not None
    assert result.flagged is True
    assert result.event_type == "vegetation_burn_change"
    assert result.severity == "critical"  # mean dNBR over the burned patch exceeds 0.66
    assert result.evidence["changed_pixel_fraction"] == pytest.approx(16 / 100)
    assert result.evidence["mean_dnbr"] == pytest.approx(1.0667, abs=1e-3)
    assert result.confidence == pytest.approx(1.0)  # saturated well above target fraction
    assert result.geometry == GEOMETRY
    assert result.observation_id == _COMMON_KWARGS["observation_id"]


def test_sub_threshold_change_does_not_flag() -> None:
    before = _healthy_bands()
    after = _healthy_bands()
    # Mild change everywhere: NDVI drop ~0.09 (< default 0.15), dNBR ~0.17 (< default 0.27).
    after["nir"][:] = 0.45
    after["red"][:] = 0.12
    after["swir2"][:] = 0.15

    result = evaluate_change(
        before_bands=before, after_bands=after, thresholds=ChangeThresholds(), **_COMMON_KWARGS
    )

    assert result is None


def test_mismatched_band_shapes_raise() -> None:
    before = _healthy_bands(size=10)
    after = _healthy_bands(size=5)

    with pytest.raises(ValueError, match="same shape"):
        evaluate_change(
            before_bands=before, after_bands=after, thresholds=ChangeThresholds(), **_COMMON_KWARGS
        )


def test_evaluation_is_deterministic() -> None:
    before = _healthy_bands()
    after = _healthy_bands()
    after["nir"][0:4, 0:4] = 0.15
    after["red"][0:4, 0:4] = 0.2
    after["swir2"][0:4, 0:4] = 0.35

    first = evaluate_change(
        before_bands=before, after_bands=after, thresholds=ChangeThresholds(), **_COMMON_KWARGS
    )
    second = evaluate_change(
        before_bands=before, after_bands=after, thresholds=ChangeThresholds(), **_COMMON_KWARGS
    )

    assert first is not None and second is not None
    assert first.evidence == second.evidence
    assert first.severity == second.severity
    assert first.confidence == second.confidence


def test_bare_soil_is_excluded_by_vegetated_gate() -> None:
    # Never vegetated to begin with (NDVI well below the min_vegetated_ndvi gate) --
    # a large spectral swing here must not be mistaken for vegetation/burn change.
    before = {
        "red": np.full((10, 10), 0.3, dtype=np.float32),
        "nir": np.full((10, 10), 0.32, dtype=np.float32),
        "swir2": np.full((10, 10), 0.3, dtype=np.float32),
    }
    after = {
        "red": np.full((10, 10), 0.35, dtype=np.float32),
        "nir": np.full((10, 10), 0.1, dtype=np.float32),
        "swir2": np.full((10, 10), 0.4, dtype=np.float32),
    }

    result = evaluate_change(
        before_bands=before, after_bands=after, thresholds=ChangeThresholds(), **_COMMON_KWARGS
    )

    assert result is None


def _observation(*, item_id: str, captured_at: datetime, cloud_cover: float = 5.0) -> Observation:
    return Observation(
        id=uuid.uuid4(),
        source="sentinel-2-l2a",
        source_item_id=item_id,
        captured_at=captured_at,
        cloud_cover=cloud_cover,
        assets={"B04": {"href": "https://x/b04.tif"}, "B08": {"href": "https://x/b08.tif"}},
        metadata_json={},
    )


def test_select_pairs_never_crosses_tiles() -> None:
    # Regression: a watch area spanning two Sentinel-2 tiles previously paired
    # "the two most recent observations overall," which could be two different
    # tiles covering different ground on the same day -- not a valid
    # before/after comparison. Only one tile (T30UVB) here actually has a
    # qualifying (>=3 day gap) pair; T30UVA's items are only 1 day apart.
    tile_a_new = _observation(
        item_id="S2B_MSIL2A_20260625T113319_R080_T30UVA_20260625T141327",
        captured_at=datetime(2026, 6, 25, tzinfo=UTC),
    )
    tile_a_old = _observation(
        item_id="S2B_MSIL2A_20260624T113319_R080_T30UVA_20260624T141327",
        captured_at=datetime(2026, 6, 24, tzinfo=UTC),
    )
    tile_b_new = _observation(
        item_id="S2B_MSIL2A_20260625T113320_R080_T30UVB_20260625T141328",
        captured_at=datetime(2026, 6, 25, tzinfo=UTC),
    )
    tile_b_old = _observation(
        item_id="S2A_MSIL2A_20260610T113320_R080_T30UVB_20260610T141328",
        captured_at=datetime(2026, 6, 10, tzinfo=UTC),
    )

    pairs = select_pairs(
        [tile_a_new, tile_a_old, tile_b_new, tile_b_old], min_gap=timedelta(days=3)
    )

    assert len(pairs) == 1
    tile, before, after = pairs[0]
    assert tile == "T30UVB"
    assert before is tile_b_old
    assert after is tile_b_new


def test_select_pairs_returns_empty_without_a_qualifying_gap() -> None:
    same_tile_close = [
        _observation(
            item_id="S2B_MSIL2A_20260625T113319_R080_T30UVA_20260625T141327",
            captured_at=datetime(2026, 6, 25, tzinfo=UTC),
        ),
        _observation(
            item_id="S2A_MSIL2A_20260624T113319_R080_T30UVA_20260624T141327",
            captured_at=datetime(2026, 6, 24, tzinfo=UTC),
        ),
    ]

    assert select_pairs(same_tile_close, min_gap=timedelta(days=3)) == []


def test_select_pairs_ignores_unparseable_item_ids() -> None:
    unparseable = [
        _observation(item_id="not-a-real-stac-id", captured_at=datetime(2026, 6, 25, tzinfo=UTC)),
        _observation(item_id="also-not-one", captured_at=datetime(2026, 6, 1, tzinfo=UTC)),
    ]

    assert select_pairs(unparseable, min_gap=timedelta(days=3)) == []


def test_select_pairs_orders_by_gap_then_tile_name() -> None:
    # Two tiles share the same 5-day gap; a third has a smaller gap. Order
    # must be gap-descending first, then tile name as a stable tie-break --
    # never arbitrary dict/insertion order, since a degenerate tile (e.g.
    # mostly water) at the front would make the caller's retry loop pointless.
    def pair_for(tile: str, *, gap_days: int) -> list[Observation]:
        newest = datetime(2026, 6, 25, tzinfo=UTC)
        return [
            _observation(item_id=f"S2B_MSIL2A_20260625T000000_R080_{tile}_X", captured_at=newest),
            _observation(
                item_id=f"S2A_MSIL2A_20260601T000000_R080_{tile}_X",
                captured_at=newest - timedelta(days=gap_days),
            ),
        ]

    candidates = [
        *pair_for("T30UVB", gap_days=5),
        *pair_for("T30UVA", gap_days=5),
        *pair_for("T30UVC", gap_days=2),
    ]

    pairs = select_pairs(candidates, min_gap=timedelta(days=2))

    assert [tile for tile, _before, _after in pairs] == ["T30UVA", "T30UVB", "T30UVC"]

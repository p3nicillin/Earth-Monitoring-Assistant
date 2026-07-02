import math
from datetime import UTC, datetime

import pytest

from app.services.ephemeris import (
    PLANET_ORDER,
    compute_ephemeris,
    heliocentric_position,
    julian_date,
)

J2000 = datetime(2000, 1, 1, 12, 0, tzinfo=UTC)

# Perihelion/aphelion bounds with margin for the approximate elements.
DISTANCE_BOUNDS = {
    "mercury": (0.30, 0.48),
    "venus": (0.71, 0.74),
    "earth": (0.97, 1.02),
    "mars": (1.35, 1.68),
    "jupiter": (4.90, 5.50),
    "saturn": (9.00, 10.13),
    "uranus": (18.20, 20.15),
    "neptune": (29.70, 30.40),
    "pluto": (29.60, 49.40),
}


def test_julian_date_epoch() -> None:
    assert julian_date(J2000) == pytest.approx(2451545.0, abs=1e-6)


def test_julian_date_requires_timezone() -> None:
    with pytest.raises(ValueError):
        julian_date(datetime(2026, 7, 2, 0, 0))  # noqa: DTZ001


def test_heliocentric_distances_stay_within_orbital_bounds() -> None:
    for moment in (J2000, datetime(2026, 7, 2, tzinfo=UTC), datetime(2049, 12, 31, tzinfo=UTC)):
        for planet, (minimum, maximum) in DISTANCE_BOUNDS.items():
            distance = math.hypot(*heliocentric_position(planet, moment))
            assert minimum <= distance <= maximum, f"{planet} at {moment}: {distance}"


def test_earth_longitude_at_j2000_matches_elements() -> None:
    x, y, _ = heliocentric_position("earth", J2000)
    longitude = math.degrees(math.atan2(y, x)) % 360
    # Mean longitude 100.46 deg with eccentricity correction stays within 2.5 deg.
    assert longitude == pytest.approx(100.46, abs=2.5)


def test_mercury_moves_about_four_degrees_per_day() -> None:
    day_one = datetime(2026, 7, 2, tzinfo=UTC)
    day_two = datetime(2026, 7, 3, tzinfo=UTC)
    lon_one = math.degrees(math.atan2(*reversed(heliocentric_position("mercury", day_one)[:2])))
    lon_two = math.degrees(math.atan2(*reversed(heliocentric_position("mercury", day_two)[:2])))
    delta = (lon_two - lon_one) % 360
    assert 2.0 < delta < 7.0


def test_compute_ephemeris_snapshot_is_complete_and_consistent() -> None:
    snapshot = compute_ephemeris(datetime(2026, 7, 2, tzinfo=UTC))
    assert [planet.name for planet in snapshot.planets] == list(PLANET_ORDER)
    by_name = {planet.name: planet for planet in snapshot.planets}
    earth = by_name["earth"]
    assert earth.distance_from_earth_au == pytest.approx(0.0, abs=1e-9)
    assert earth.elongation_deg == 0.0
    for planet in snapshot.planets:
        assert 0 <= planet.ecliptic_longitude_deg < 360
        assert planet.distance_from_sun_au == pytest.approx(
            math.hypot(planet.x_au, planet.y_au, planet.z_au), rel=1e-9
        )
        if planet.name != "earth":
            assert 0.0 <= planet.elongation_deg <= 180.0
            # Light travels one au in ~8.317 minutes.
            assert planet.light_time_minutes == pytest.approx(
                planet.distance_from_earth_au * 8.3167, rel=1e-3
            )
    # Inner planets can never appear far from the Sun in Earth's sky.
    assert by_name["mercury"].elongation_deg <= 28.5
    assert by_name["venus"].elongation_deg <= 48.0


def test_ephemeris_defaults_to_now() -> None:
    snapshot = compute_ephemeris()
    assert (datetime.now(UTC) - snapshot.computed_at).total_seconds() < 5

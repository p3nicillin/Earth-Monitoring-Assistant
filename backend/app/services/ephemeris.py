"""Approximate heliocentric ephemerides for the major planets.

Positions are computed from the JPL "Keplerian Elements for Approximate
Positions of the Major Planets" (E. M. Standish), Table 1, valid 1800-2050.
Accuracy is within a few arcminutes for the classical planets in that span,
which is sufficient for situational awareness displays; it is not suitable
for targeting or navigation.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.solar_system import EphemerisSnapshot, PlanetState

EPHEMERIS_SOURCE = "JPL approximate Keplerian elements (Standish, 1800-2050)"
_J2000_JD = 2451545.0
_KEPLER_TOLERANCE_DEG = 1e-6
_KEPLER_MAX_ITERATIONS = 100


@dataclass(frozen=True)
class KeplerianElements:
    """Element values at J2000 and centennial rates: a, e, I, L, varpi, Omega."""

    semi_major_axis_au: float
    semi_major_axis_rate: float
    eccentricity: float
    eccentricity_rate: float
    inclination_deg: float
    inclination_rate: float
    mean_longitude_deg: float
    mean_longitude_rate: float
    perihelion_longitude_deg: float
    perihelion_longitude_rate: float
    node_longitude_deg: float
    node_longitude_rate: float


@dataclass(frozen=True)
class PlanetFacts:
    display_color: str
    radius_km: float
    orbital_period_days: float
    body_class: str


# Standish Table 1 (1800 AD - 2050 AD). "earth" is the Earth-Moon barycenter.
_ELEMENTS: dict[str, KeplerianElements] = {
    "mercury": KeplerianElements(
        0.38709927,
        0.00000037,
        0.20563593,
        0.00001906,
        7.00497902,
        -0.00594749,
        252.25032350,
        149472.67411175,
        77.45779628,
        0.16047689,
        48.33076593,
        -0.12534081,
    ),
    "venus": KeplerianElements(
        0.72333566,
        0.00000390,
        0.00677672,
        -0.00004107,
        3.39467605,
        -0.00078890,
        181.97909950,
        58517.81538729,
        131.60246718,
        0.00268329,
        76.67984255,
        -0.27769418,
    ),
    "earth": KeplerianElements(
        1.00000261,
        0.00000562,
        0.01671123,
        -0.00004392,
        -0.00001531,
        -0.01294668,
        100.46457166,
        35999.37244981,
        102.93768193,
        0.32327364,
        0.0,
        0.0,
    ),
    "mars": KeplerianElements(
        1.52371034,
        0.00001847,
        0.09339410,
        0.00007882,
        1.84969142,
        -0.00813131,
        -4.55343205,
        19140.30268499,
        -23.94362959,
        0.44441088,
        49.55953891,
        -0.29257343,
    ),
    "jupiter": KeplerianElements(
        5.20288700,
        -0.00011607,
        0.04838624,
        -0.00013253,
        1.30439695,
        -0.00183714,
        34.39644051,
        3034.74612775,
        14.72847983,
        0.21252668,
        100.47390909,
        0.20469106,
    ),
    "saturn": KeplerianElements(
        9.53667594,
        -0.00125060,
        0.05386179,
        -0.00050991,
        2.48599187,
        0.00193609,
        49.95424423,
        1222.49362201,
        92.59887831,
        -0.41897216,
        113.66242448,
        -0.28867794,
    ),
    "uranus": KeplerianElements(
        19.18916464,
        -0.00196176,
        0.04725744,
        -0.00004397,
        0.77263783,
        -0.00242939,
        313.23810451,
        428.48202785,
        170.95427630,
        0.40805281,
        74.01692503,
        0.04240589,
    ),
    "neptune": KeplerianElements(
        30.06992276,
        0.00026291,
        0.00859048,
        0.00005105,
        1.77004347,
        0.00035372,
        -55.12002969,
        218.45945325,
        44.96476227,
        -0.32241464,
        131.78422574,
        -0.00508664,
    ),
    "pluto": KeplerianElements(
        39.48211675,
        -0.00031596,
        0.24882730,
        0.00005170,
        17.14001206,
        0.00004818,
        238.92903833,
        145.20780515,
        224.06891629,
        -0.04062942,
        110.30393684,
        -0.01183482,
    ),
}

_FACTS: dict[str, PlanetFacts] = {
    "mercury": PlanetFacts("#9ca3af", 2439.7, 87.969, "terrestrial planet"),
    "venus": PlanetFacts("#facc15", 6051.8, 224.701, "terrestrial planet"),
    "earth": PlanetFacts("#38bdf8", 6371.0, 365.256, "terrestrial planet"),
    "mars": PlanetFacts("#f87171", 3389.5, 686.980, "terrestrial planet"),
    "jupiter": PlanetFacts("#fb923c", 69911.0, 4332.589, "gas giant"),
    "saturn": PlanetFacts("#fbbf24", 58232.0, 10759.22, "gas giant"),
    "uranus": PlanetFacts("#5eead4", 25362.0, 30685.4, "ice giant"),
    "neptune": PlanetFacts("#818cf8", 24622.0, 60189.0, "ice giant"),
    "pluto": PlanetFacts("#d8b4fe", 1188.3, 90560.0, "dwarf planet"),
}

PLANET_ORDER = tuple(_ELEMENTS)


def julian_date(moment: datetime) -> float:
    """UTC datetime to Julian date. UTC~TT is fine at arcminute accuracy."""
    if moment.tzinfo is None:
        raise ValueError("Ephemeris timestamps must be timezone-aware")
    return moment.timestamp() / 86400.0 + 2440587.5


def _wrap_degrees(value: float) -> float:
    wrapped = math.fmod(value, 360.0)
    return wrapped + 360.0 if wrapped < 0 else wrapped


def _solve_kepler(mean_anomaly_deg: float, eccentricity: float) -> float:
    """Solve M = E - e*sin(E) by Newton iteration, all angles in degrees."""
    e_star = math.degrees(eccentricity)
    mean = math.fmod(mean_anomaly_deg + 180.0, 360.0) - 180.0
    eccentric = mean + e_star * math.sin(math.radians(mean))
    for _ in range(_KEPLER_MAX_ITERATIONS):
        delta_mean = mean - (eccentric - e_star * math.sin(math.radians(eccentric)))
        delta_ecc = delta_mean / (1.0 - eccentricity * math.cos(math.radians(eccentric)))
        eccentric += delta_ecc
        if abs(delta_ecc) < _KEPLER_TOLERANCE_DEG:
            break
    return eccentric


def heliocentric_position(planet: str, moment: datetime) -> tuple[float, float, float]:
    """J2000 ecliptic heliocentric rectangular coordinates in astronomical units."""
    elements = _ELEMENTS[planet]
    centuries = (julian_date(moment) - _J2000_JD) / 36525.0
    a = elements.semi_major_axis_au + elements.semi_major_axis_rate * centuries
    e = elements.eccentricity + elements.eccentricity_rate * centuries
    inclination = math.radians(elements.inclination_deg + elements.inclination_rate * centuries)
    mean_longitude = elements.mean_longitude_deg + elements.mean_longitude_rate * centuries
    perihelion = elements.perihelion_longitude_deg + elements.perihelion_longitude_rate * centuries
    node = math.radians(elements.node_longitude_deg + elements.node_longitude_rate * centuries)
    argument_perihelion = math.radians(perihelion) - node
    eccentric = math.radians(_solve_kepler(mean_longitude - perihelion, e))

    x_orbital = a * (math.cos(eccentric) - e)
    y_orbital = a * math.sqrt(1.0 - e * e) * math.sin(eccentric)

    cos_w, sin_w = math.cos(argument_perihelion), math.sin(argument_perihelion)
    cos_o, sin_o = math.cos(node), math.sin(node)
    cos_i, sin_i = math.cos(inclination), math.sin(inclination)
    x = (cos_w * cos_o - sin_w * sin_o * cos_i) * x_orbital + (
        -sin_w * cos_o - cos_w * sin_o * cos_i
    ) * y_orbital
    y = (cos_w * sin_o + sin_w * cos_o * cos_i) * x_orbital + (
        -sin_w * sin_o + cos_w * cos_o * cos_i
    ) * y_orbital
    z = (sin_w * sin_i) * x_orbital + (cos_w * sin_i) * y_orbital
    return x, y, z


def _elongation_deg(
    planet_vec: tuple[float, float, float], earth_vec: tuple[float, float, float]
) -> float:
    """Sun-Earth-planet angle: how far the planet appears from the Sun in Earth's sky."""
    to_planet = tuple(p - e for p, e in zip(planet_vec, earth_vec, strict=True))
    to_sun = tuple(-component for component in earth_vec)
    dot = sum(a * b for a, b in zip(to_planet, to_sun, strict=True))
    norm = math.hypot(*to_planet) * math.hypot(*to_sun)
    if norm == 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / norm))))


def compute_ephemeris(moment: datetime | None = None) -> EphemerisSnapshot:
    at = moment or datetime.now(UTC)
    earth_vec = heliocentric_position("earth", at)
    planets: list[PlanetState] = []
    for name in PLANET_ORDER:
        vec = heliocentric_position(name, at)
        facts = _FACTS[name]
        distance_from_sun = math.hypot(*vec)
        distance_from_earth = math.hypot(*(p - e for p, e in zip(vec, earth_vec, strict=True)))
        planets.append(
            PlanetState(
                name=name,
                body_class=facts.body_class,
                x_au=vec[0],
                y_au=vec[1],
                z_au=vec[2],
                ecliptic_longitude_deg=_wrap_degrees(math.degrees(math.atan2(vec[1], vec[0]))),
                ecliptic_latitude_deg=math.degrees(
                    math.asin(vec[2] / distance_from_sun) if distance_from_sun else 0.0
                ),
                distance_from_sun_au=distance_from_sun,
                distance_from_earth_au=distance_from_earth,
                elongation_deg=0.0 if name == "earth" else _elongation_deg(vec, earth_vec),
                light_time_minutes=distance_from_earth * 8.316746397,
                orbital_period_days=facts.orbital_period_days,
                radius_km=facts.radius_km,
                display_color=facts.display_color,
            )
        )
    return EphemerisSnapshot(
        computed_at=at,
        source=EPHEMERIS_SOURCE,
        valid_range="1800-2050 CE",
        planets=planets,
    )

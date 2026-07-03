"""Registry of learned space-weather metrics.

Each spec names the recorded series, which side of the distribution is
anomalous, and the published operational floor the adaptive threshold may
tighten but never relax below (NOAA G/R/S scale entry points and the
conventional 600 km/s / -10 nT solar-wind gates already used by the static
spot detectors).
"""

from dataclasses import dataclass
from typing import Literal

Direction = Literal["high", "low"]


@dataclass(frozen=True)
class MetricSpec:
    key: str
    title: str
    unit: str
    direction: Direction
    published_floor: float
    body: Literal["sun", "earth", "interplanetary"]
    minimum: float | None = None
    maximum: float | None = None


KP = MetricSpec(
    key="kp",
    title="Planetary K-index",
    unit="Kp",
    direction="high",
    published_floor=5.0,  # NOAA G1
    body="earth",
    minimum=0.0,
    maximum=9.0,
)
XRAY_FLUX = MetricSpec(
    key="xray_long_wm2",
    title="GOES X-ray flux (0.1-0.8 nm)",
    unit="W/m^2",
    direction="high",
    published_floor=1e-5,  # M-class / NOAA R1
    body="sun",
    minimum=0.0,
)
SOLAR_WIND_SPEED = MetricSpec(
    key="solar_wind_speed_kms",
    title="Solar wind speed",
    unit="km/s",
    direction="high",
    published_floor=600.0,
    body="interplanetary",
    minimum=0.0,
)
SOLAR_WIND_BZ = MetricSpec(
    key="solar_wind_bz_nt",
    title="IMF Bz",
    unit="nT",
    direction="low",
    published_floor=-10.0,
    body="interplanetary",
)
PROTON_FLUX = MetricSpec(
    key="proton_flux_10mev_pfu",
    title=">=10 MeV proton flux",
    unit="pfu",
    direction="high",
    published_floor=10.0,  # NOAA S1
    body="earth",
    minimum=0.0,
)

METRIC_SPECS: tuple[MetricSpec, ...] = (
    KP,
    XRAY_FLUX,
    SOLAR_WIND_SPEED,
    SOLAR_WIND_BZ,
    PROTON_FLUX,
)
METRICS_BY_KEY: dict[str, MetricSpec] = {spec.key: spec for spec in METRIC_SPECS}

# Series smooth enough for short-horizon trend extrapolation to beat guessing.
# X-ray flux and proton flux are too impulsive for a linear model to forecast
# honestly, so the system only scores models where the approach is defensible.
FORECASTABLE_METRICS: tuple[MetricSpec, ...] = (KP, SOLAR_WIND_SPEED)

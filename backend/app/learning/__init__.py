"""Self-improving statistical layer over the live space-weather feeds.

The scheduler continuously persists feed measurements (`recorder`), learns
per-metric climatology from that growing archive (`baselines`), issues
forecasts and scores them against what actually happened (`forecasts`), and
raises data-driven anomaly detections whose thresholds tighten as history
accumulates (`anomalies`).

Honesty contract: everything here is transparent statistics over recorded
samples — quantile baselines, damped-trend extrapolation, and measured
forecast error. "Improvement" is reported as numbers (sample depth, baseline
maturity, model error vs. a persistence control), never as an opaque claim.
"""

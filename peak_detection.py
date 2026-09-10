"""Noise-aware peak selection shared by spectroscopy workspaces."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, savgol_filter


DEFAULT_MAX_PEAKS = {
    "FTIR": 24,
    "XRD": 25,
    "UVVIS": 15,
    "RAMAN": 20,
    "GENERAL": 30,
}


def peak_polarity(technique: str, converted_transmittance: bool = False) -> str:
    """Return the scientifically conventional automatic peak direction."""
    if technique.upper() == "FTIR" and not converted_transmittance:
        return "down"
    return "up"


def _smoothed_detection_signal(values: np.ndarray) -> np.ndarray:
    """Lightly smooth for detection only, preserving the plotted data."""
    count = len(values)
    if count < 7:
        return values.copy()
    window = min(21, max(5, (count // 150) * 2 + 1))
    window = min(window, count if count % 2 else count - 1)
    if window < 5:
        return values.copy()
    return savgol_filter(values, window, min(2, window - 1), mode="interp")


def noise_adaptive_peak_indices(
    y,
    *,
    direction: str = "up",
    maximum: int = 30,
    prominence: float | None = None,
    minimum_height: float | None = None,
):
    """Find a restrained set of significant peaks on arbitrary signal scales.

    Automatic prominence combines a robust signal span with a derivative-based
    noise estimate. The strongest candidates are retained if more than the
    requested maximum survive.
    """
    values = np.asarray(y, dtype=float)
    finite = np.isfinite(values)
    if np.count_nonzero(finite) < 5:
        return np.asarray([], dtype=int), {}
    if not np.all(finite):
        positions = np.arange(len(values))
        values = np.interp(positions, positions[finite], values[finite])
    detected = _smoothed_detection_signal(values)
    search = detected if direction == "up" else -detected

    q05, q95 = np.percentile(search, [5, 95])
    robust_span = float(q95 - q05)
    if robust_span <= np.finfo(float).eps:
        robust_span = float(np.ptp(search))
    differences = np.diff(search)
    derivative_mad = float(np.median(np.abs(differences - np.median(differences))))
    noise = 1.4826 * derivative_mad / np.sqrt(2.0)
    automatic_prominence = max(0.08 * robust_span, 6.0 * noise, np.finfo(float).eps)
    used_prominence = automatic_prominence if prominence is None else max(float(prominence), 0.0)
    # Keep genuinely close spectral features eligible; the prominence ranking
    # and explicit maximum handle label density separately.
    distance = max(2, len(search) // 500)

    kwargs = {"prominence": used_prominence, "distance": distance}
    if minimum_height is not None:
        kwargs["height"] = minimum_height if direction == "up" else -minimum_height
    peaks, properties = find_peaks(search, **kwargs)
    maximum = max(1, int(maximum))
    if len(peaks) > maximum:
        candidate_count = len(peaks)
        keep = np.argsort(properties["prominences"])[-maximum:]
        peaks = peaks[keep]
        properties = {
            key: np.asarray(value)[keep]
            for key, value in properties.items()
            if np.asarray(value).shape[:1] == (candidate_count,)
        }
    order = np.argsort(peaks)
    peaks = peaks[order]
    for key, value in tuple(properties.items()):
        array = np.asarray(value)
        if array.shape[:1] == (len(order),):
            properties[key] = array[order]
    properties["used_prominence"] = used_prominence
    return peaks, properties


def local_extremum_index(x, y, x_click: float, *, direction: str, fraction: float = 0.025):
    """Snap a canvas click to a nearby upward peak or downward valley."""
    x_values, y_values = np.asarray(x, float), np.asarray(y, float)
    finite = np.isfinite(x_values) & np.isfinite(y_values)
    if not np.any(finite):
        raise ValueError("No finite spectrum points are available.")
    original_positions = np.flatnonzero(finite)
    x_values, y_values = x_values[finite], y_values[finite]
    span = float(np.ptp(x_values))
    half_window = max(span * fraction, np.median(np.abs(np.diff(np.sort(x_values)))) * 3)
    candidates = np.flatnonzero(np.abs(x_values - float(x_click)) <= half_window)
    if not len(candidates):
        return int(original_positions[np.abs(x_values - float(x_click)).argmin()])
    local = y_values[candidates]
    selected = candidates[np.argmax(local) if direction == "up" else np.argmin(local)]
    return int(original_positions[selected])

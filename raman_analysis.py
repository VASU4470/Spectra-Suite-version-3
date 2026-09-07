"""Testable Raman peak measurements."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks, peak_widths


@dataclass(frozen=True)
class RamanPeak:
    shift_cm1: float
    intensity: float
    fwhm_cm1: float
    area: float


def measure_raman_peaks(x, y, prominence: float = 0.0, minimum_height=None):
    """Find upward Raman bands and estimate FWHM and local integrated area."""
    x_arr, y_arr = np.asarray(x, float), np.asarray(y, float)
    valid = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_arr, y_arr = x_arr[valid], y_arr[valid]
    order = np.argsort(x_arr)
    x_arr, y_arr = x_arr[order], y_arr[order]
    if len(x_arr) < 3:
        return []
    indices, _ = find_peaks(y_arr, prominence=max(0.0, float(prominence)), height=minimum_height)
    if not len(indices):
        return []
    widths, _height, left_ips, right_ips = peak_widths(y_arr, indices, rel_height=0.5)
    sample_index = np.arange(len(x_arr), dtype=float)
    left_x = np.interp(left_ips, sample_index, x_arr)
    right_x = np.interp(right_ips, sample_index, x_arr)
    results = []
    for index, left, right in zip(indices, left_x, right_x):
        mask = (x_arr >= left) & (x_arr <= right)
        if np.count_nonzero(mask) >= 2:
            baseline = np.interp(x_arr[mask], [left, right], [y_arr[mask][0], y_arr[mask][-1]])
            area = float(np.trapezoid(np.clip(y_arr[mask] - baseline, 0, None), x_arr[mask]))
        else:
            area = 0.0
        results.append(RamanPeak(float(x_arr[index]), float(y_arr[index]), float(right-left), area))
    return results


def nearest_peak_ratio(peaks, first_shift: float, second_shift: float):
    """Return I(first)/I(second) using the closest detected band to each target."""
    if not peaks:
        raise ValueError("No Raman peaks have been detected.")
    first = min(peaks, key=lambda item: abs(item.shift_cm1 - first_shift))
    second = min(peaks, key=lambda item: abs(item.shift_cm1 - second_shift))
    if second.intensity == 0:
        raise ValueError("The denominator peak has zero intensity.")
    return first, second, float(first.intensity / second.intensity)

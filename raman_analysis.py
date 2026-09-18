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
    if x_arr.ndim != 1 or y_arr.ndim != 1 or x_arr.shape != y_arr.shape:
        raise ValueError("Raman X and Y must be matching one-dimensional arrays.")
    valid = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_arr, y_arr = x_arr[valid], y_arr[valid]
    order = np.argsort(x_arr)
    x_arr, y_arr = x_arr[order], y_arr[order]
    if len(x_arr) < 3:
        return []
    if np.any(np.diff(x_arr) <= 0):
        raise ValueError("Raman shifts must be unique; combine repeated measurements first.")
    indices, _ = find_peaks(y_arr, prominence=max(0.0, float(prominence)), height=minimum_height)
    if not len(indices):
        return []
    widths, _height, left_ips, right_ips = peak_widths(y_arr, indices, rel_height=0.5)
    sample_index = np.arange(len(x_arr), dtype=float)
    left_x = np.interp(left_ips, sample_index, x_arr)
    right_x = np.interp(right_ips, sample_index, x_arr)
    results = []
    for index, left, right in zip(indices, left_x, right_x):
        interior = x_arr[(x_arr > left) & (x_arr < right)]
        area_x = np.r_[left, interior, right]
        area_y = np.interp(area_x, x_arr, y_arr)
        baseline = np.interp(area_x, [left, right], [area_y[0], area_y[-1]])
        area = float(np.trapezoid(np.clip(area_y - baseline, 0, None), area_x))
        results.append(RamanPeak(float(x_arr[index]), float(y_arr[index]), float(right-left), area))
    return results


def nearest_peak_ratio(peaks, first_shift: float, second_shift: float, tolerance=10.0):
    """Return a ratio only for two distinct bands inside the requested tolerance."""
    if not peaks:
        raise ValueError("No Raman peaks have been detected.")
    first = min(peaks, key=lambda item: abs(item.shift_cm1 - first_shift))
    second = min(peaks, key=lambda item: abs(item.shift_cm1 - second_shift))
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Peak matching tolerance must be positive and finite.")
    if not np.isfinite(first_shift) or not np.isfinite(second_shift):
        raise ValueError("Ratio target shifts must be finite.")
    if abs(first.shift_cm1-first_shift) > tolerance or abs(second.shift_cm1-second_shift) > tolerance:
        raise ValueError("No detected band lies within the matching tolerance of one or both targets.")
    if first is second:
        raise ValueError("Both targets select the same band. Choose two distinct peaks.")
    if second.intensity <= 0:
        raise ValueError("The denominator peak must have positive intensity.")
    return first, second, float(first.intensity / second.intensity)

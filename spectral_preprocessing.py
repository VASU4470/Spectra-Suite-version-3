"""Conservative, testable preprocessing helpers for optical spectra."""

from __future__ import annotations

import numpy as np


def trim_noisy_edges(x, y, *, maximum_fraction=0.10):
    """Trim only end regions whose point-to-point noise greatly exceeds the centre.

    The operation is deliberately conservative: at most ten percent is removed
    from either end and a clean spectrum is returned unchanged.  It is intended
    for display cleanup, not as a substitute for inspecting the raw data.
    """
    x_arr, y_arr = np.asarray(x, float), np.asarray(y, float)
    finite = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_arr, y_arr = x_arr[finite], y_arr[finite]
    n = len(y_arr)
    if n < 50:
        return x_arr, y_arr

    differences = np.abs(np.diff(y_arr))
    centre = differences[int(0.2 * len(differences)):int(0.8 * len(differences))]
    centre_median = float(np.median(centre))
    centre_mad = float(np.median(np.abs(centre - centre_median)))
    scale = max(centre_median + 6.0 * centre_mad, 3.0 * centre_median, np.finfo(float).eps)
    window = max(7, min(31, n // 40))
    maximum = max(window, int(n * float(maximum_fraction)))

    def local_noise(start):
        stop = min(len(differences), start + window)
        return float(np.median(differences[start:stop])) if stop > start else 0.0

    left = 0
    if local_noise(0) > scale:
        for candidate in range(1, maximum + 1):
            if local_noise(candidate) <= scale and local_noise(candidate + window) <= scale:
                left = candidate
                break

    right = n
    reversed_diff = differences[::-1]
    def right_noise(start):
        stop = min(len(reversed_diff), start + window)
        return float(np.median(reversed_diff[start:stop])) if stop > start else 0.0

    if right_noise(0) > scale:
        for candidate in range(1, maximum + 1):
            if right_noise(candidate) <= scale and right_noise(candidate + window) <= scale:
                right = n - candidate
                break

    if right - left < max(20, int(0.75 * n)):
        return x_arr, y_arr
    return x_arr[left:right], y_arr[left:right]


def subtract_reference(x, y, reference_x, reference_y, multiplier=1.0):
    """Subtract an interpolated reference spectrum on the sample X grid."""
    x_arr, y_arr = np.asarray(x, float), np.asarray(y, float)
    ref_x, ref_y = np.asarray(reference_x, float), np.asarray(reference_y, float)
    finite = np.isfinite(ref_x) & np.isfinite(ref_y)
    ref_x, ref_y = ref_x[finite], ref_y[finite]
    if len(ref_x) < 2:
        raise ValueError("The selected baseline/reference needs at least two numeric points.")
    order = np.argsort(ref_x)
    return y_arr - np.interp(x_arr, ref_x[order], ref_y[order]) * float(multiplier)

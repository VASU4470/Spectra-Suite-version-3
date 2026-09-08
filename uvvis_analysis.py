"""Numerical helpers for UV-Vis spectroscopy analysis.

The functions in this module contain no Qt code so that the scientific
calculations can be unit-tested independently of the desktop interface.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


HC_EV_NM = 1239.841984


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    r_squared: float
    x_start: float
    x_end: float
    points: int
    slope_std: float = float("nan")
    intercept_std: float = float("nan")
    slope_intercept_covariance: float = float("nan")


@dataclass(frozen=True)
class TaucResult:
    band_gap_ev: float
    exponent: float
    fit: LinearFit
    band_gap_std_ev: float = float("nan")
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class UrbachResult:
    urbach_energy_ev: float
    fit: LinearFit


TAUC_EXPONENTS = {
    "Direct allowed": 2.0,
    "Indirect allowed": 0.5,
    "Direct forbidden": 2.0 / 3.0,
    "Indirect forbidden": 1.0 / 3.0,
}


def spectral_axis_to_energy(x, axis_kind: str):
    """Return photon energy (eV) for wavelength, energy, or wavenumber X data."""
    values = np.asarray(x, dtype=float)
    key = axis_kind.lower()
    with np.errstate(divide="ignore", invalid="ignore"):
        if key == "wavelength (nm)":
            energy = HC_EV_NM / values
        elif key == "photon energy (ev)":
            energy = values.copy()
        elif key == "wavenumber (cm⁻¹)":
            energy = values / 8065.544005
        else:
            raise ValueError(f"Unsupported spectral axis: {axis_kind}")
    return energy


def signal_to_absorption(y, signal_kind: str, thickness_um: float | None = None):
    """Convert a measured signal to alpha or a proportional absorption proxy.

    Absorbance is converted to the absorption coefficient when a positive film
    thickness is supplied. Reflectance is converted with Kubelka-Munk F(R).
    """
    values = np.asarray(y, dtype=float)
    key = signal_kind.lower()
    with np.errstate(divide="ignore", invalid="ignore"):
        if key == "absorbance":
            absorbance = values
        elif key == "transmittance (%)":
            absorbance = -np.log10(values / 100.0)
        elif key == "transmittance (fraction)":
            absorbance = -np.log10(values)
        elif key == "reflectance (%)":
            reflectance = values / 100.0
            return (1.0 - reflectance) ** 2 / (2.0 * reflectance), "F(R)"
        elif key == "reflectance (fraction)":
            return (1.0 - values) ** 2 / (2.0 * values), "F(R)"
        elif key == "absorption coefficient (cm⁻¹)":
            return values.copy(), "α (cm⁻¹)"
        else:
            raise ValueError(f"Unsupported UV-Vis signal: {signal_kind}")

    if thickness_um is not None and thickness_um > 0:
        alpha = 2.302585093 * absorbance / (thickness_um * 1e-4)
        return alpha, "α (cm⁻¹)"
    return absorbance, "relative absorption"


def _finite_sorted(x, y):
    x_arr, y_arr = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_arr, y_arr = x_arr[mask], y_arr[mask]
    order = np.argsort(x_arr)
    return x_arr[order], y_arr[order]


def linear_fit(x, y, start: float, end: float) -> LinearFit:
    low, high = sorted((float(start), float(end)))
    x_arr, y_arr = _finite_sorted(x, y)
    mask = (x_arr >= low) & (x_arr <= high)
    x_fit, y_fit = x_arr[mask], y_arr[mask]
    if len(x_fit) < 3:
        raise ValueError("The selected fit range must contain at least three points.")
    slope, intercept = np.polyfit(x_fit, y_fit, 1)
    predicted = slope * x_fit + intercept
    residual = float(np.sum((y_fit - predicted) ** 2))
    total = float(np.sum((y_fit - np.mean(y_fit)) ** 2))
    r_squared = 1.0 - residual / total if total > 0 else 1.0
    slope_std = intercept_std = covariance_value = float("nan")
    try:
        _coefficients, covariance = np.polyfit(x_fit, y_fit, 1, cov=True)
        slope_std, intercept_std = np.sqrt(np.diag(covariance))
        covariance_value = float(covariance[0, 1])
    except (ValueError, np.linalg.LinAlgError):
        pass
    return LinearFit(
        float(slope), float(intercept), r_squared, low, high, len(x_fit),
        float(slope_std), float(intercept_std), covariance_value,
    )


def correct_absorption_baseline(energy_ev, absorption, start, end, method):
    """Subtract a constant or linear pre-edge absorption baseline."""
    energy = np.asarray(energy_ev, float)
    alpha = np.asarray(absorption, float)
    key = method.lower()
    if key.startswith("none"):
        return alpha.copy(), np.zeros_like(alpha)
    low, high = sorted((float(start), float(end)))
    mask = np.isfinite(energy) & np.isfinite(alpha) & (energy >= low) & (energy <= high)
    if np.count_nonzero(mask) < 3:
        raise ValueError("The pre-edge baseline range must contain at least three points.")
    if key.startswith("constant"):
        baseline = np.full_like(alpha, float(np.median(alpha[mask])))
    elif key.startswith("linear"):
        slope, intercept = np.polyfit(energy[mask], alpha[mask], 1)
        baseline = slope * energy + intercept
    else:
        raise ValueError(f"Unsupported baseline method: {method}")
    return alpha - baseline, baseline


def tauc_transform(energy_ev, absorption, transition: str):
    exponent = TAUC_EXPONENTS.get(transition)
    if exponent is None:
        raise ValueError(f"Unsupported transition: {transition}")
    energy = np.asarray(energy_ev, float)
    alpha = np.asarray(absorption, float)
    with np.errstate(invalid="ignore", over="ignore"):
        ordinate = np.power(np.clip(alpha * energy, 0, None), exponent)
    return ordinate, exponent


def fit_tauc(energy_ev, absorption, transition: str, start: float, end: float):
    ordinate, exponent = tauc_transform(energy_ev, absorption, transition)
    fit = linear_fit(energy_ev, ordinate, start, end)
    if fit.slope <= 0:
        raise ValueError("The selected Tauc region does not have a positive slope.")
    band_gap = -fit.intercept / fit.slope
    if not np.isfinite(band_gap) or band_gap <= 0:
        raise ValueError("The selected range does not produce a physical positive intercept.")
    gap_std = float("nan")
    if np.isfinite(fit.slope_std) and np.isfinite(fit.intercept_std):
        derivative_slope = fit.intercept / fit.slope ** 2
        derivative_intercept = -1.0 / fit.slope
        variance = (
            derivative_slope ** 2 * fit.slope_std ** 2
            + derivative_intercept ** 2 * fit.intercept_std ** 2
        )
        if np.isfinite(fit.slope_intercept_covariance):
            variance += (
                2.0 * derivative_slope * derivative_intercept
                * fit.slope_intercept_covariance
            )
        gap_std = float(np.sqrt(max(0.0, variance)))
    warnings = []
    if fit.r_squared < 0.98:
        warnings.append("The selected region has R² below 0.98; adjust the linear range.")
    if band_gap >= fit.x_start:
        warnings.append("The y=0 intercept is not below the fitted region; the range is unsuitable.")
    if fit.x_start - band_gap > 2.0 * max(fit.x_end - fit.x_start, np.finfo(float).eps):
        warnings.append("The y=0 intercept is a long extrapolation from the fitted region.")
    return TaucResult(float(band_gap), exponent, fit, gap_std, tuple(warnings)), ordinate


def suggest_tauc_range(energy_ev, absorption, transition: str):
    """Suggest a high-linearity positive-slope region for user review."""
    ordinate, _exponent = tauc_transform(energy_ev, absorption, transition)
    energy, ordinate = _finite_sorted(energy_ev, ordinate)
    valid = np.isfinite(ordinate) & (ordinate > 0)
    energy, ordinate = energy[valid], ordinate[valid]
    n = len(energy)
    if n < 20:
        raise ValueError("At least 20 positive Tauc points are needed to suggest a range.")
    candidates = []
    for fraction in (0.08, 0.12, 0.18, 0.25):
        width = max(12, int(n * fraction))
        if width >= n:
            continue
        stride = max(1, width // 8)
        for start_index in range(0, n - width + 1, stride):
            xs = energy[start_index:start_index + width]
            ys = ordinate[start_index:start_index + width]
            slope, intercept = np.polyfit(xs, ys, 1)
            if slope <= 0:
                continue
            gap = -intercept / slope
            if not np.isfinite(gap) or gap <= 0 or gap >= xs[0]:
                continue
            predicted = slope * xs + intercept
            total = float(np.sum((ys - np.mean(ys)) ** 2))
            if total <= 0:
                continue
            r2 = 1.0 - float(np.sum((ys - predicted) ** 2)) / total
            extrapolation = (xs[0] - gap) / max(xs[-1] - xs[0], np.finfo(float).eps)
            if extrapolation > 2.0:
                continue
            signal_span = float(np.ptp(ys)) / max(float(np.ptp(ordinate)), np.finfo(float).eps)
            score = r2 + min(signal_span, 0.25) * 0.08 - extrapolation * 0.002
            candidates.append((score, float(xs[0]), float(xs[-1])))
    if not candidates:
        raise ValueError("No defensible positive-slope Tauc region was found automatically.")
    _score, start, end = max(candidates)
    return start, end


def fit_urbach(energy_ev, absorption, start: float, end: float):
    energy = np.asarray(energy_ev, float)
    alpha = np.asarray(absorption, float)
    log_alpha = np.full_like(alpha, np.nan)
    positive = alpha > 0
    log_alpha[positive] = np.log(alpha[positive])
    fit = linear_fit(energy, log_alpha, start, end)
    if fit.slope <= 0:
        raise ValueError("The selected Urbach region does not have a positive slope.")
    return UrbachResult(float(1.0 / fit.slope), fit), log_alpha

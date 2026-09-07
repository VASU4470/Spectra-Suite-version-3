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


@dataclass(frozen=True)
class TaucResult:
    band_gap_ev: float
    exponent: float
    fit: LinearFit


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
    return LinearFit(float(slope), float(intercept), r_squared, low, high, len(x_fit))


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
    return TaucResult(float(band_gap), exponent, fit), ordinate


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

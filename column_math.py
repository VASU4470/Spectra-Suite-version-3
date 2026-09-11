"""Safe column formulas and optical-signal conversions.

The formula evaluator intentionally accepts only numeric column references,
arithmetic operators, and the functions listed in ``FORMULA_HELP``.  It never
passes user text to Python's ``eval`` or ``exec``.
"""

from __future__ import annotations

import ast
import re

import numpy as np
from scipy.signal import savgol_filter

from processing import baseline_als


FORMULA_HELP = (
    "Use C1, C2, ... for table columns. Examples: C2 + C3; C2 * 5; "
    "normalize(C2); baseline(C2); smooth(C2, 11); transmittance(C2); "
    "absorbance(C2); km(C2). km() expects reflectance as a fraction; use "
    "km(C2 / 100) for percent reflectance. Available functions: abs, sqrt, log, log10, "
    "exp, clip, normalize, zscore, smooth, baseline, transmittance, "
    "absorbance, and km."
)


class FormulaError(ValueError):
    """Raised when a column formula is invalid or unsafe."""


def absorbance_to_percent_transmittance(values):
    """Convert base-10 absorbance to percent transmittance."""
    absorbance_values = np.asarray(values, dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        result = 100.0 * np.power(10.0, -absorbance_values)
    return result


def percent_transmittance_to_absorbance(values):
    """Convert percent transmittance to base-10 absorbance."""
    transmittance_values = np.asarray(values, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = -np.log10(transmittance_values / 100.0)
    result[(transmittance_values <= 0) | (transmittance_values > 100)] = np.nan
    return result


def kubelka_munk(values, *, percent=False):
    """Return Kubelka-Munk F(R) from diffuse reflectance.

    Reflectance must be a fraction in (0, 1] unless ``percent`` is true.
    Values outside the physical range are returned as NaN rather than silently
    clipped into a plausible-looking result.
    """
    reflectance = np.asarray(values, dtype=float)
    if percent:
        reflectance = reflectance / 100.0
    valid = np.isfinite(reflectance) & (reflectance > 0.0) & (reflectance <= 1.0)
    result = np.full_like(reflectance, np.nan, dtype=float)
    result[valid] = (1.0 - reflectance[valid]) ** 2 / (2.0 * reflectance[valid])
    return result


def apply_optical_transform(values, transform):
    """Apply a named, reversible-on-raw-data display transformation."""
    key = str(transform or "none").strip().lower()
    if key in {"", "none", "original"}:
        return np.asarray(values, dtype=float).copy()
    if key == "absorbance_to_percent_transmittance":
        return absorbance_to_percent_transmittance(values)
    if key == "percent_transmittance_to_absorbance":
        return percent_transmittance_to_absorbance(values)
    if key == "reflectance_fraction_to_kubelka_munk":
        return kubelka_munk(values, percent=False)
    if key == "reflectance_percent_to_kubelka_munk":
        return kubelka_munk(values, percent=True)
    raise ValueError(f"Unsupported optical transform: {transform}")


def _finite_fill(values):
    array = np.asarray(values, dtype=float)
    finite = np.isfinite(array)
    if np.count_nonzero(finite) < 3:
        raise FormulaError("This function needs at least three numeric values.")
    positions = np.arange(len(array), dtype=float)
    filled = np.interp(positions, positions[finite], array[finite])
    return array, filled, finite


def _normalize(values):
    array = np.asarray(values, dtype=float)
    finite = np.isfinite(array)
    if not np.any(finite):
        return np.full_like(array, np.nan)
    low, high = float(np.min(array[finite])), float(np.max(array[finite]))
    if high == low:
        result = np.zeros_like(array)
    else:
        result = (array - low) / (high - low)
    result[~finite] = np.nan
    return result


def _zscore(values):
    array = np.asarray(values, dtype=float)
    finite = np.isfinite(array)
    if not np.any(finite):
        return np.full_like(array, np.nan)
    mean, deviation = float(np.mean(array[finite])), float(np.std(array[finite]))
    result = array - mean if deviation == 0 else (array - mean) / deviation
    result[~finite] = np.nan
    return result


def _smooth(values, points=11):
    _, filled, finite = _finite_fill(values)
    window = int(points)
    if window < 3:
        raise FormulaError("smooth() needs at least three points.")
    if window % 2 == 0:
        window += 1
    if window >= len(filled):
        window = len(filled) - 1 if len(filled) % 2 == 0 else len(filled)
    if window < 3:
        raise FormulaError("The column is too short for smoothing.")
    polynomial_order = min(3, window - 1)
    result = savgol_filter(filled, window, polynomial_order)
    result[~finite] = np.nan
    return result


def _baseline_correct(values, stiffness=8.0, asymmetry=0.05):
    _, filled, finite = _finite_fill(values)
    stiffness = float(stiffness)
    asymmetry = float(asymmetry)
    if not 1.0 <= stiffness <= 14.0:
        raise FormulaError("baseline() stiffness must be between 1 and 14.")
    if not 0.0001 <= asymmetry <= 0.9999:
        raise FormulaError("baseline() asymmetry must be between 0.0001 and 0.9999.")
    result = filled - baseline_als(filled, lam=10.0 ** stiffness, p=asymmetry)
    result[~finite] = np.nan
    return result


def _clip(values, low, high):
    return np.clip(np.asarray(values, dtype=float), float(low), float(high))


_FUNCTIONS = {
    "abs": np.abs,
    "sqrt": np.sqrt,
    "log": np.log,
    "log10": np.log10,
    "exp": np.exp,
    "clip": _clip,
    "normalize": _normalize,
    "zscore": _zscore,
    "smooth": _smooth,
    "baseline": _baseline_correct,
    "transmittance": absorbance_to_percent_transmittance,
    "absorbance": percent_transmittance_to_absorbance,
    "km": kubelka_munk,
}


_BINARY_OPERATORS = {
    ast.Add: np.add,
    ast.Sub: np.subtract,
    ast.Mult: np.multiply,
    ast.Div: np.divide,
    ast.Pow: np.power,
    ast.Mod: np.mod,
}
_UNARY_OPERATORS = {ast.UAdd: lambda value: value, ast.USub: np.negative}
_COLUMN_PATTERN = re.compile(r"C([1-9][0-9]*)", re.IGNORECASE)


def evaluate_column_formula(expression, columns):
    """Evaluate a restricted vector formula against equally sized columns."""
    arrays = [np.asarray(column, dtype=float) for column in columns]
    if not arrays:
        raise FormulaError("The table does not contain any columns.")
    length = len(arrays[0])
    if any(len(array) != length for array in arrays):
        raise FormulaError("Every source column must have the same row count.")
    try:
        tree = ast.parse(str(expression).strip(), mode="eval")
    except SyntaxError as error:
        raise FormulaError("The formula syntax is not valid.") from error
    if sum(1 for _node in ast.walk(tree)) > 80:
        raise FormulaError("The formula is too complex.")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise FormulaError("Only numeric constants are allowed.")
            return float(node.value)
        if isinstance(node, ast.Name):
            match = _COLUMN_PATTERN.fullmatch(node.id)
            if not match:
                raise FormulaError(f"Unknown name '{node.id}'. Use C1, C2, ... for columns.")
            index = int(match.group(1)) - 1
            if not 0 <= index < len(arrays):
                raise FormulaError(f"{node.id.upper()} is outside the current table.")
            return arrays[index]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            with np.errstate(all="ignore"):
                return _BINARY_OPERATORS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(node.op)](visit(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = _FUNCTIONS.get(node.func.id.lower())
            if function is None:
                raise FormulaError(f"Function '{node.func.id}' is not available.")
            if node.keywords:
                raise FormulaError("Formula functions do not accept named arguments.")
            try:
                with np.errstate(all="ignore"):
                    return function(*(visit(argument) for argument in node.args))
            except FormulaError:
                raise
            except (TypeError, ValueError, OverflowError) as error:
                raise FormulaError(f"Could not calculate {node.func.id}(): {error}") from error
        raise FormulaError("The formula contains an unsupported operation.")

    result = np.asarray(visit(tree), dtype=float)
    if result.ndim == 0:
        result = np.full(length, float(result))
    if result.shape != (length,):
        raise FormulaError("The formula must produce one value per table row.")
    result[~np.isfinite(result)] = np.nan
    return result

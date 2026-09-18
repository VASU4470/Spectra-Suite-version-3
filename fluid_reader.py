"""Reader for ASCII Tecplot POINT files used by the fluid-dynamics workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
from scipy.interpolate import RegularGridInterpolator


@dataclass
class TecplotField:
    path: Path
    title: str
    zone: str
    variables: tuple[str, ...]
    i: int
    j: int
    k: int
    values: np.ndarray

    @property
    def x(self): return self.values[..., 0]

    @property
    def y(self): return self.values[..., 1]

    def variable(self, name):
        try: index = self.variables.index(name)
        except ValueError as error: raise KeyError(name) from error
        return self.values[..., index]

    @property
    def scalar_variables(self): return self.variables[2:]


def read_tecplot(path):
    """Read one structured ASCII Tecplot zone using POINT packing."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines: raise ValueError("The Tecplot file is empty.")
    title = path.stem; variables = []; zone = "Zone 1"; dims = {"I": 0, "J": 1, "K": 1}
    data_start = None; in_variables = False
    for index, line in enumerate(lines):
        upper = line.upper()
        if "TITLE" in upper:
            match = re.search(r'"([^"]+)"', line)
            if match: title = match.group(1)
        if "ZONE" in upper:
            in_variables = False
            match = re.search(r'T\s*=\s*"([^"]+)"', line, re.I)
            if match: zone = match.group(1)
        else:
            if "VARIABLES" in upper:
                in_variables = True
            if in_variables:
                variables.extend(re.findall(r'"([^"]+)"', line))
        for key, value in re.findall(r'\b([IJK])\s*=\s*(\d+)', line, re.I):
            dims[key.upper()] = int(value)
        compact = re.sub(r"\s+", "", upper)
        if "F=POINT" in compact or "DATAPACKING=POINT" in compact:
            data_start = index + 1
            break
    if data_start is None: raise ValueError("Only ASCII Tecplot POINT files are supported.")
    if len(variables) < 2: raise ValueError("The file must define at least X and Y variables.")
    try: data = np.loadtxt(lines[data_start:], dtype=float)
    except ValueError as error: raise ValueError(f"Could not parse Tecplot numeric data: {error}") from error
    if data.ndim == 1: data = data.reshape(1, -1)
    expected = dims["I"] * dims["J"] * dims["K"]
    if expected <= 0 or len(data) != expected:
        raise ValueError(f"ZONE dimensions expect {expected} points, but {len(data)} were found.")
    if data.shape[1] != len(variables):
        raise ValueError(f"The file defines {len(variables)} variables but has {data.shape[1]} columns.")
    if dims["K"] != 1:
        raise ValueError("This workspace plots 2D zones (K=1). Export a 2D slice of the volume first.")
    if not np.all(np.isfinite(data)):
        raise ValueError("Tecplot coordinates and field values must be finite.")
    # Cartesian files from different exporters may use either point ordering.
    # Reconstruct from coordinates, retaining the workspace's [x, y] convention.
    x_values, xi = np.unique(data[:, 0], return_inverse=True)
    y_values, yi = np.unique(data[:, 1], return_inverse=True)
    if len(x_values) * len(y_values) == expected:
        if len(np.unique(xi * len(y_values) + yi)) != expected:
            raise ValueError("The structured grid contains duplicate coordinate pairs.")
        values = np.empty((len(x_values), len(y_values), len(variables)))
        values[xi, yi] = data
    else:
        # Ordered curvilinear Tecplot POINT zones use I as the fastest index.
        values = data.reshape(dims["J"], dims["I"], len(variables)).transpose(1, 0, 2)
    return TecplotField(path, title, zone, tuple(variables), dims["I"], dims["J"], dims["K"], values)


def aligned_difference(first, second, variable):
    """Return second-first on the first structured grid inside the shared domain."""
    first_value, second_value = first.variable(variable), second.variable(variable)
    if first.values.shape[:2] == second.values.shape[:2] and np.allclose(first.x, second.x) and np.allclose(first.y, second.y):
        return first.x, first.y, second_value - first_value
    second_x = second.x[:, 0]; second_y = second.y[0, :]
    if not (np.allclose(second.x, second_x[:, None]) and
            np.allclose(second.y, second_y[None, :]) and
            np.allclose(first.x, first.x[:, :1]) and
            np.allclose(first.y, first.y[:1, :])):
        raise ValueError("Different-grid interpolation requires rectilinear X/Y grids.")
    if np.any(np.diff(second_x) <= 0) or np.any(np.diff(second_y) <= 0):
        raise ValueError("Shifted-grid differences require increasing structured X/Y coordinates.")
    row_mask = (first.x[:, 0] >= second_x.min()) & (first.x[:, 0] <= second_x.max())
    col_mask = (first.y[0, :] >= second_y.min()) & (first.y[0, :] <= second_y.max())
    if not np.any(row_mask) or not np.any(col_mask):
        raise ValueError("The selected field grids do not overlap.")
    target_x = first.x[np.ix_(row_mask, col_mask)]
    target_y = first.y[np.ix_(row_mask, col_mask)]
    target_first = first_value[np.ix_(row_mask, col_mask)]
    interpolator = RegularGridInterpolator((second_x, second_y), second_value, bounds_error=True)
    points = np.column_stack((target_x.ravel(), target_y.ravel()))
    target_second = interpolator(points).reshape(target_x.shape)
    return target_x, target_y, target_second - target_first

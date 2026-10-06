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
    """Read Tecplot zones or headerless numeric tables containing a 2D grid.

    Ordinary TXT/CSV tables use their first two columns as X/Y and remaining
    columns as scalar fields. A text row immediately above the data supplies
    optional column names.
    """
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines: raise ValueError("The Tecplot file is empty.")
    title = path.stem; variables = []; zone = "Zone 1"
    dims = {"I": 0, "J": 0, "K": 1}; in_variables = False
    numeric_rows = []
    previous_text = None
    header = None
    started = False
    point_packing = True
    for index, line in enumerate(lines):
        upper = line.upper()
        if re.search(r"\bTITLE\b", upper):
            match = re.search(r'"([^"]+)"', line)
            if match: title = match.group(1)
        if re.search(r"\bZONE\b", upper):
            in_variables = False
            match = re.search(r'T\s*=\s*"([^"]+)"', line, re.I)
            if match: zone = match.group(1)
        if re.search(r"\bF\s*=\s*BLOCK\b|\bDATAPACKING\s*=\s*BLOCK\b", upper):
            point_packing = False
        else:
            if "VARIABLES" in upper:
                in_variables = True
            if in_variables:
                variables.extend(re.findall(r'"([^"]+)"', line))
        for key, value in re.findall(r'\b([IJK])\s*=\s*(\d+)', line, re.I):
            dims[key.upper()] = int(value)
        row = _numeric_values(line)
        if row is not None:
            if not started:
                started = True
                if previous_text and len(_header_tokens(previous_text)) == len(row):
                    header = _header_tokens(previous_text)
            numeric_rows.append(row)
        elif not started and line.strip() and not line.lstrip().startswith(("#", "!")):
            previous_text = line
    if not numeric_rows:
        raise ValueError("No numeric X/Y/field data rows were found in the text file.")
    if not point_packing:
        raise ValueError("Only ASCII Tecplot POINT packing and plain numeric tables are supported.")
    column_count = len(numeric_rows[0])
    if column_count < 3:
        raise ValueError("Fluid data needs at least three columns: X, Y, and one field.")
    if any(len(row) != column_count for row in numeric_rows):
        raise ValueError("Numeric data rows have different numbers of columns.")
    data = np.asarray(numeric_rows, dtype=float)
    if not variables or len(variables) != column_count:
        variables = header if header and len(header) == column_count else []
    if len(variables) != column_count:
        variables = ["X", "Y"] + [f"Field_{i}" for i in range(1, column_count - 1)]
    expected = dims["I"] * dims["J"] * dims["K"]
    if dims["K"] != 1:
        raise ValueError("This workspace plots 2D zones (K=1). Export a 2D slice of the volume first.")
    if expected > 0 and len(data) != expected:
        raise ValueError(f"ZONE dimensions expect {expected} points, but {len(data)} were found.")
    if expected <= 0:
        # Headerless tables do not carry Tecplot zone dimensions; infer a
        # structured Cartesian grid from their coordinate columns.
        x_count = len(np.unique(data[:, 0]))
        y_count = len(np.unique(data[:, 1]))
        if x_count * y_count != len(data):
            raise ValueError(
                "Could not infer a structured grid from the X/Y columns. "
                "Include Tecplot zone dimensions for curvilinear data."
            )
        dims["I"], dims["J"] = x_count, y_count
        expected = len(data)
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


def _numeric_values(line):
    """Return whitespace/comma separated numeric values or None for text."""
    cleaned = line.strip()
    if not cleaned or cleaned.startswith(("#", "!")):
        return None
    # Plain exports are commonly tab, comma, or semicolon delimited.
    tokens = [item for item in re.split(r"[\s,;]+", cleaned) if item]
    try:
        return [float(item) for item in tokens]
    except ValueError:
        return None


def _header_tokens(line):
    """Extract names from quoted Tecplot declarations or a plain header row."""
    quoted = re.findall(r'"([^"]+)"', line)
    if quoted:
        return quoted
    if "," in line or ";" in line:
        delimiter = "," if "," in line else ";"
        return [item.strip().strip("\"'") for item in line.split(delimiter) if item.strip()]
    return [item.strip().strip("\"'") for item in re.split(r"[\s,;]+", line.strip()) if item]


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

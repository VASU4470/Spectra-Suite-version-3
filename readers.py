"""Shared spectrum readers.

These functions replace helpers referenced by the application but omitted
from the original repository.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _numeric_columns(frame: pd.DataFrame, x_col: int, y_col: int):
    if min(x_col, y_col) < 0 or max(x_col, y_col) >= frame.shape[1]:
        return np.array([]), np.array([])
    values = frame.iloc[:, [x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if values.empty:
        return np.array([]), np.array([])
    return values.iloc[:, 0].to_numpy(float), values.iloc[:, 1].to_numpy(float)


def robust_read_spectrum(filepath):
    """Read the first two numeric columns from common spectrum formats.

    Text headers and malformed rows are ignored. Commas, tabs, semicolons and
    arbitrary whitespace are accepted, matching the behavior embedded in the
    earlier SpectraSuite FT-IR and XRD modules.
    """
    path = Path(filepath)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return _numeric_columns(pd.read_excel(path, header=None), 0, 1)

    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as stream:
        for line in stream:
            fields = line.replace(",", " ").replace("\t", " ").replace(";", " ").split()
            if len(fields) < 2:
                continue
            try:
                rows.append((float(fields[0]), float(fields[1])))
            except ValueError:
                continue

    if not rows:
        return np.array([]), np.array([])
    values = np.asarray(rows, dtype=float)
    finite = np.isfinite(values).all(axis=1)
    return values[finite, 0], values[finite, 1]


def read_generic_configured(
    filepath, *, delimiter=",", skip_rows=0, x_col=0, y_col=1
):
    """Read user-selected X/Y columns with an explicit parsing configuration."""
    path = Path(filepath)
    skip_rows = max(0, int(skip_rows))
    x_col, y_col = int(x_col), int(y_col)

    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, header=None, skiprows=skip_rows)
    else:
        separator = r"\s+" if delimiter == " " else delimiter
        frame = pd.read_csv(
            path,
            header=None,
            skiprows=skip_rows,
            sep=separator,
            engine="python",
            encoding_errors="ignore",
            on_bad_lines="skip",
        )
    return _numeric_columns(frame, x_col, y_col)

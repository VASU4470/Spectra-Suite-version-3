"""Discover one or more X/Y spectra inside common instrument data files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SpectrumDataset:
    """A named numeric X/Y dataset discovered in a source file."""

    name: str
    x: np.ndarray
    y: np.ndarray
    source: str
    sheet: str | None = None


def _clean_label(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _is_axis_label(value: str) -> bool:
    text = value.casefold().replace("%", "").strip()
    tokens = (
        "wavelength", "wavenumber", "raman shift", "intensity", "absorbance",
        "transmittance", "reflectance", "photon energy", "2theta", "2θ",
        "x", "y", "nm", "cm-1", "cm⁻¹", "a.u.", "counts",
    )
    return not text or text in tokens or any(text == token for token in tokens)


def _dataset_name(frame: pd.DataFrame, x_col: int, y_col: int, first_numeric: int,
                  base: str, sheet: str | None) -> str:
    candidates = []
    for row in range(max(0, first_numeric)):
        for col in (x_col, y_col):
            label = _clean_label(frame.iat[row, col])
            if label and not _is_axis_label(label):
                try:
                    float(label)
                except ValueError:
                    candidates.append(label)
    detail = candidates[0] if candidates else ""
    if sheet and sheet.casefold() not in {"sheet1", "data"}:
        detail = detail or sheet
    return f"{base} — {detail}" if detail and detail != base else base


def _numeric_pair(frame: pd.DataFrame, x_col: int, y_col: int, minimum: int):
    values = frame.iloc[:, [x_col, y_col]].apply(pd.to_numeric, errors="coerce")
    valid = values.notna().all(axis=1)
    if int(valid.sum()) < minimum:
        return None
    first = int(np.flatnonzero(valid.to_numpy())[0])
    clean = values.loc[valid]
    array = clean.to_numpy(float)
    finite = np.isfinite(array).all(axis=1)
    array = array[finite]
    if len(array) < minimum:
        return None
    return array[:, 0], array[:, 1], first


def _columns_match(frame: pd.DataFrame, first: int, second: int) -> bool:
    values = frame.iloc[:, [first, second]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(values) < 3:
        return False
    left, right = values.iloc[:, 0].to_numpy(float), values.iloc[:, 1].to_numpy(float)
    scale = max(float(np.nanmax(np.abs(left))), 1.0)
    return bool(np.nanmedian(np.abs(left - right)) <= scale * 1e-8)


def datasets_from_frame(frame: pd.DataFrame, base: str, *, sheet: str | None = None,
                        minimum_points: int = 3) -> list[SpectrumDataset]:
    """Extract repeated X/Y pairs or a shared-X/multiple-Y table."""
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if frame.shape[1] < 2:
        return []

    numeric_counts = frame.apply(pd.to_numeric, errors="coerce").notna().sum()
    numeric_cols = [index for index, count in enumerate(numeric_counts) if count >= minimum_points]
    if len(numeric_cols) < 2:
        return []

    pairs: list[tuple[int, int]] = []
    # Instrument exports commonly repeat X before every Y: X1,Y1,X2,Y2,...
    adjacent = [(index, index + 1) for index in range(0, frame.shape[1] - 1, 2)]
    repeated_x = len(adjacent) > 1 and all(
        pair[0] in numeric_cols and pair[1] in numeric_cols for pair in adjacent
    ) and all(_columns_match(frame, adjacent[0][0], pair[0]) for pair in adjacent[1:])
    if repeated_x:
        pairs = adjacent
    else:
        # Otherwise interpret the first numeric column as a shared X column.
        x_col = numeric_cols[0]
        pairs = [(x_col, y_col) for y_col in numeric_cols[1:]]

    output: list[SpectrumDataset] = []
    used_names: dict[str, int] = {}
    for x_col, y_col in pairs:
        pair = _numeric_pair(frame, x_col, y_col, minimum_points)
        if pair is None:
            continue
        x, y, first_numeric = pair
        name = _dataset_name(frame, x_col, y_col, first_numeric, base, sheet)
        count = used_names.get(name, 0) + 1
        used_names[name] = count
        if count > 1:
            header = ""
            for row in range(first_numeric):
                candidate = _clean_label(frame.iat[row, y_col])
                if candidate and not _is_axis_label(candidate):
                    header = candidate
                    break
            name = f"{name} — {header or f'Series {count}'}"
        output.append(SpectrumDataset(name, x, y, str(base), sheet))
    return output


def _read_text_frame(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        raise ValueError("The file is empty.")
    sample = "\n".join(nonempty[:40])
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        delimiter = None
    rows = []
    for line in nonempty:
        values = next(csv.reader([line], delimiter=delimiter)) if delimiter else line.split()
        rows.append([value.strip() for value in values])
    width = max(map(len, rows))
    return pd.DataFrame([row + [None] * (width - len(row)) for row in rows])


def discover_spectra(path, *, minimum_points: int = 3) -> list[SpectrumDataset]:
    """Return every plottable dataset found across sheets or column groups."""
    source = Path(path)
    if source.suffix.lower() in {".xlsx", ".xls"}:
        sheets = pd.read_excel(source, sheet_name=None, header=None)
        found = []
        for sheet_name, frame in sheets.items():
            found.extend(datasets_from_frame(
                frame, source.stem, sheet=str(sheet_name), minimum_points=minimum_points
            ))
    else:
        found = datasets_from_frame(
            _read_text_frame(source), source.stem, minimum_points=minimum_points
        )
    if not found:
        raise ValueError(f"No numeric X/Y datasets were found in {source.name}.")
    found = [SpectrumDataset(item.name, item.x, item.y, str(source), item.sheet) for item in found]
    # A single plain two-column file should keep the familiar filename label.
    if len(found) == 1:
        only = found[0]
        found[0] = SpectrumDataset(source.stem, only.x, only.y, str(source), only.sheet)
    return found


def discover_many(paths, *, minimum_points: int = 3):
    """Discover datasets from several files and return non-fatal read errors."""
    datasets, failures = [], []
    for value in paths:
        path = Path(value)
        try:
            discovered = discover_spectra(path, minimum_points=minimum_points)
        except Exception as error:
            failures.append((path.name, str(error)))
            continue
        datasets.extend(discovered)
    # Ensure list labels remain unique across similarly named files/sheets.
    used: dict[str, int] = {}
    unique = []
    for item in datasets:
        count = used.get(item.name, 0) + 1
        used[item.name] = count
        name = item.name if count == 1 else f"{item.name} ({count})"
        unique.append(SpectrumDataset(name, item.x, item.y, str(Path(item.source)), item.sheet))
    return unique, failures

"""LIBS text/ZIP discovery without extracting archives or changing raw signals."""
from pathlib import Path, PurePosixPath
import stat
from zipfile import ZipFile

import numpy as np
import pandas as pd

from dataset_reader import SpectrumDataset, datasets_from_frame, text_frame

TEXT_SUFFIXES = {".txt", ".csv", ".tsv", ".dat", ".xy", ".asc"}
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 5000


def _frame_spectra(frame, name, source, minimum_points, sheet=None):
    # The supplied headerless instrument format is wavelength, constant 1, intensity.
    # The auxiliary column's meaning is not inferred from its numeric value.
    # Scope this interpretation to LIBS; generic three-column tables are unchanged.
    if frame.shape[1] == 3:
        numeric = frame.apply(pd.to_numeric, errors="coerce")
        values = numeric.to_numpy(float)
        if (len(values) >= minimum_points and numeric.notna().all().all()
                and np.all(values[:, 1] == 1)):
            finite = np.isfinite(values[:, 0]) & np.isfinite(values[:, 2])
            values = values[finite]
            if len(values) < minimum_points:
                raise ValueError("Too few finite wavelength/intensity pairs.")
            if np.ptp(values[:, 0]) <= 0:
                raise ValueError("The wavelength column has no range.")
            label = f"{name} — {sheet}" if sheet else name
            return [SpectrumDataset(label, values[:, 0], values[:, 2], source, sheet)]
    found = datasets_from_frame(frame, name, sheet=sheet, minimum_points=minimum_points)
    if not found:
        raise ValueError("No numeric wavelength/intensity spectrum found.")
    return [SpectrumDataset(d.name, d.x, d.y, source, d.sheet) for d in found]


def _read_spectra(text, name, source, minimum_points):
    return _frame_spectra(text_frame(text), name, source, minimum_points)


def _archive_member_allowed(info):
    name = info.filename.replace("\\", "/")
    path = PurePosixPath(name)
    mode = info.external_attr >> 16
    return (not info.is_dir() and not path.is_absolute()
            and not any(part in {"..", "__MACOSX"} or part.startswith(".") for part in path.parts)
            and not stat.S_ISLNK(mode)
            and path.suffix.lower() in TEXT_SUFFIXES)


def discover_libs_many(paths, *, minimum_points=3):
    datasets, failures = [], []
    for value in paths:
        source = Path(value)
        try:
            if source.suffix.lower() != ".zip":
                if source.suffix.lower() in {".xlsx", ".xls"}:
                    for sheet, frame in pd.read_excel(source, sheet_name=None, header=None).items():
                        try:
                            datasets.extend(_frame_spectra(
                                frame, source.stem, str(source), minimum_points, str(sheet)))
                        except ValueError as error:
                            failures.append((f"{source.name} :: {sheet}", str(error)))
                    continue
                if source.stat().st_size > MAX_MEMBER_BYTES:
                    raise ValueError("Text file exceeds the 16 MiB import limit.")
                datasets.extend(_read_spectra(source.read_text(encoding="utf-8-sig"),
                                              source.stem, str(source), minimum_points))
                continue
            with ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_MEMBERS:
                    raise ValueError("Archive exceeds the 5,000-entry import limit.")
                members = [entry for entry in entries if _archive_member_allowed(entry)]
                if not members:
                    raise ValueError("No supported spectrum text files in this ZIP.")
                if sum(entry.file_size for entry in members) > MAX_ARCHIVE_BYTES:
                    raise ValueError("Archive spectra exceed the 256 MiB import limit.")
                for member in sorted(members, key=lambda entry: entry.filename.casefold()):
                    label = f"{source.name} :: {member.filename}"
                    try:
                        if member.file_size > MAX_MEMBER_BYTES:
                            raise ValueError("Spectrum exceeds the 16 MiB import limit.")
                        with archive.open(member) as stream:
                            data = stream.read(MAX_MEMBER_BYTES + 1)
                        if len(data) > MAX_MEMBER_BYTES:
                            raise ValueError("Spectrum exceeds the 16 MiB import limit.")
                        datasets.extend(_read_spectra(
                            data.decode("utf-8-sig"), PurePosixPath(member.filename.replace("\\", "/")).stem,
                            f"{source.resolve()}::{member.filename}", minimum_points))
                    except Exception as error:
                        failures.append((label, str(error)))
        except Exception as error:
            failures.append((source.name, str(error)))
    unique, names = [], set()
    for dataset in datasets:
        name, number = dataset.name, 1
        while name in names:
            number += 1
            name = f"{dataset.name} ({number})"
        names.add(name)
        unique.append(SpectrumDataset(name, dataset.x, dataset.y, dataset.source, dataset.sheet))
    return unique, failures

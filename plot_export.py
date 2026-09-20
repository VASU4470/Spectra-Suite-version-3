"""Reliable, shared figure export helpers."""

from __future__ import annotations

from pathlib import Path
from io import BytesIO
from contextlib import contextmanager
import os
import tempfile

import numpy as np
# Explicit imports are required by frozen builds: savefig discovers these
# dynamically, which PyInstaller's GUI-backend auto-detection cannot see.
from matplotlib.backends import backend_agg, backend_pdf, backend_svg


SUPPORTED_FIGURE_FORMATS = (".png", ".jpg", ".svg", ".pdf", ".tiff")


@contextmanager
def sized_figure(figure, size_inches=None):
    """Fit labels at export size and restore the live layout as well as its canvas."""
    size = figure.get_size_inches().copy()
    canvas = figure.canvas
    engine = figure.get_layout_engine()
    subplot = dict(vars(figure.subplotpars))
    positions = [(ax, ax.get_position(original=True).frozen(), ax.get_position().frozen(), ax.get_in_layout())
                 for ax in figure.axes]
    try:
        if size_inches is not None:
            figure.set_size_inches(size_inches, forward=False)
        if engine is None or type(engine).__name__ == "PlaceHolderLayoutEngine":
            figure.tight_layout()
        yield
    finally:
        figure.set_size_inches(size, forward=False)
        figure.set_canvas(canvas)
        figure.set_layout_engine(engine)
        figure.subplotpars.update(**subplot)
        for ax, original, active, in_layout in positions:
            ax.set_position(original, which="original")
            ax.set_position(active, which="active")
            ax.set_in_layout(in_layout)


def figure_bytes(figure, *, format="png", dpi=100, size_inches=None,
                 transparent=False, tight=False):
    """Render a preview or vector report panel without replacing its live canvas."""
    stream = BytesIO()
    backend = {"pdf": backend_pdf, "svg": backend_svg}.get(format, backend_agg)
    with sized_figure(figure, size_inches):
        figure.savefig(stream, format=format, backend="module://" + backend.__name__,
                       dpi=dpi, transparent=transparent, bbox_inches="tight" if tight else None)
        return stream.getvalue()


def normalize_figure_path(filename, selected_filter="", default_suffix=".png"):
    """Add a selected/default extension without replacing an explicit valid one."""
    path = Path(filename)
    if path.suffix.lower() in SUPPORTED_FIGURE_FORMATS:
        return path
    selected = next(
        (suffix for suffix in SUPPORTED_FIGURE_FORMATS if f"*{suffix}" in selected_filter.lower()),
        default_suffix,
    )
    return path.with_suffix(selected)


def save_figure(figure, filename, *, selected_filter="", dpi=300,
                size_inches=None, transparent=False, tight=True):
    """Atomically export without changing the live canvas or losing an old file."""
    path = normalize_figure_path(filename, selected_filter)
    dpi = int(dpi)
    if not 1 <= dpi <= 2400:
        raise ValueError("Resolution must be between 1 and 2400 DPI.")
    size = np.asarray(size_inches if size_inches is not None else figure.get_size_inches(), float)
    if size.shape != (2,) or not np.all(np.isfinite(size)) or np.any(size <= 0):
        raise ValueError("Figure width and height must be positive finite values.")
    suffix = path.suffix.lower()
    if suffix not in {".pdf", ".svg"} and np.prod(size * dpi) > 100_000_000:
        raise ValueError("Image exceeds 100 megapixels. Reduce its dimensions or DPI.")
    if transparent and suffix == ".jpg":
        raise ValueError("JPEG does not support transparency. Use PNG, PDF or SVG.")
    path.parent.mkdir(parents=True, exist_ok=True)
    backend = {".pdf": backend_pdf, ".svg": backend_svg}.get(suffix, backend_agg)
    handle, temporary_name = tempfile.mkstemp(prefix=".spectrasuite-", suffix=suffix, dir=path.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with sized_figure(figure, size):
            figure.savefig(temporary, format=suffix[1:], backend="module://" + backend.__name__,
                           dpi=dpi, bbox_inches="tight" if tight else None,
                           transparent=transparent)
        if temporary.stat().st_size == 0:
            raise OSError(f"Figure export created an empty file: {path}")
        if suffix == ".pdf":
            with temporary.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise OSError(f"PDF export is invalid: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path

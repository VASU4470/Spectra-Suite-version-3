"""Reliable, shared figure export helpers."""

from __future__ import annotations

from pathlib import Path


SUPPORTED_FIGURE_FORMATS = (".png", ".jpg", ".svg", ".pdf", ".tiff")


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


def save_figure(figure, filename, *, selected_filter="", dpi=300):
    """Save a Matplotlib figure and verify that a non-empty file was written."""
    path = normalize_figure_path(filename, selected_filter)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=int(dpi), bbox_inches="tight")
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"Figure export did not create a valid file: {path}")
    if path.suffix.lower() == ".pdf":
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise OSError(f"PDF export is invalid: {path}")
    return path

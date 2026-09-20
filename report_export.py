"""Selected-dataset exports and paginated vector PDF reports."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable
from xml.sax.saxutils import escape

import matplotlib
from matplotlib.figure import Figure
import numpy as np
import pandas as pd
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app_version import APP_VERSION
from plot_export import figure_bytes, save_figure


@dataclass
class ExportItem:
    name: str
    figure: Callable[[], Figure]
    data: pd.DataFrame | None = None
    results: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    source: str = ""


def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def setting_lines(settings, prefix=""):
    """Show all settings while summarizing embedded reference arrays as data."""
    for key, value in settings.items():
        label = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from setting_lines(value, label + " / ")
        elif isinstance(value, np.ndarray):
            finite = value[np.isfinite(value)] if np.issubdtype(value.dtype, np.number) else []
            detail = f"; range {np.min(finite):.7g} to {np.max(finite):.7g}" if len(finite) else ""
            yield f"{label}: array with shape {value.shape}{detail}"
        elif key == "bg_data" and isinstance(value, (tuple, list)):
            for index, array in enumerate(value):
                yield from setting_lines({f"reference {'XY'[index] if index < 2 else index}": np.asarray(array)}, prefix)
        elif key in {"pixel_points", "original_x", "original_y"} and isinstance(value, list):
            yield f"{label}: {len(value)} entries (retained in the export bundle's settings JSON)"
        else:
            yield f"{label}: {json.dumps(json_value(value), ensure_ascii=False)}"


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")[:100] or "spectrum"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        name = "_" + name
    return name


def _fonts():
    if "SpectraSans" not in pdfmetrics.getRegisteredFontNames():
        root = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        pdfmetrics.registerFont(TTFont("SpectraSans", str(root / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("SpectraSansBold", str(root / "DejaVuSans-Bold.ttf")))


def _paragraph(text, *, size=9, bold=False, color="#172033"):
    style = ParagraphStyle("body", fontName="SpectraSansBold" if bold else "SpectraSans",
                           fontSize=size, leading=size * 1.45, textColor=colors.HexColor(color),
                           splitLongWords=True, spaceAfter=7)
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def save_pdf_report(items, filename, *, options=None, progress=None):
    """A4 figure pages followed by complete results/settings pages, atomically saved."""
    items = list(items)
    if not items:
        raise ValueError("Select at least one dataset for the report.")
    _fonts()
    options = dict(options or {})
    path = Path(filename).with_suffix(".pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = A4
    writer = PdfWriter()
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    def white_page(canvas, _document=None):
        canvas.saveState(); canvas.setFillColor(colors.white)
        canvas.rect(0, 0, width, height, fill=1, stroke=0); canvas.restoreState()
    for index, item in enumerate(items):
        if progress:
            progress(index, len(items), item.name)
        fig = item.figure()
        panel = PdfReader(BytesIO(figure_bytes(fig, format="pdf", **options))).pages[0]
        header_stream = BytesIO()
        header = Canvas(header_stream, pagesize=A4)
        white_page(header)
        header.setFont("SpectraSans", 9)
        header.setFillColor(colors.HexColor("#2563eb"))
        header.drawString(36, height - 34, f"SpectraSuite {APP_VERSION} | Scientific report")
        title = _paragraph(item.name, size=16, bold=True)
        _, title_height = title.wrap(width - 72, 100)
        title.drawOn(header, 36, height - 52 - title_height)
        header.setFillColor(colors.HexColor("#475569"))
        header.setFont("SpectraSans", 8)
        header.drawString(36, 58, f"Generated {created} | Dataset {index + 1} of {len(items)}")
        header.drawString(36, 44, "Results and processing settings follow this figure.")
        header.showPage(); header.save()
        page = writer.add_page(PdfReader(BytesIO(header_stream.getvalue())).pages[0])
        available_height = height - 160 - title_height
        pw, ph = float(panel.mediabox.width), float(panel.mediabox.height)
        scale = min((width - 72) / pw, available_height / ph)
        tx = (width - pw * scale) / 2 - float(panel.mediabox.left) * scale
        ty = 92 + (available_height - ph * scale) / 2 - float(panel.mediabox.bottom) * scale
        page.merge_transformed_page(panel, Transformation().scale(scale).translate(tx, ty))

        text_stream = BytesIO()
        story = [_paragraph(item.name, size=15, bold=True),
                 _paragraph("Results and processing settings", size=12, bold=True),
                 _paragraph(f"Source: {item.source or 'Current workspace / manual data'}")]
        if item.data is not None:
            story.append(_paragraph(f"Exported data: {len(item.data):,} rows; columns: {', '.join(map(str, item.data.columns))}"))
        story.append(Spacer(1, 8))
        story.append(_paragraph("Results", size=11, bold=True))
        story.extend(_paragraph(line) for line in (item.results or ["No stored analysis results for this dataset."]))
        story.append(Spacer(1, 8))
        story.append(_paragraph("Processing and plot settings", size=11, bold=True))
        story.extend(_paragraph(line) for line in setting_lines(item.settings))
        story.append(_paragraph("Figure export settings", size=11, bold=True))
        story.extend(_paragraph(line) for line in setting_lines(options))
        SimpleDocTemplate(text_stream, pagesize=A4, leftMargin=36, rightMargin=36,
                          topMargin=40, bottomMargin=48).build(story, onFirstPage=white_page, onLaterPages=white_page)
        for metadata_page in PdfReader(BytesIO(text_stream.getvalue())).pages:
            writer.add_page(metadata_page)
    total = len(writer.pages)
    for number, page in enumerate(writer.pages, 1):
        stream = BytesIO()
        footer = Canvas(stream, pagesize=A4)
        footer.setFont("SpectraSans", 8); footer.setFillColor(colors.HexColor("#64748b"))
        footer.drawRightString(width - 36, 22, f"{number} / {total}")
        footer.showPage(); footer.save()
        page.merge_page(PdfReader(BytesIO(stream.getvalue())).pages[0])
    writer.add_metadata({"/Title": "SpectraSuite scientific report", "/Creator": f"SpectraSuite {APP_VERSION}"})
    handle, temporary = tempfile.mkstemp(prefix=".spectrasuite-report-", suffix=".pdf", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as output:
            writer.write(output)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def export_batch(items, folder, *, extension="pdf", options=None, include_data=True,
                 include_figures=True, include_report=True, progress=None):
    """Publish a complete new export folder only when every selected output succeeds."""
    items = list(items)
    if not items or not any((include_data, include_figures, include_report)):
        raise ValueError("Select datasets and at least one export product.")
    if extension not in {"pdf", "svg", "png", "tiff", "jpg"}:
        raise ValueError("Unsupported figure format.")
    destination = Path(folder)
    destination.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".spectrasuite-export-", dir=destination))
    target = destination / ("SpectraSuite_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + stage.name.rsplit("-", 1)[-1])
    manifest = []
    try:
        for index, item in enumerate(items):
            if progress:
                progress(index, len(items), item.name)
            stem = f"{index + 1:03d}_{safe_name(item.name)}"
            files = []
            if include_figures:
                files.append(save_figure(item.figure(), stage / f"{stem}_plot.{extension}", **(options or {})).name)
            if include_data and item.data is not None:
                name = f"{stem}_data.csv"
                item.data.to_csv(stage / name, index=False)
                files.append(name)
            (stage / f"{stem}_results.txt").write_text("\n".join(item.results) or "No stored analysis results.", encoding="utf-8")
            (stage / f"{stem}_settings.json").write_text(json.dumps(json_value(item.settings), indent=2, ensure_ascii=False), encoding="utf-8")
            manifest.append({"name": item.name, "source": item.source, "files": files,
                             "results": f"{stem}_results.txt", "settings": f"{stem}_settings.json"})
        if include_report:
            save_pdf_report(items, stage / "report.pdf", options=options, progress=progress)
        (stage / "manifest.json").write_text(json.dumps({"version": APP_VERSION, "datasets": manifest}, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target

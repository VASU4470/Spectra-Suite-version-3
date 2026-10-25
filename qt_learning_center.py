"""Offline Learning Center for SpectraSuite.

The Learning Center explains the scientific workflow around the application's
measurements and analyses.  It is educational documentation only; it does not
modify scientific calculations or processing defaults.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from qt_theme import LIGHT_STYLE, apply_theme, apply_window_icon


TOPICS = [
    (
        "Getting Started",
        "User Manual",
        """
        <h2>User Manual</h2>
        <p>The Learning Center is an offline companion to SpectraSuite.</p>
        <p>Use the Project Explorer to select data and documents, the ribbon to
        choose processing or analysis commands, and the central workspace to keep
        plots, data tables, results, and history visible as separate documents.</p>
        <p>Technique-specific guides will be expanded as the UI v2 migration is
        validated.</p>
        """,
    ),
    (
        "Science of Analysis",
        "Scientific workflow",
        """
        <h2>Science of Analysis</h2>
        <p>A scientific result should be understood as a chain:</p>
        <p><b>Physical phenomenon → Instrument measurement → Raw data →
        Processing → Analysis → Interpretation.</b></p>
        <p>SpectraSuite should make each step visible. Processing changes the
        representation of measured data; analysis extracts quantities from that
        representation; interpretation assigns scientific meaning and always
        depends on experimental context and assumptions.</p>
        """,
    ),
    (
        "Techniques",
        "FT-IR",
        """
        <h2>FT-IR spectroscopy</h2>
        <h3>What is measured?</h3>
        <p>FT-IR measures the wavelength- or wavenumber-dependent response of a
        sample to infrared radiation, typically reported as transmittance,
        absorbance, or related intensity.</p>
        <h3>Instrumentation</h3>
        <p>A typical FT-IR instrument uses a broadband infrared source, an
        interferometer, a sample compartment, and a detector. The measured
        interferogram is transformed into a spectrum by a Fourier transform.</p>
        <h3>In SpectraSuite</h3>
        <p>Common operations include baseline correction, smoothing,
        normalization, peak identification, area measurement, and deconvolution.
        The conventional FT-IR wavenumber direction is preserved in the UI.</p>
        """,
    ),
    (
        "Techniques",
        "XRD",
        """
        <h2>X-ray diffraction (XRD)</h2>
        <h3>What is measured?</h3>
        <p>XRD records diffracted X-ray intensity as a function of diffraction
        angle, commonly 2θ.</p>
        <h3>Instrumentation</h3>
        <p>A laboratory diffractometer generally contains an X-ray source,
        sample stage/goniometer, optics, and detector. Crystal planes produce
        diffraction maxima when the Bragg condition is satisfied.</p>
        <h3>In SpectraSuite</h3>
        <p>Current analysis includes peak detection, FWHM measurement, peak
        height, and Scherrer crystallite-size estimation. Instrumental
        broadening and Williamson–Hall analysis should remain clearly separated
        until validated.</p>
        """,
    ),
    (
        "Techniques",
        "UV-Vis",
        """
        <h2>UV-Visible spectroscopy</h2>
        <h3>What is measured?</h3>
        <p>UV-Vis measures the optical response of a sample as a function of
        wavelength, commonly absorbance or transmittance.</p>
        <h3>Instrumentation</h3>
        <p>Typical systems include UV/visible light sources, wavelength
        selection optics, a sample path, and a photodetector.</p>
        <h3>In SpectraSuite</h3>
        <p>Processing may include baseline removal, edge trimming, optical
        transforms, Tauc analysis, Urbach energy, and Kubelka–Munk-related
        workflows where appropriate. The assumptions of every transform should
        be checked before interpreting a result.</p>
        """,
    ),
    (
        "Techniques",
        "Raman",
        """
        <h2>Raman spectroscopy</h2>
        <h3>What is measured?</h3>
        <p>Raman spectroscopy records inelastically scattered light as a
        function of Raman shift.</p>
        <h3>Instrumentation</h3>
        <p>A typical Raman instrument combines a monochromatic laser,
        collection optics, rejection filters, a spectrograph, and a detector.</p>
        <h3>In SpectraSuite</h3>
        <p>Baseline correction, smoothing, peak measurements, ratios,
        annotation, and deconvolution are supported or planned within the shared
        spectroscopy workflow.</p>
        """,
    ),
    (
        "Techniques",
        "XPS",
        """
        <h2>X-ray photoelectron spectroscopy (XPS)</h2>
        <p>XPS measures photoelectron intensity as a function of binding energy.
        A source irradiates the sample and an electron-energy analyser measures
        emitted electrons. SpectraSuite currently treats XPS functionality
        conservatively as preview functionality where chemical-state fitting or
        quantitative workflows are not yet validated.</p>
        """,
    ),
    (
        "Techniques",
        "LIBS",
        """
        <h2>Laser-induced breakdown spectroscopy (LIBS)</h2>
        <p>LIBS uses a focused laser pulse to create a transient plasma. Optical
        emission from that plasma is dispersed spectrally and detected as
        intensity versus wavelength. Peak positions alone do not establish an
        elemental assignment without appropriate reference and validation.</p>
        """,
    ),
    (
        "Data Processing",
        "Baseline correction",
        """
        <h2>Baseline correction</h2>
        <p>Baseline correction estimates and removes a slowly varying background
        from a signal. It can improve peak measurements, but an inappropriate
        baseline can also alter peak height, area, and apparent shape.</p>
        <p>SpectraSuite preserves the application's established baseline
        algorithm and defaults during the UI redesign. The Learning Center
        should document the exact method and parameters used by each workflow.</p>
        """,
    ),
    (
        "Data Processing",
        "Smoothing",
        """
        <h2>Smoothing</h2>
        <p>Smoothing reduces short-scale noise to make trends and peaks easier to
        inspect. Excessive smoothing can broaden peaks, shift local extrema, or
        erase weak features.</p>
        <p>SpectraSuite uses its existing smoothing implementation and defaults;
        the UI redesign does not change those scientific choices.</p>
        """,
    ),
    (
        "Analysis Science",
        "Peak detection",
        """
        <h2>Peak detection</h2>
        <p>Peak detection identifies local spectral features using rules such as
        prominence, height, separation, or noise-adaptive criteria. The selected
        parameters influence how many peaks are reported.</p>
        <p>A detected peak is a mathematical feature of the processed signal; it
        is not automatically a chemical or physical identification.</p>
        """,
    ),
    (
        "Analysis Science",
        "Peak area",
        """
        <h2>Peak area</h2>
        <p>Integrated area is computed over a selected interval relative to a
        chosen baseline. The numerical value depends on the interval, baseline,
        signal units, and preprocessing steps.</p>
        """,
    ),
    (
        "Analysis Science",
        "FWHM",
        """
        <h2>Full width at half maximum (FWHM)</h2>
        <p>FWHM describes the width of a peak at half of its peak height above
        the relevant baseline. It is widely used to characterize peak
        broadening, but its physical interpretation depends on the technique and
        line-shape assumptions.</p>
        """,
    ),
    (
        "Analysis Science",
        "Scherrer crystallite size",
        """
        <h2>Scherrer crystallite-size estimate</h2>
        <p>The Scherrer relation estimates coherent diffraction-domain size from
        XRD peak broadening:</p>
        <p><b>D = Kλ / (β cos θ)</b></p>
        <p>where D is crystallite size, K is a shape factor, λ is X-ray
        wavelength, β is peak broadening in radians, and θ is the Bragg angle.</p>
        <p>Crystallite size is not necessarily the same as particle size.
        Instrumental broadening, strain, line-shape choice, and peak overlap can
        affect the estimate.</p>
        """,
    ),
    (
        "Analysis Science",
        "Tauc analysis",
        """
        <h2>Tauc analysis</h2>
        <p>A Tauc-style analysis transforms optical data and fits an assumed
        linear region to estimate an optical transition energy from an
        intercept. The result depends strongly on signal conversion, transition
        model, fit interval, and data quality.</p>
        <p>SpectraSuite should always show the selected fit interval, fit quality,
        and intercept rather than presenting the value without context.</p>
        """,
    ),
    (
        "Analysis Science",
        "Deconvolution and fitting",
        """
        <h2>Deconvolution and peak fitting</h2>
        <p>Peak fitting represents an observed signal as one or more model
        components plus a baseline. Gaussian, Lorentzian, Voigt, and
        pseudo-Voigt models make different assumptions about line shape.</p>
        <p>A mathematically good fit does not by itself prove that every fitted
        component corresponds to a distinct physical species.</p>
        """,
    ),
    (
        "Interpretation",
        "Assumptions and limitations",
        """
        <h2>Assumptions and limitations</h2>
        <p>Every analysis result should be interpreted together with the raw
        measurement, preprocessing history, units, selected parameters, and
        technique-specific assumptions.</p>
        <p>SpectraSuite should distinguish measured values, processed values,
        calculated quantities, and user interpretations wherever possible.</p>
        """,
    ),
    (
        "Equations & References",
        "Equations used by SpectraSuite",
        """
        <h2>Equations and references</h2>
        <p>This section will become the authoritative offline reference for
        equations implemented by SpectraSuite, including variable definitions,
        units, assumptions, and literature/software references.</p>
        <p>Only equations confirmed against the current source and tests should
        be documented here as implemented behavior.</p>
        """,
    ),
]


class LearningCenterDialog(QDialog):
    """Offline, searchable-by-navigation scientific help center."""

    def __init__(self, parent=None, initial_topic=None):
        super().__init__(parent)
        self.setWindowTitle("SpectraSuite Learning Center")
        self.resize(1000, 720)
        self.setMinimumSize(760, 520)
        apply_theme(self, LIGHT_STYLE)
        apply_window_icon(self, "APP")

        root = QVBoxLayout(self)
        heading = QLabel("Learn — science, instrumentation, processing and analysis")
        heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        self.topic_list = QListWidget()
        self.topic_list.setMinimumWidth(250)
        self.topic_list.setMaximumWidth(340)
        splitter.addWidget(self.topic_list)

        content_wrap = QWidget()
        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(8, 0, 0, 0)
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        content_layout.addWidget(self.content)
        splitter.addWidget(content_wrap)
        splitter.setSizes([280, 720])

        last_category = None
        target_row = 0
        for category, title, html in TOPICS:
            if category != last_category:
                header = QListWidgetItem(category)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = header.font()
                font.setBold(True)
                header.setFont(font)
                self.topic_list.addItem(header)
                last_category = category
            item = QListWidgetItem(f"   {title}")
            item.setData(Qt.ItemDataRole.UserRole, html)
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
            self.topic_list.addItem(item)
            if initial_topic and initial_topic.lower() in title.lower():
                target_row = self.topic_list.count() - 1

        self.topic_list.currentItemChanged.connect(self._topic_changed)
        self.topic_list.setCurrentRow(target_row if target_row else 1)

    def _topic_changed(self, item, _previous=None):
        if item is None:
            return
        html = item.data(Qt.ItemDataRole.UserRole)
        if html:
            self.content.setHtml(html)

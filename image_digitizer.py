"""Calibrated graph-image digitization; no inference of units or hidden dimensions."""
from dataclasses import dataclass
import hashlib

import numpy as np
from scipy.ndimage import label


@dataclass
class AxisCalibration:
    origin: tuple
    x_point: tuple
    y_point: tuple
    x0: float
    x1: float
    y0: float
    y1: float
    x_log: bool = False
    y_log: bool = False

    def matrix(self):
        points = np.asarray([self.origin, self.x_point, self.y_point], dtype=float)
        values = np.asarray([self.x0, self.x1, self.y0, self.y1], dtype=float)
        if not np.all(np.isfinite(points)) or not np.all(np.isfinite(values)):
            raise ValueError("Calibration points and axis values must be finite.")
        matrix = np.column_stack((points[1] - points[0], points[2] - points[0]))
        if abs(np.linalg.det(matrix)) < 1 or np.linalg.cond(matrix) > 1000:
            raise ValueError("Choose three well-separated calibration points on the two axes.")
        if self.x0 == self.x1 or self.y0 == self.y1:
            raise ValueError("The two values on each axis must be different.")
        if (self.x_log and min(self.x0, self.x1) <= 0) or (self.y_log and min(self.y0, self.y1) <= 0):
            raise ValueError("Logarithmic axes require positive calibration values.")
        return matrix

    def fractions(self, pixels):
        pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
        return np.linalg.solve(self.matrix(), (pixels - self.origin).T).T

    def convert(self, pixels):
        uv = self.fractions(pixels)
        output = np.empty_like(uv)
        for index, (low, high, log_scale) in enumerate(((self.x0, self.x1, self.x_log), (self.y0, self.y1, self.y_log))):
            if log_scale:
                output[:, index] = np.power(10., np.log10(low) + uv[:, index] * (np.log10(high) - np.log10(low)))
            else:
                output[:, index] = low + uv[:, index] * (high - low)
        if not np.all(np.isfinite(output)):
            raise ValueError("Some points are outside the finite calibrated range.")
        return output


@dataclass
class DigitizedCurve:
    name: str
    x: np.ndarray
    y: np.ndarray
    xlabel: str
    ylabel: str
    metadata: dict


def color_trace(rgb, color, calibration, tolerance=35, step=3):
    """Sample the largest connected color region, one center point per X bin."""
    rgb = np.asarray(rgb, dtype=np.uint8)
    distance = np.max(np.abs(rgb.astype(np.int16) - np.asarray(color, dtype=np.int16)), axis=2)
    mask = distance <= tolerance
    yy, xx = np.nonzero(mask)
    if not len(xx):
        raise ValueError("No pixels match that color. Adjust the color tolerance.")
    uv = calibration.fractions(np.column_stack((xx, yy)))
    inside = np.all((uv >= 0) & (uv <= 1), axis=1)
    mask[:] = False; mask[yy[inside], xx[inside]] = True
    components, count = label(mask, structure=np.ones((3, 3)))
    if not count:
        raise ValueError("No matching curve inside the calibrated plot area.")
    sizes = np.bincount(components.ravel()); sizes[0] = 0
    yy, xx = np.nonzero(components == np.argmax(sizes))
    if len(xx) < 3:
        raise ValueError("The selected color does not form a continuous curve.")
    uv = calibration.fractions(np.column_stack((xx, yy)))
    resolution = max(2, int(np.linalg.norm(np.asarray(calibration.x_point) - calibration.origin) / max(1, step)))
    bins = np.minimum(resolution - 1, np.floor(uv[:, 0] * resolution).astype(int))
    pixels = [np.median(np.column_stack((xx[bins == index], yy[bins == index])), axis=0)
              for index in np.unique(bins)]
    if len(pixels) < 2:
        raise ValueError("The selected region has too little X range to trace.")
    return np.asarray(pixels)


def image_provenance(rgb, source, calibration, method, pixels):
    return {"kind": "digitized image", "approximate": True, "source_image": str(source),
            "image_sha256": hashlib.sha256(np.ascontiguousarray(rgb).tobytes()).hexdigest(),
            "image_size": [int(rgb.shape[1]), int(rgb.shape[0])],
            "calibration": dict(vars(calibration)), "method": method,
            "pixel_points": np.asarray(pixels).tolist()}

"""Deterministic technical image analysis for Refract v2.

This module deliberately measures image properties instead of asking a vision
model to estimate them. Results are suitable as evidence for the v2 reviewer.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import ExifTags, Image, ImageOps


@dataclass(frozen=True)
class SourceMeasurements:
    width: int
    height: int
    bit_depth: int | None
    color_space: str | None
    file_format: str
    exif: dict[str, str | int | float | None]
    sha256: str


@dataclass(frozen=True)
class TechnicalMeasurements:
    exposure_ev_bias: float | None
    clipped_highlights_pct: float
    clipped_shadows_pct: float
    dynamic_range_proxy: float | None
    white_balance: str
    wb_confidence: float
    sharpness_score: float
    motion_blur_likelihood: float
    noise_score: float
    color_cast: str | None
    measurements: dict[str, float | int | str]


@dataclass(frozen=True)
class TechnicalAnalysisResult:
    source: SourceMeasurements
    technical: TechnicalMeasurements


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_exif(img: Image.Image) -> dict[str, str | int | float | None]:
    out: dict[str, str | int | float | None] = {}
    try:
        exif = img.getexif()
    except Exception:
        return out
    for key, value in exif.items():
        name = ExifTags.TAGS.get(key, str(key))
        if isinstance(value, (str, int, float)) or value is None:
            out[name] = value
        elif isinstance(value, tuple) and len(value) == 2 and all(
            isinstance(x, int) for x in value
        ):
            num, den = value
            out[name] = float(num / den) if den else None
        else:
            text = str(value)
            if len(text) <= 200:
                out[name] = text
    return out


def _bit_depth(img: Image.Image) -> int | None:
    mode = img.mode
    if mode in {"1"}:
        return 1
    if mode in {"L", "P", "RGB", "RGBA", "CMYK", "YCbCr"}:
        return 8
    if mode.startswith("I;16"):
        return 16
    if mode == "I":
        return 32
    if mode == "F":
        return 32
    return None


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(rgb, dtype=np.float32)
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32)


def _luminance(linear_rgb: np.ndarray) -> np.ndarray:
    return (
        0.2126 * linear_rgb[..., 0]
        + 0.7152 * linear_rgb[..., 1]
        + 0.0722 * linear_rgb[..., 2]
    ).astype(np.float32)


def _estimate_white_balance(rgb01: np.ndarray) -> tuple[str, float, str | None, dict[str, float]]:
    med = np.median(rgb01.reshape(-1, 3), axis=0).astype(np.float64)
    r, g, b = [max(float(v), 1e-6) for v in med]
    rb_ratio = r / b
    rg_ratio = r / g
    bg_ratio = b / g

    log_rb = math.log2(rb_ratio)
    magnitude = abs(log_rb)
    confidence = min(0.70, magnitude / 0.75)

    if magnitude < 0.12:
        label = "neutral"
        cast = None
        confidence = max(0.35, 0.55 - magnitude)
    elif log_rb > 0:
        label = "warm"
        cast = "red/yellow"
    else:
        label = "cool"
        cast = "blue/cyan"

    if abs(math.log2(max(rg_ratio * bg_ratio, 1e-6))) > 0.25:
        cast = (cast + ", green/magenta imbalance") if cast else "green/magenta imbalance"

    return label, float(confidence), cast, {
        "median_r": r,
        "median_g": g,
        "median_b": b,
        "median_r_over_b": rb_ratio,
    }


def _sharpness_and_motion(gray8: np.ndarray) -> tuple[float, float, dict[str, float]]:
    lap = cv2.Laplacian(gray8, cv2.CV_32F, ksize=3)
    sharpness = float(np.var(lap))

    gx = cv2.Sobel(gray8, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray8, cv2.CV_32F, 0, 1, ksize=3)
    ex = float(np.mean(np.abs(gx))) + 1e-6
    ey = float(np.mean(np.abs(gy))) + 1e-6
    directional_imbalance = abs(ex - ey) / max(ex, ey)

    softness = 1.0 / (1.0 + sharpness / 150.0)
    motion = float(np.clip(0.65 * softness + 0.35 * directional_imbalance, 0.0, 1.0))
    return sharpness, motion, {
        "edge_energy_x": ex,
        "edge_energy_y": ey,
        "directional_imbalance": directional_imbalance,
    }


def _noise_score(gray01: np.ndarray) -> tuple[float, dict[str, float]]:
    gray32 = gray01.astype(np.float32)
    smooth = cv2.GaussianBlur(gray32, (0, 0), sigmaX=1.0, sigmaY=1.0)
    residual = gray32 - smooth

    gx = cv2.Sobel(gray32, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray32, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx * gx + gy * gy)
    threshold = float(np.percentile(grad, 45))
    flat = grad <= threshold
    samples = residual[flat] if np.any(flat) else residual.ravel()
    median = float(np.median(samples))
    mad = float(np.median(np.abs(samples - median)))
    sigma = 1.4826 * mad
    score_8bit = sigma * 255.0
    return float(score_8bit), {
        "noise_sigma_linear": sigma,
        "noise_sigma_8bit": score_8bit,
        "flat_region_gradient_threshold": threshold,
    }


class TechnicalAnalyzer:
    """Measure source facts and image-quality signals without an LLM."""

    def analyze(self, image_path: str | Path) -> TechnicalAnalysisResult:
        path = Path(image_path)
        with Image.open(path) as opened:
            source_format = opened.format or path.suffix.lstrip(".").upper() or "UNKNOWN"
            bit_depth = _bit_depth(opened)
            exif = _safe_exif(opened)
            icc = opened.info.get("icc_profile")
            color_space = "embedded ICC" if icc else ("sRGB-assumed" if opened.mode in {"RGB", "RGBA"} else None)
            img = ImageOps.exif_transpose(opened).convert("RGB")

        rgb01 = np.asarray(img, dtype=np.float32) / 255.0
        linear = _srgb_to_linear(rgb01)
        y = _luminance(linear)

        clipped_hi = float(np.mean(np.max(rgb01, axis=2) >= 0.995) * 100.0)
        clipped_lo = float(np.mean(y <= _srgb_to_linear(np.array(0.005, dtype=np.float32))) * 100.0)

        p005 = float(np.percentile(y, 0.5))
        p50 = float(np.percentile(y, 50.0))
        p995 = float(np.percentile(y, 99.5))
        dynamic_range = None
        if p995 > 1e-6 and p005 > 1e-6:
            dynamic_range = float(math.log2(p995 / p005))
        exposure_bias = None
        if p50 > 1e-8:
            exposure_bias = float(math.log2(p50 / 0.18))

        wb, wb_conf, cast, wb_measurements = _estimate_white_balance(rgb01)
        gray8 = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
        sharpness, motion, sharp_measurements = _sharpness_and_motion(gray8)
        noise, noise_measurements = _noise_score(y)

        measurements: dict[str, float | int | str] = {
            "luminance_p00_5": p005,
            "luminance_p50": p50,
            "luminance_p99_5": p995,
            **wb_measurements,
            **sharp_measurements,
            **noise_measurements,
        }

        return TechnicalAnalysisResult(
            source=SourceMeasurements(
                width=img.width,
                height=img.height,
                bit_depth=bit_depth,
                color_space=color_space,
                file_format=source_format,
                exif=exif,
                sha256=_sha256(path),
            ),
            technical=TechnicalMeasurements(
                exposure_ev_bias=exposure_bias,
                clipped_highlights_pct=clipped_hi,
                clipped_shadows_pct=clipped_lo,
                dynamic_range_proxy=dynamic_range,
                white_balance=wb,
                wb_confidence=wb_conf,
                sharpness_score=sharpness,
                motion_blur_likelihood=motion,
                noise_score=noise,
                color_cast=cast,
                measurements=measurements,
            ),
        )

    def to_domain(self, result: TechnicalAnalysisResult) -> tuple[Any, Any]:
        from ..domain.models import SourceFacts, TechnicalAssessment

        return SourceFacts(**result.source.__dict__), TechnicalAssessment(**result.technical.__dict__)

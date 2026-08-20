"""Deterministic non-generative DevelopEngine for Refract v2.

The first implementation uses float32 linear-light sRGB and OpenCV/NumPy. The
operation API is intentionally independent of that backend so a future
OCIO/scene-referred or RAW implementation can replace the internals without
changing EditPlan.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np
from PIL import Image, ImageOps

from .masks import MaskResolver


ENGINE_NAME = "develop"
ENGINE_VERSION = "0.1.0"


class DevelopEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class DevelopResult:
    output_path: str
    sha256: str
    width: int
    height: int
    operation_ids: list[str]
    latency_ms: int


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32)


def _linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    rgb = np.maximum(rgb, 0.0)
    return np.where(
        rgb <= 0.0031308,
        rgb * 12.92,
        1.055 * np.power(rgb, 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return (
        0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    ).astype(np.float32)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def _replace_luminance(rgb: np.ndarray, old_y: np.ndarray, new_y: np.ndarray) -> np.ndarray:
    ratio = new_y / np.maximum(old_y, 1e-6)
    return np.maximum(rgb * ratio[..., None], 0.0).astype(np.float32)


def _tone_region(rgb: np.ndarray, parameter: str, value: float) -> np.ndarray:
    y = _luminance(rgb)
    if parameter == "shadows":
        weight = 1.0 - _smoothstep(0.08, 0.45, y)
        max_ev = 1.5
    elif parameter == "highlights":
        weight = _smoothstep(0.30, 0.82, y)
        max_ev = 1.5
    elif parameter == "blacks":
        weight = 1.0 - _smoothstep(0.02, 0.22, y)
        max_ev = 0.8
    elif parameter == "whites":
        weight = _smoothstep(0.58, 0.96, y)
        max_ev = 0.8
    else:
        raise DevelopEngineError(f"Unsupported tone region: {parameter}")
    ev = np.clip(value, -100.0, 100.0) / 100.0 * max_ev
    new_y = y * np.power(2.0, ev * weight)
    return _replace_luminance(rgb, y, new_y)


def _contrast(rgb: np.ndarray, value: float) -> np.ndarray:
    y = _luminance(rgb)
    stops = np.log2(np.maximum(y, 1e-6) / 0.18)
    gain = float(2.0 ** (np.clip(value, -100.0, 100.0) / 100.0))
    new_y = 0.18 * np.power(2.0, stops * gain)
    return _replace_luminance(rgb, y, new_y)


def _tone_curve(rgb: np.ndarray, points: list[tuple[float, float]]) -> np.ndarray:
    y = _luminance(rgb)
    xp = np.array([p[0] for p in points], dtype=np.float32)
    fp = np.array([p[1] for p in points], dtype=np.float32)
    new_y = np.interp(np.clip(y, 0.0, 1.0), xp, fp).astype(np.float32)
    above = y > 1.0
    if np.any(above):
        new_y[above] = y[above]
    return _replace_luminance(rgb, y, new_y)


def _encoded_hsv(rgb_linear: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    encoded = np.clip(_linear_to_srgb(rgb_linear), 0.0, 1.0)
    hsv = cv2.cvtColor(encoded.astype(np.float32), cv2.COLOR_RGB2HSV)
    return encoded, hsv


def _hue_distance(h: np.ndarray, center: float) -> np.ndarray:
    return np.abs(((h - center + 180.0) % 360.0) - 180.0)


HUE_CENTERS = {
    "red": 0.0,
    "orange": 30.0,
    "yellow": 60.0,
    "green": 120.0,
    "aqua": 180.0,
    "blue": 240.0,
    "purple": 280.0,
    "magenta": 320.0,
}


def _hsl(rgb: np.ndarray, op) -> np.ndarray:
    _, hsv = _encoded_hsv(rgb)
    h = hsv[..., 0]
    s = hsv[..., 1]
    v = hsv[..., 2]
    center = HUE_CENTERS[op.channel]
    distance = _hue_distance(h, center)
    weight = np.where(
        distance < 45.0,
        0.5 * (1.0 + np.cos(np.pi * distance / 45.0)),
        0.0,
    ).astype(np.float32)
    h = (h + weight * (float(op.hue) * 0.30)) % 360.0
    s = np.clip(s * (1.0 + weight * float(op.saturation) / 100.0), 0.0, 1.0)
    v = np.clip(v * (1.0 + weight * float(op.luminance) / 150.0), 0.0, 1.0)
    out = cv2.cvtColor(np.dstack([h, s, v]).astype(np.float32), cv2.COLOR_HSV2RGB)
    return _srgb_to_linear(np.clip(out, 0.0, 1.0))


def _saturation(rgb: np.ndarray, value: float, vibrance: bool = False) -> np.ndarray:
    _, hsv = _encoded_hsv(rgb)
    s = hsv[..., 1]
    strength = np.clip(value, -100.0, 100.0) / 100.0
    weight = (1.0 - s) if vibrance and strength > 0 else 1.0
    s = np.clip(s * (1.0 + strength * weight), 0.0, 1.0)
    hsv[..., 1] = s
    encoded = cv2.cvtColor(hsv.astype(np.float32), cv2.COLOR_HSV2RGB)
    return _srgb_to_linear(np.clip(encoded, 0.0, 1.0))


def _clarity(rgb: np.ndarray, value: float, radius_px: float = 24.0) -> np.ndarray:
    y = _luminance(rgb)
    log_y = np.log2(np.maximum(y, 1e-5))
    base = cv2.GaussianBlur(log_y, (0, 0), sigmaX=max(radius_px / 3.0, 0.8))
    detail = log_y - base
    amount = np.clip(value, -60.0, 60.0) / 60.0 * 0.65
    new_y = np.power(2.0, log_y + amount * detail)
    return _replace_luminance(rgb, y, new_y)


def _dehaze(rgb: np.ndarray, value: float) -> np.ndarray:
    amount = np.clip(value, -50.0, 50.0)
    out = _contrast(rgb, amount * 0.35)
    out = _clarity(out, amount * 0.65, radius_px=40.0)
    return out


def _sharpen(rgb: np.ndarray, op) -> np.ndarray:
    y = _luminance(rgb)
    blur = cv2.GaussianBlur(y, (0, 0), sigmaX=max(float(op.radius), 0.2))
    detail = y - blur
    threshold = float(op.threshold)
    if threshold > 0:
        detail = np.where(np.abs(detail) >= threshold, detail, 0.0)
    new_y = np.maximum(y + float(op.amount) * detail, 0.0)
    return _replace_luminance(rgb, y, new_y)


def _denoise(rgb: np.ndarray, op) -> np.ndarray:
    encoded8 = np.clip(_linear_to_srgb(rgb) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    h_luma = float(op.luminance) * 12.0
    h_color = float(op.chroma) * 12.0
    if h_luma <= 0.01 and h_color <= 0.01:
        return rgb.copy()
    den = cv2.fastNlMeansDenoisingColored(encoded8, None, h_luma, h_color, 7, 21)
    den_lin = _srgb_to_linear(den.astype(np.float32) / 255.0)
    keep = float(op.preserve_detail)
    return np.clip(den_lin * (1.0 - keep) + rgb * keep, 0.0, None)


class DevelopEngine:
    """Execute non-generative EditPlan operations deterministically."""

    def __init__(self, mask_resolver: MaskResolver | None = None):
        self.mask_resolver = mask_resolver or MaskResolver()

    def apply(
        self,
        image_path: str | Path,
        plan,
        output_path: str | Path,
        *,
        masks: Mapping[str, object] | None = None,
    ) -> DevelopResult:
        if getattr(plan, "requires_generative", False):
            raise DevelopEngineError("DevelopEngine cannot execute generative operations")

        started = time.perf_counter()
        source = Path(image_path)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source) as opened:
            exif_obj = opened.getexif()
            if 274 in exif_obj:
                exif_obj[274] = 1
            exif = exif_obj.tobytes() if exif_obj else None
            icc = opened.info.get("icc_profile")
            image = ImageOps.exif_transpose(opened).convert("RGB")

        encoded = np.asarray(image, dtype=np.float32) / 255.0
        rgb = _srgb_to_linear(encoded)
        operation_ids: list[str] = []

        for op in plan.operations:
            before = rgb
            kind = op.kind
            if kind == "scalar":
                p, value = op.parameter, float(op.value)
                if p == "exposure_ev":
                    edited = rgb * float(2.0 ** np.clip(value, -5.0, 5.0))
                elif p == "contrast":
                    edited = _contrast(rgb, value)
                elif p in {"highlights", "shadows", "whites", "blacks"}:
                    edited = _tone_region(rgb, p, value)
                elif p == "saturation":
                    edited = _saturation(rgb, value, vibrance=False)
                elif p == "vibrance":
                    edited = _saturation(rgb, value, vibrance=True)
                elif p == "clarity":
                    edited = _clarity(rgb, value)
                elif p == "dehaze":
                    edited = _dehaze(rgb, value)
                elif p in {"temperature", "tint"}:
                    raise DevelopEngineError(
                        f"{p} is schema-valid but not implemented in DevelopEngine {ENGINE_VERSION}; "
                        "do not approximate white balance with RGB channel offsets"
                    )
                else:
                    raise DevelopEngineError(f"Unsupported scalar parameter: {p}")
            elif kind == "tone_curve":
                edited = _tone_curve(rgb, op.points)
            elif kind == "hsl":
                edited = _hsl(rgb, op)
            elif kind == "sharpen":
                edited = _sharpen(rgb, op)
            elif kind == "denoise":
                edited = _denoise(rgb, op)
            elif kind == "geometry":
                raise DevelopEngineError(
                    f"Geometry operations are not implemented in DevelopEngine {ENGINE_VERSION}"
                )
            elif kind == "generative":
                raise DevelopEngineError("Generative operations require a GenerativeEditor")
            else:
                raise DevelopEngineError(f"Unsupported operation kind: {kind}")

            mask = self.mask_resolver.resolve(op.scope, rgb.shape[:2], masks)
            rgb = before * (1.0 - mask[..., None]) + edited * mask[..., None]
            rgb = np.maximum(rgb, 0.0).astype(np.float32)
            operation_ids.append(op.op_id)

        encoded_out = np.clip(_linear_to_srgb(rgb), 0.0, 1.0)
        out8 = (encoded_out * 255.0 + 0.5).astype(np.uint8)
        final = Image.fromarray(out8, "RGB")
        save_kwargs = {}
        suffix = output.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            save_kwargs.update(quality=95, subsampling=0, optimize=True)
        if exif:
            save_kwargs["exif"] = exif
        if icc:
            save_kwargs["icc_profile"] = icc
        final.save(output, **save_kwargs)

        latency = int((time.perf_counter() - started) * 1000)
        return DevelopResult(
            output_path=str(output),
            sha256=_sha256(output),
            width=final.width,
            height=final.height,
            operation_ids=operation_ids,
            latency_ms=latency,
        )

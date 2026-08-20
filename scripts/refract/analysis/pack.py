"""Build a multi-resolution evidence pack for the Refract v2 reviewer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class AnalysisCrop:
    crop_id: str
    role: str
    path: str
    bbox_norm: tuple[float, float, float, float]
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class AnalysisPackManifest:
    schema_version: str
    source_path: str
    source_width: int
    source_height: int
    proxy_path: str
    crops: list[AnalysisCrop]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["crops"] = [asdict(crop) for crop in self.crops]
        return data


def _sha(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return h


def _grid_boxes(width: int, height: int, fraction: float = 0.34, grid: int = 5):
    cw = max(32, min(width, int(width * fraction)))
    ch = max(32, min(height, int(height * fraction)))
    xs = np.linspace(0, max(0, width - cw), grid).astype(int)
    ys = np.linspace(0, max(0, height - ch), grid).astype(int)
    seen: set[tuple[int, int, int, int]] = set()
    for y in ys:
        for x in xs:
            box = (int(x), int(y), int(x + cw), int(y + ch))
            if box not in seen:
                seen.add(box)
                yield box


def _bbox_norm(box, width, height):
    x1, y1, x2, y2 = box
    return (x1 / width, y1 / height, x2 / width, y2 / height)


def _crop_scores(gray: np.ndarray, box) -> tuple[float, float, float]:
    x1, y1, x2, y2 = box
    tile = gray[y1:y2, x1:x2]
    mean = float(np.mean(tile))
    std = float(np.std(tile))
    gx = cv2.Sobel(tile, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(tile, cv2.CV_32F, 0, 1, ksize=3)
    detail = float(np.mean(np.sqrt(gx * gx + gy * gy)))
    highlight = mean + 0.18 * std
    shadow = mean - 0.12 * std
    return highlight, shadow, detail


class AnalysisPackBuilder:
    def __init__(self, proxy_long_edge: int = 2048, jpeg_quality: int = 95):
        self.proxy_long_edge = proxy_long_edge
        self.jpeg_quality = jpeg_quality

    def build(self, image_path: str | Path, output_dir: str | Path) -> AnalysisPackManifest:
        source_path = Path(image_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")

        width, height = image.size
        proxy = image.copy()
        proxy.thumbnail((self.proxy_long_edge, self.proxy_long_edge), Image.Resampling.LANCZOS)
        proxy_path = out / "full-frame.jpg"
        proxy.save(proxy_path, "JPEG", quality=self.jpeg_quality, optimize=True)

        select = image.copy()
        select.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        gray = cv2.cvtColor(np.asarray(select), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        sw, sh = select.size
        boxes = list(_grid_boxes(sw, sh))
        scored = [(box, *_crop_scores(gray, box)) for box in boxes]

        highlight_box = max(scored, key=lambda item: item[1])[0]
        shadow_box = min(scored, key=lambda item: item[2])[0]
        detail_box = max(scored, key=lambda item: item[3])[0]

        subject_w = int(sw * 0.50)
        subject_h = int(sh * 0.50)
        sx = max(0, (sw - subject_w) // 2)
        sy = max(0, (sh - subject_h) // 2)
        subject_box = (sx, sy, sx + subject_w, sy + subject_h)

        def native_box(box):
            x1, y1, x2, y2 = box
            return (
                int(round(x1 * width / sw)),
                int(round(y1 * height / sh)),
                int(round(x2 * width / sw)),
                int(round(y2 * height / sh)),
            )

        crops: list[AnalysisCrop] = []
        for role, box in [
            ("subject", subject_box),
            ("highlight", highlight_box),
            ("shadow", shadow_box),
            ("detail", detail_box),
        ]:
            nbox = native_box(box)
            crop = image.crop(nbox)
            crop_path = out / f"{role}.jpg"
            crop.save(crop_path, "JPEG", quality=self.jpeg_quality, optimize=True)
            crops.append(
                AnalysisCrop(
                    crop_id=role,
                    role=role,
                    path=str(crop_path),
                    bbox_norm=_bbox_norm(nbox, width, height),
                    width=crop.width,
                    height=crop.height,
                    sha256=_sha(crop_path),
                )
            )

        manifest = AnalysisPackManifest(
            schema_version="1.0",
            source_path=str(source_path),
            source_width=width,
            source_height=height,
            proxy_path=str(proxy_path),
            crops=crops,
        )
        (out / "manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2) + "\n")
        return manifest

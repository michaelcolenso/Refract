"""Mask resolution for deterministic Refract v2 edits."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import cv2
import numpy as np
from PIL import Image


class MaskResolutionError(ValueError):
    pass


def _load_mask(value, shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    if isinstance(value, (str, Path)):
        with Image.open(value) as image:
            arr = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
    else:
        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 3:
            arr = arr[..., 0]
        if arr.max(initial=0) > 1.0:
            arr = arr / 255.0
    if arr.shape != (h, w):
        arr = cv2.resize(arr, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(arr, 0.0, 1.0).astype(np.float32)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return (x >= edge1).astype(np.float32)
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


class MaskResolver:
    """Resolve global, gradient, and externally supplied semantic masks."""

    def resolve(
        self,
        scope,
        image_shape: tuple[int, int],
        masks: Mapping[str, object] | None = None,
    ) -> np.ndarray:
        h, w = image_shape
        scope_type = getattr(scope, "type", None)
        if scope_type == "global":
            return np.ones((h, w), dtype=np.float32)

        if scope_type == "linear_gradient":
            sx, sy = scope.start_norm
            ex, ey = scope.end_norm
            yy, xx = np.mgrid[0:h, 0:w]
            x = xx / max(w - 1, 1)
            y = yy / max(h - 1, 1)
            vx, vy = ex - sx, ey - sy
            length2 = vx * vx + vy * vy
            if length2 < 1e-8:
                raise MaskResolutionError("linear gradient start/end cannot be identical")
            t = ((x - sx) * vx + (y - sy) * vy) / length2
            feather = float(scope.feather)
            half_width = max(1e-4, 0.5 * feather)
            return _smoothstep(0.5 - half_width, 0.5 + half_width, t)

        if scope_type == "mask":
            masks = masks or {}
            keys = [
                getattr(scope, "region_id", None),
                getattr(scope, "semantic_query", None),
            ]
            key = next((k for k in keys if k and k in masks), None)
            if key is None:
                wanted = [k for k in keys if k]
                raise MaskResolutionError(f"No external mask supplied for {wanted}")
            mask = _load_mask(masks[key], (h, w))

            expand = int(getattr(scope, "expand_px", 0) or 0)
            if expand:
                radius = abs(expand)
                kernel = cv2.getStructuringElement(
                    cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1)
                )
                if expand > 0:
                    mask = cv2.dilate(mask, kernel)
                else:
                    mask = cv2.erode(mask, kernel)

            feather = int(getattr(scope, "feather_px", 0) or 0)
            if feather > 0:
                mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(feather / 3.0, 0.5))
            return np.clip(mask, 0.0, 1.0).astype(np.float32)

        raise MaskResolutionError(f"Unsupported scope type: {scope_type!r}")

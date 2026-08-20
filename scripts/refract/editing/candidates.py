"""Deterministic candidate generation from a single recommended EditPlan."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Mapping

from .develop import DevelopEngine, ENGINE_NAME, ENGINE_VERSION


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _scale_operation(op, factor: float):
    update = {}
    if op.kind == "scalar":
        update["value"] = float(op.value) * factor
    elif op.kind == "tone_curve":
        update["points"] = [
            (float(x), float(x + factor * (y - x))) for x, y in op.points
        ]
    elif op.kind == "hsl":
        update.update(
            hue=float(op.hue) * factor,
            saturation=float(op.saturation) * factor,
            luminance=float(op.luminance) * factor,
        )
    elif op.kind == "sharpen":
        update["amount"] = float(op.amount) * factor
    elif op.kind == "denoise":
        update.update(
            luminance=float(op.luminance) * factor,
            chroma=float(op.chroma) * factor,
        )
    elif op.kind == "geometry":
        return op
    elif op.kind == "generative":
        raise ValueError("Cannot scale a generative operation into a deterministic candidate")
    return op.model_copy(update=update)


def conservative_plan(plan, factor: float = 0.55):
    if not 0 < factor <= 1:
        raise ValueError("candidate scale factor must be in (0, 1]")
    operations = [_scale_operation(op, factor) for op in plan.operations]
    return plan.model_copy(
        update={
            "plan_id": f"{plan.plan_id}-conservative",
            "strategy": "conservative",
            "operations": operations,
            "requires_generative": False,
        }
    )


class CandidateGenerator:
    """Create O/A/B candidates without additional model calls."""

    def __init__(self, engine: DevelopEngine | None = None, conservative_factor: float = 0.55):
        self.engine = engine or DevelopEngine()
        self.conservative_factor = conservative_factor

    def generate(
        self,
        image_path: str | Path,
        plan,
        output_dir: str | Path,
        *,
        masks: Mapping[str, object] | None = None,
    ):
        from ..domain.models import EditCandidate, EngineInvocation

        if plan.requires_generative:
            raise ValueError("CandidateGenerator phase 1 handles non-generative plans only")

        source = Path(image_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        original_path = out / f"O-original{source.suffix.lower() or '.jpg'}"
        shutil.copy2(source, original_path)
        from PIL import Image
        with Image.open(original_path) as im:
            width, height = im.size

        original = EditCandidate(
            candidate_id=f"O-{uuid.uuid4().hex[:8]}",
            asset_id=plan.asset_id,
            plan_id=None,
            strategy="original",
            output_path=str(original_path),
            sha256=_sha(original_path),
            width=width,
            height=height,
            applied_operations=[],
            engine_chain=[],
            status="generated",
        )
        if plan.strategy == "no_op" or not plan.operations:
            return [original]

        candidates = [original]
        for label, strategy, candidate_plan in [
            ("A", "conservative", conservative_plan(plan, self.conservative_factor)),
            ("B", "recommended", plan.model_copy(update={"strategy": "recommended"})),
        ]:
            output_path = out / f"{label}-{strategy}.jpg"
            result = self.engine.apply(source, candidate_plan, output_path, masks=masks)
            candidates.append(
                EditCandidate(
                    candidate_id=f"{label}-{uuid.uuid4().hex[:8]}",
                    asset_id=plan.asset_id,
                    plan_id=candidate_plan.plan_id,
                    strategy=strategy,
                    output_path=result.output_path,
                    sha256=result.sha256,
                    width=result.width,
                    height=result.height,
                    applied_operations=result.operation_ids,
                    engine_chain=[
                        EngineInvocation(
                            engine=ENGINE_NAME,
                            version=ENGINE_VERSION,
                            operation_ids=result.operation_ids,
                            latency_ms=result.latency_ms,
                            estimated_cost_usd=0.0,
                        )
                    ],
                    status="generated",
                )
            )
        return candidates

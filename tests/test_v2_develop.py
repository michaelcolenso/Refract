from pathlib import Path

import numpy as np
from PIL import Image

from refract.domain.models import (
    EditPlan,
    GlobalScope,
    HSLAdjustment,
    MaskScope,
    ScalarAdjustment,
    SharpenAdjustment,
)
from refract.editing import CandidateGenerator, DevelopEngine


def _plan(operations):
    return EditPlan(
        plan_id="plan-1",
        asset_id="asset-1",
        intent="natural technical refinement",
        strategy="recommended",
        operations=operations,
        preserve=[],
        forbidden=["content synthesis"],
        expected_result=[],
        confidence=0.9,
        requires_generative=False,
    )


def _make_image(path):
    x = np.linspace(0, 255, 256, dtype=np.uint8)
    arr = np.tile(x, (128, 1))
    rgb = np.dstack([arr, np.flip(arr, axis=1), np.full_like(arr, 90)])
    Image.fromarray(rgb).save(path)


def test_exposure_changes_image_and_preserves_size(tmp_path):
    src = tmp_path / "in.jpg"
    _make_image(src)
    plan = _plan([
        ScalarAdjustment(
            op_id="exposure",
            parameter="exposure_ev",
            value=0.5,
            scope=GlobalScope(),
            rationale="lift the frame",
            confidence=0.9,
        )
    ])
    out = tmp_path / "out.jpg"

    result = DevelopEngine().apply(src, plan, out)

    assert result.width == 256 and result.height == 128
    before = np.asarray(Image.open(src), dtype=np.float32).mean()
    after = np.asarray(Image.open(out), dtype=np.float32).mean()
    assert after > before


def test_mask_localizes_edit(tmp_path):
    src = tmp_path / "in.jpg"
    _make_image(src)
    plan = _plan([
        ScalarAdjustment(
            op_id="left-exposure",
            parameter="exposure_ev",
            value=1.0,
            scope=MaskScope(region_id="left", feather_px=0),
            rationale="test local edit",
            confidence=0.9,
        )
    ])
    mask = np.zeros((128, 256), np.float32)
    mask[:, :128] = 1
    out = tmp_path / "out.jpg"

    DevelopEngine().apply(src, plan, out, masks={"left": mask})
    before = np.asarray(Image.open(src), dtype=np.float32)
    after = np.asarray(Image.open(out), dtype=np.float32)

    inside = np.mean(np.abs(after[:, :120] - before[:, :120]))
    outside = np.mean(np.abs(after[:, 140:] - before[:, 140:]))
    assert inside > outside * 3


def test_hsl_and_luminance_sharpen_execute(tmp_path):
    src = tmp_path / "in.jpg"
    _make_image(src)
    plan = _plan([
        HSLAdjustment(
            op_id="blue-hsl",
            channel="blue",
            saturation=20,
            scope=GlobalScope(),
            rationale="increase blue separation",
            confidence=0.8,
        ),
        SharpenAdjustment(
            op_id="sharpen",
            amount=0.3,
            radius=0.8,
            threshold=0.002,
            scope=GlobalScope(),
            rationale="restore edge definition",
            confidence=0.8,
        ),
    ])

    result = DevelopEngine().apply(src, plan, tmp_path / "out.jpg")
    assert result.operation_ids == ["blue-hsl", "sharpen"]


def test_candidate_generator_creates_original_conservative_recommended(tmp_path):
    src = tmp_path / "in.jpg"
    _make_image(src)
    plan = _plan([
        ScalarAdjustment(
            op_id="exposure",
            parameter="exposure_ev",
            value=0.6,
            scope=GlobalScope(),
            rationale="lift exposure",
            confidence=0.9,
        )
    ])

    candidates = CandidateGenerator(conservative_factor=0.55).generate(
        src, plan, tmp_path / "candidates"
    )

    assert [candidate.strategy for candidate in candidates] == [
        "original",
        "conservative",
        "recommended",
    ]
    assert all(Path(candidate.output_path).exists() for candidate in candidates)
    assert candidates[1].plan_id.endswith("-conservative")
    assert candidates[1].engine_chain[0].estimated_cost_usd == 0.0

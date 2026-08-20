"""Tests for Refract v2 typed domain contracts."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from refract.domain.models import (
    ComparativeJudgment,
    EditPlan,
    GlobalScope,
    MaskScope,
    ScalarAdjustment,
)


def test_edit_plan_rejects_incorrect_generative_flag():
    operation = ScalarAdjustment(
        op_id="op-1",
        parameter="shadows",
        value=12,
        scope=GlobalScope(),
        rationale="Reveal architectural detail",
        confidence=0.9,
    )

    with pytest.raises(ValidationError, match="requires_generative"):
        EditPlan(
            plan_id="plan-1",
            asset_id="asset-1",
            intent="Preserve night mood",
            strategy="recommended",
            operations=[operation],
            confidence=0.9,
            requires_generative=True,
        )


def test_mask_scope_requires_region_or_query():
    with pytest.raises(ValidationError, match="region_id or semantic_query"):
        MaskScope()


def test_no_op_plan_cannot_have_operations():
    operation = ScalarAdjustment(
        op_id="op-1",
        parameter="exposure_ev",
        value=0.1,
        scope=GlobalScope(),
        rationale="Small lift",
        confidence=0.8,
    )

    with pytest.raises(ValidationError, match="no_op"):
        EditPlan(
            plan_id="plan-1",
            asset_id="asset-1",
            intent="Do nothing",
            strategy="no_op",
            operations=[operation],
            confidence=1,
            requires_generative=False,
        )


def test_comparative_judgment_requires_complete_ranking():
    with pytest.raises(ValidationError, match="exactly the shown candidates"):
        ComparativeJudgment(
            judgment_id="judge-1",
            asset_id="asset-1",
            candidate_order=["O", "A", "B"],
            ranking=["B", "O"],
            winner_id="B",
            keep_original=False,
            confidence=0.9,
            rationale="B is strongest",
        )


def test_comparative_judgment_requires_winner_first():
    with pytest.raises(ValidationError, match="first ranked candidate"):
        ComparativeJudgment(
            judgment_id="judge-1",
            asset_id="asset-1",
            candidate_order=["O", "A"],
            ranking=["A", "O"],
            winner_id="O",
            keep_original=True,
            confidence=0.9,
            rationale="Mismatch is invalid",
        )

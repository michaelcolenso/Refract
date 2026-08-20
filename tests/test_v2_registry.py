"""Tests for Refract v2 model registry and versioned storage."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from refract.domain.models import (
    CompositionAssessment,
    EvidenceSource,
    PhotoAnalysis,
    SceneAssessment,
    SourceFacts,
    TechnicalAssessment,
)
from refract.providers import (
    FailureKind,
    ModelRegistryError,
    ModelRole,
    classify_provider_error,
    resolve_model_id,
    validate_model_role,
)
from refract.storage import ArtifactStoreError, V2ArtifactStore


def _analysis() -> PhotoAnalysis:
    return PhotoAnalysis(
        analysis_id="analysis-1",
        asset_id="asset-1",
        source=SourceFacts(
            width=2400,
            height=1600,
            bit_depth=8,
            color_space="sRGB",
            file_format="JPEG",
            sha256="abc123",
        ),
        scene=SceneAssessment(
            genre="landscape",
            primary_subject="city skyline",
            intent="moody nighttime cityscape",
            mood="energetic",
            lighting="night",
        ),
        technical=TechnicalAssessment(
            clipped_highlights_pct=0.5,
            clipped_shadows_pct=2.0,
            white_balance="mixed",
            wb_confidence=0.8,
            sharpness_score=0.75,
            motion_blur_likelihood=0.1,
            noise_score=0.35,
        ),
        composition=CompositionAssessment(
            subject_salience=0.8,
            balance=0.85,
            depth=0.7,
        ),
        edit_opportunity=35,
        confidence=0.9,
        provenance=[
            EvidenceSource(source_type="measurement", source="technical-analyzer")
        ],
    )


def test_current_defaults_are_capability_valid():
    assert resolve_model_id(
        role=ModelRole.REVIEW,
        provider="openai",
    ) == "gpt-5.6-sol"
    assert resolve_model_id(
        role=ModelRole.REVIEW,
        provider="google",
    ) == "gemini-3.1-pro-preview"
    assert resolve_model_id(
        role=ModelRole.EDIT,
        provider="google",
    ) == "gemini-3-pro-image"


def test_retired_gemini_model_is_not_registered():
    with pytest.raises(ModelRegistryError):
        validate_model_role("gemini-3-pro-preview", ModelRole.REVIEW)


def test_model_role_mismatch_fails():
    with pytest.raises(ModelRegistryError, match="does not support"):
        validate_model_role("gpt-image-2-2026-04-21", ModelRole.REVIEW)


def test_failure_classifier_distinguishes_quota_from_rate_limit():
    assert (
        classify_provider_error("429 credit_balance_exhausted insufficient_quota")
        == FailureKind.QUOTA
    )
    assert classify_provider_error("429 too many requests") == FailureKind.RATE_LIMIT


def test_artifact_store_round_trip(tmp_path):
    store = V2ArtifactStore(tmp_path)
    analysis = _analysis()

    path = store.write_model("entry-1", "analysis", analysis)
    loaded = store.read_model(path, PhotoAnalysis)

    assert path == tmp_path / "processed" / "entry-1" / "v2" / "analysis.json"
    assert loaded == analysis


def test_artifact_store_rejects_path_traversal(tmp_path):
    store = V2ArtifactStore(tmp_path)
    with pytest.raises(ArtifactStoreError):
        store.artifact_path("../escape", "analysis")

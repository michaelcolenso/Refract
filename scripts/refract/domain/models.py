"""Typed domain contracts for Refract v2.

These models are the stable boundary between analysis, planning, editing,
quality assurance, judging, and persistence. Pixel-mutating code must consume
an EditPlan rather than free-form critique strings.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RefractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceSource(RefractModel):
    source_type: Literal["measurement", "model", "human", "metadata"]
    source: str
    detail: str | None = None


class PreservationConstraint(RefractModel):
    description: str
    importance: Literal["normal", "high", "critical"] = "high"


class SourceFacts(RefractModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    bit_depth: int | None = Field(default=None, gt=0)
    color_space: str | None = None
    file_format: str
    exif: dict[str, str | int | float | None] = Field(default_factory=dict)
    sha256: str


class TechnicalAssessment(RefractModel):
    exposure_ev_bias: float | None = None
    clipped_highlights_pct: float = Field(ge=0, le=100)
    clipped_shadows_pct: float = Field(ge=0, le=100)
    dynamic_range_proxy: float | None = None
    white_balance: Literal["cool", "neutral", "warm", "mixed", "unknown"]
    wb_confidence: float = Field(ge=0, le=1)
    sharpness_score: float = Field(ge=0)
    motion_blur_likelihood: float = Field(ge=0, le=1)
    noise_score: float = Field(ge=0)
    color_cast: str | None = None
    measurements: dict[str, float | int | str] = Field(default_factory=dict)


class SceneAssessment(RefractModel):
    genre: str
    primary_subject: str
    secondary_subjects: list[str] = Field(default_factory=list)
    intent: str
    mood: str
    lighting: str


class CompositionAssessment(RefractModel):
    subject_salience: float = Field(ge=0, le=1)
    balance: float = Field(ge=0, le=1)
    depth: float = Field(ge=0, le=1)
    edge_distractions: list[str] = Field(default_factory=list)
    geometry_notes: list[str] = Field(default_factory=list)
    crop_recommendation: Literal["keep", "consider", "strongly_consider"] = "keep"


class RegionAssessment(RefractModel):
    region_id: str
    label: str
    role: Literal[
        "subject",
        "background",
        "highlight",
        "shadow",
        "detail",
        "face",
        "sky",
        "other",
    ]
    bbox_norm: tuple[float, float, float, float] | None = None
    mask_query: str | None = None
    observations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bbox(self) -> "RegionAssessment":
        if self.bbox_norm is not None:
            x1, y1, x2, y2 = self.bbox_norm
            if not all(0 <= value <= 1 for value in self.bbox_norm):
                raise ValueError("bbox_norm coordinates must be normalized to [0, 1]")
            if x2 <= x1 or y2 <= y1:
                raise ValueError("bbox_norm must have positive width and height")
        return self


class Observation(RefractModel):
    category: Literal[
        "technical",
        "composition",
        "color",
        "tonality",
        "detail",
        "subject",
        "aesthetic",
    ]
    statement: str
    severity: Literal["note", "minor", "moderate", "major"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class PhotoAnalysis(RefractModel):
    schema_version: Literal["2.0"] = "2.0"
    analysis_id: str
    asset_id: str
    source: SourceFacts
    scene: SceneAssessment
    technical: TechnicalAssessment
    composition: CompositionAssessment
    regions: list[RegionAssessment] = Field(default_factory=list)
    strengths: list[Observation] = Field(default_factory=list)
    issues: list[Observation] = Field(default_factory=list)
    preserve: list[PreservationConstraint] = Field(default_factory=list)
    edit_opportunity: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    provenance: list[EvidenceSource] = Field(default_factory=list)


class GlobalScope(RefractModel):
    type: Literal["global"] = "global"


class MaskScope(RefractModel):
    type: Literal["mask"] = "mask"
    region_id: str | None = None
    semantic_query: str | None = None
    feather_px: int = Field(default=32, ge=0)
    expand_px: int = 0

    @model_validator(mode="after")
    def require_target(self) -> "MaskScope":
        if not self.region_id and not self.semantic_query:
            raise ValueError("MaskScope requires region_id or semantic_query")
        return self


class LinearGradientScope(RefractModel):
    type: Literal["linear_gradient"] = "linear_gradient"
    start_norm: tuple[float, float]
    end_norm: tuple[float, float]
    feather: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_points(self) -> "LinearGradientScope":
        points = (*self.start_norm, *self.end_norm)
        if not all(0 <= value <= 1 for value in points):
            raise ValueError("gradient coordinates must be normalized to [0, 1]")
        return self


Scope = Annotated[
    GlobalScope | MaskScope | LinearGradientScope,
    Field(discriminator="type"),
]


class ScalarAdjustment(RefractModel):
    kind: Literal["scalar"] = "scalar"
    op_id: str
    parameter: Literal[
        "exposure_ev",
        "contrast",
        "highlights",
        "shadows",
        "whites",
        "blacks",
        "temperature",
        "tint",
        "vibrance",
        "saturation",
        "clarity",
        "dehaze",
    ]
    value: float
    scope: Scope
    rationale: str
    confidence: float = Field(ge=0, le=1)


class ToneCurveAdjustment(RefractModel):
    kind: Literal["tone_curve"] = "tone_curve"
    op_id: str
    points: list[tuple[float, float]] = Field(min_length=2)
    scope: Scope
    rationale: str
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_curve(self) -> "ToneCurveAdjustment":
        previous_x = -1.0
        for x, y in self.points:
            if not 0 <= x <= 1 or not 0 <= y <= 1:
                raise ValueError("tone curve points must be normalized to [0, 1]")
            if x <= previous_x:
                raise ValueError("tone curve x coordinates must be strictly increasing")
            previous_x = x
        return self


class HSLAdjustment(RefractModel):
    kind: Literal["hsl"] = "hsl"
    op_id: str
    channel: Literal[
        "red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"
    ]
    hue: float = Field(default=0, ge=-100, le=100)
    saturation: float = Field(default=0, ge=-100, le=100)
    luminance: float = Field(default=0, ge=-100, le=100)
    scope: Scope
    rationale: str
    confidence: float = Field(ge=0, le=1)


class SharpenAdjustment(RefractModel):
    kind: Literal["sharpen"] = "sharpen"
    op_id: str
    amount: float = Field(ge=0, le=2)
    radius: float = Field(gt=0, le=5)
    threshold: float = Field(ge=0, le=1)
    scope: Scope
    rationale: str
    confidence: float = Field(ge=0, le=1)


class DenoiseAdjustment(RefractModel):
    kind: Literal["denoise"] = "denoise"
    op_id: str
    luminance: float = Field(ge=0, le=1)
    chroma: float = Field(ge=0, le=1)
    preserve_detail: float = Field(ge=0, le=1)
    scope: Scope
    rationale: str
    confidence: float = Field(ge=0, le=1)


class GeometryAdjustment(RefractModel):
    kind: Literal["geometry"] = "geometry"
    op_id: str
    crop_norm: tuple[float, float, float, float] | None = None
    rotation_deg: float = Field(default=0, ge=-45, le=45)
    vertical: float = Field(default=0, ge=-1, le=1)
    horizontal: float = Field(default=0, ge=-1, le=1)
    rationale: str
    confidence: float = Field(ge=0, le=1)


class GenerativeAdjustment(RefractModel):
    kind: Literal["generative"] = "generative"
    op_id: str
    operation: Literal["remove", "repair", "replace", "extend", "reconstruct", "creative"]
    prompt: str
    scope: MaskScope
    preserve: list[str] = Field(default_factory=list)
    provider_preference: list[str] = Field(default_factory=list)
    rationale: str
    confidence: float = Field(ge=0, le=1)


EditOperation = Annotated[
    ScalarAdjustment
    | ToneCurveAdjustment
    | HSLAdjustment
    | SharpenAdjustment
    | DenoiseAdjustment
    | GeometryAdjustment
    | GenerativeAdjustment,
    Field(discriminator="kind"),
]


class EditPlan(RefractModel):
    schema_version: Literal["2.0"] = "2.0"
    plan_id: str
    asset_id: str
    intent: str
    strategy: Literal[
        "no_op", "conservative", "recommended", "alternate", "retouch", "reimagine"
    ]
    operations: list[EditOperation] = Field(default_factory=list)
    preserve: list[PreservationConstraint] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    expected_result: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    requires_generative: bool

    @model_validator(mode="after")
    def validate_generative_flag(self) -> "EditPlan":
        expected = any(op.kind == "generative" for op in self.operations)
        if self.requires_generative != expected:
            raise ValueError(
                "requires_generative must match presence of generative operations"
            )
        if self.strategy == "no_op" and self.operations:
            raise ValueError("no_op plans cannot contain edit operations")
        return self


class EngineInvocation(RefractModel):
    engine: str
    model: str | None = None
    version: str | None = None
    operation_ids: list[str] = Field(default_factory=list)
    latency_ms: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class CandidateQA(RefractModel):
    valid_image: bool
    dimensions_preserved: bool
    aspect_ratio_delta: float = Field(ge=0)
    clipped_highlights_delta_pct: float
    clipped_shadows_delta_pct: float
    outside_mask_change: float | None = Field(default=None, ge=0)
    inside_mask_change: float | None = Field(default=None, ge=0)
    edit_locality_ratio: float | None = Field(default=None, ge=0)
    sharpness_delta: float | None = None
    structural_similarity: float | None = Field(default=None, ge=0, le=1)
    identity_preservation: float | None = Field(default=None, ge=0, le=1)
    artifact_flags: list[str] = Field(default_factory=list)
    hard_failures: list[str] = Field(default_factory=list)
    passed: bool


class EditCandidate(RefractModel):
    schema_version: Literal["2.0"] = "2.0"
    candidate_id: str
    asset_id: str
    plan_id: str | None = None
    strategy: Literal["original", "conservative", "recommended", "alternate", "generative"]
    output_path: str
    sha256: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    applied_operations: list[str] = Field(default_factory=list)
    engine_chain: list[EngineInvocation] = Field(default_factory=list)
    qa: CandidateQA | None = None
    status: Literal[
        "generated", "qa_pass", "qa_fail", "judged", "selected", "rejected"
    ] = "generated"


class DimensionJudgment(RefractModel):
    best_candidate_id: str
    notes: str


class CandidateRegression(RefractModel):
    candidate_id: str
    category: Literal[
        "identity",
        "composition",
        "tonality",
        "color",
        "detail",
        "artifact",
        "overprocessing",
        "intent",
    ]
    severity: Literal["minor", "moderate", "major", "fatal"]
    description: str


class RetryInstruction(RefractModel):
    candidate_id: str
    operation_ids_to_change: list[str] = Field(default_factory=list)
    instruction: str
    max_retries: int = Field(default=1, ge=0, le=3)


class ComparativeJudgment(RefractModel):
    schema_version: Literal["2.0"] = "2.0"
    judgment_id: str
    asset_id: str
    candidate_order: list[str] = Field(min_length=1)
    ranking: list[str] = Field(min_length=1)
    winner_id: str
    keep_original: bool
    confidence: float = Field(ge=0, le=1)
    dimensions: dict[str, DimensionJudgment] = Field(default_factory=dict)
    regressions: list[CandidateRegression] = Field(default_factory=list)
    hard_rejections: list[str] = Field(default_factory=list)
    rationale: str
    retry: RetryInstruction | None = None
    needs_escalation: bool = False

    @model_validator(mode="after")
    def validate_candidate_sets(self) -> "ComparativeJudgment":
        shown = set(self.candidate_order)
        ranked = set(self.ranking)
        if len(shown) != len(self.candidate_order):
            raise ValueError("candidate_order cannot contain duplicates")
        if len(ranked) != len(self.ranking):
            raise ValueError("ranking cannot contain duplicates")
        if shown != ranked:
            raise ValueError("ranking must contain exactly the shown candidates")
        if self.winner_id != self.ranking[0]:
            raise ValueError("winner_id must equal the first ranked candidate")
        return self


ArtifactModel = PhotoAnalysis | EditPlan | EditCandidate | ComparativeJudgment

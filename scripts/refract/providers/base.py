"""Provider interfaces and normalized provider failures for Refract v2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from refract.domain import ComparativeJudgment, EditCandidate, EditPlan, PhotoAnalysis


class FailureKind(str, Enum):
    AUTH = "auth"
    QUOTA = "quota"
    RATE_LIMIT = "rate_limit"
    MODEL_RETIRED = "model_retired"
    UNAVAILABLE = "unavailable"
    INVALID_REQUEST = "invalid_request"
    REFUSAL = "refusal"
    UNKNOWN = "unknown"


class ProviderFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        kind: FailureKind = FailureKind.UNKNOWN,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.kind = kind
        self.retryable = retryable
        self.status_code = status_code


def classify_provider_error(error: Exception | str) -> FailureKind:
    text = str(error).lower()

    if any(token in text for token in ("credit_balance_exhausted", "insufficient_quota", "no credits")):
        return FailureKind.QUOTA
    if any(token in text for token in ("deprecated", "no longer available", "model_not_found", "model retired")):
        return FailureKind.MODEL_RETIRED
    if any(token in text for token in ("unauthorized", "invalid api key", "authentication", "401")):
        return FailureKind.AUTH
    if any(token in text for token in ("rate limit", "too many requests", "429")):
        return FailureKind.RATE_LIMIT
    if any(token in text for token in ("service unavailable", "temporarily unavailable", "503", "502")):
        return FailureKind.UNAVAILABLE
    if any(token in text for token in ("invalid_request", "bad request", "400")):
        return FailureKind.INVALID_REQUEST
    if "refusal" in text or "refused" in text:
        return FailureKind.REFUSAL
    return FailureKind.UNKNOWN


class ReviewProvider(ABC):
    provider_name: str
    model_id: str

    @abstractmethod
    def analyze(
        self,
        *,
        asset_id: str,
        images: Sequence[Path],
        technical_facts: dict[str, Any],
    ) -> PhotoAnalysis:
        raise NotImplementedError

    @abstractmethod
    def plan(self, analysis: PhotoAnalysis) -> EditPlan:
        raise NotImplementedError


class JudgeProvider(ABC):
    provider_name: str
    model_id: str

    @abstractmethod
    def judge(
        self,
        *,
        analysis: PhotoAnalysis,
        candidates: Sequence[EditCandidate],
    ) -> ComparativeJudgment:
        raise NotImplementedError


class ImageEditProvider(ABC):
    provider_name: str
    model_id: str

    @abstractmethod
    def edit(
        self,
        *,
        source: Path,
        plan: EditPlan,
        output: Path,
    ) -> None:
        raise NotImplementedError


class MaskProvider(ABC):
    provider_name: str

    @abstractmethod
    def create_mask(
        self,
        *,
        source: Path,
        query: str,
        output: Path,
    ) -> None:
        raise NotImplementedError

"""Provider abstractions and capability registry for Refract v2."""

from .base import (
    FailureKind,
    ImageEditProvider,
    JudgeProvider,
    MaskProvider,
    ProviderFailure,
    ReviewProvider,
    classify_provider_error,
)
from .registry import (
    MODEL_REGISTRY,
    ModelCapability,
    ModelRegistryError,
    ModelRole,
    default_model_id,
    resolve_model_id,
    validate_model_role,
)

__all__ = [
    "FailureKind",
    "ImageEditProvider",
    "JudgeProvider",
    "MODEL_REGISTRY",
    "MaskProvider",
    "ModelCapability",
    "ModelRegistryError",
    "ModelRole",
    "ProviderFailure",
    "ReviewProvider",
    "classify_provider_error",
    "default_model_id",
    "resolve_model_id",
    "validate_model_role",
]

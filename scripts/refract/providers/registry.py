"""Capability-aware model registry for Refract v2.

No v2 provider should bury a model ID inside its implementation. Stable aliases
and pinned snapshots are declared here and may be overridden by environment.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, ConfigDict


class ModelRole(str, Enum):
    REVIEW = "review"
    JUDGE = "judge"
    ARBITRATE = "arbitrate"
    GENERATE = "generate"
    EDIT = "edit"
    MASK = "mask"


class ModelCapability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model_id: str
    roles: frozenset[ModelRole]
    image_input: bool
    image_output: bool
    structured_output: bool
    stable: bool
    pinned: bool
    enabled: bool = True


def _cap(
    provider: str,
    model_id: str,
    roles: Iterable[ModelRole],
    *,
    image_input: bool,
    image_output: bool,
    structured_output: bool,
    stable: bool,
    pinned: bool = False,
) -> ModelCapability:
    return ModelCapability(
        provider=provider,
        model_id=model_id,
        roles=frozenset(roles),
        image_input=image_input,
        image_output=image_output,
        structured_output=structured_output,
        stable=stable,
        pinned=pinned,
    )


MODEL_REGISTRY: dict[str, ModelCapability] = {
    "gpt-5.6-sol": _cap(
        "openai",
        "gpt-5.6-sol",
        [ModelRole.REVIEW, ModelRole.JUDGE, ModelRole.ARBITRATE],
        image_input=True,
        image_output=False,
        structured_output=True,
        stable=True,
    ),
    "claude-sonnet-5": _cap(
        "anthropic",
        "claude-sonnet-5",
        [ModelRole.REVIEW, ModelRole.JUDGE],
        image_input=True,
        image_output=False,
        structured_output=True,
        stable=True,
    ),
    "claude-fable-5": _cap(
        "anthropic",
        "claude-fable-5",
        [ModelRole.JUDGE, ModelRole.ARBITRATE],
        image_input=True,
        image_output=False,
        structured_output=True,
        stable=True,
    ),
    "gemini-3.1-pro-preview": _cap(
        "google",
        "gemini-3.1-pro-preview",
        [ModelRole.REVIEW, ModelRole.JUDGE],
        image_input=True,
        image_output=False,
        structured_output=True,
        stable=False,
    ),
    "gpt-image-2-2026-04-21": _cap(
        "openai",
        "gpt-image-2-2026-04-21",
        [ModelRole.GENERATE, ModelRole.EDIT],
        image_input=True,
        image_output=True,
        structured_output=False,
        stable=True,
        pinned=True,
    ),
    "gemini-3-pro-image": _cap(
        "google",
        "gemini-3-pro-image",
        [ModelRole.GENERATE, ModelRole.EDIT],
        image_input=True,
        image_output=True,
        structured_output=True,
        stable=True,
    ),
    "gemini-3.1-flash-image": _cap(
        "google",
        "gemini-3.1-flash-image",
        [ModelRole.GENERATE, ModelRole.EDIT],
        image_input=True,
        image_output=True,
        structured_output=True,
        stable=True,
    ),
}


DEFAULT_MODELS: dict[tuple[ModelRole, str], str] = {
    (ModelRole.REVIEW, "openai"): "gpt-5.6-sol",
    (ModelRole.REVIEW, "anthropic"): "claude-sonnet-5",
    (ModelRole.REVIEW, "google"): "gemini-3.1-pro-preview",
    (ModelRole.JUDGE, "anthropic"): "claude-sonnet-5",
    (ModelRole.ARBITRATE, "anthropic"): "claude-fable-5",
    (ModelRole.EDIT, "openai"): "gpt-image-2-2026-04-21",
    (ModelRole.GENERATE, "openai"): "gpt-image-2-2026-04-21",
    (ModelRole.EDIT, "google"): "gemini-3-pro-image",
    (ModelRole.GENERATE, "google"): "gemini-3-pro-image",
}


class ModelRegistryError(ValueError):
    pass


def get_model(model_id: str) -> ModelCapability:
    try:
        return MODEL_REGISTRY[model_id]
    except KeyError as exc:
        raise ModelRegistryError(f"Unregistered Refract model: {model_id}") from exc


def default_model_id(role: ModelRole | str, provider: str) -> str:
    role = ModelRole(role)
    key = (role, provider.lower())
    try:
        return DEFAULT_MODELS[key]
    except KeyError as exc:
        raise ModelRegistryError(
            f"No default model registered for role={role.value!r}, provider={provider!r}"
        ) from exc


def validate_model_role(
    model_id: str,
    role: ModelRole | str,
    *,
    provider: str | None = None,
) -> ModelCapability:
    role = ModelRole(role)
    capability = get_model(model_id)

    if not capability.enabled:
        raise ModelRegistryError(f"Model is disabled: {model_id}")
    if role not in capability.roles:
        raise ModelRegistryError(
            f"Model {model_id} does not support Refract role {role.value}"
        )
    if provider is not None and capability.provider != provider.lower():
        raise ModelRegistryError(
            f"Model {model_id} belongs to {capability.provider}, not {provider}"
        )
    if role in (ModelRole.REVIEW, ModelRole.JUDGE, ModelRole.ARBITRATE):
        if not capability.image_input:
            raise ModelRegistryError(f"Model {model_id} lacks image input")
        if not capability.structured_output:
            raise ModelRegistryError(f"Model {model_id} lacks structured output")
    if role in (ModelRole.EDIT, ModelRole.GENERATE) and not capability.image_output:
        raise ModelRegistryError(f"Model {model_id} lacks image output")

    return capability


def resolve_model_id(
    *,
    role: ModelRole | str,
    provider: str,
    env_var: str | None = None,
    configured: str | None = None,
    strict: bool = True,
) -> str:
    """Resolve a model ID from explicit value, environment, or registry default.

    strict=False is intended only for the temporary legacy pipeline so existing
    custom model IDs continue to function while v2 adapters require registered
    capabilities.
    """

    role = ModelRole(role)
    model_id = configured
    if model_id is None and env_var:
        model_id = os.getenv(env_var)
    if not model_id:
        model_id = default_model_id(role, provider)

    if strict:
        validate_model_role(model_id, role, provider=provider)

    return model_id

"""Public request contracts and config validators for built-in capabilities."""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from deeptutor.agents.math_animator.request_config import (
    MathAnimatorRequestConfig,
    validate_math_animator_request_config,
)
from deeptutor.agents.research.request_config import (
    DeepResearchRequestConfig,
    validate_research_request_config,
)

_RUNTIME_ONLY_KEYS = {
    "_persist_user_message",
    "followup_question_context",
    # Per-turn subagent consult budget (composer stepper). Not part of any
    # capability's public config schema; stripped here so it never trips
    # ``extra="forbid"`` (turn_runtime carries it through to the turn config).
    "subagent_consult_budget",
    # Subject scope (composer SubjectSelector). The composer builds the whole
    # turn config, so the selected subject rides in ``config`` — but it is not
    # a capability parameter, and ``ChatRequestConfig`` declares no fields with
    # ``extra="forbid"``, so an unlisted key rejects the entire turn. Stripped
    # here and read back out of the turn config by ``turn_runtime``, which
    # drives the M5 subject context injection.
    "subject_id",
}


class ReasoningOverride(BaseModel):
    """The formal per-turn reasoning selection.

    ``inherit`` and ``provider_default`` are selection modes, not vendor
    effort strings.  Only ``effort`` may carry a level.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["inherit", "provider_default", "effort"] = "inherit"
    effort: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _validate_effort(self) -> "ReasoningOverride":
        if self.mode == "effort":
            if not isinstance(self.effort, str) or not self.effort.strip():
                raise ValueError("reasoning_override.effort is required when mode=effort")
        elif self.effort not in (None, ""):
            raise ValueError("reasoning_override.effort is only valid when mode=effort")
        return self


class ChatRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeepSolveRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeepQuestionRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["custom", "mimic"] = "custom"
    topic: str = ""
    num_questions: int = Field(default=1, ge=1, le=50)
    difficulty: str = ""
    # Allowed-types whitelist. Empty list means "any type — let the
    # planner pick per question". Frontend sends the user's multi-select.
    question_types: list[str] = Field(default_factory=list)
    # Optional per-type quantity targets. When non-empty, sum must equal
    # ``num_questions`` (frontend keeps them in sync). Empty dict means
    # "no per-type targets — distribute freely across allowed types".
    per_type_counts: dict[str, int] = Field(default_factory=dict)
    paper_path: str = ""
    max_questions: int = Field(default=10, ge=1, le=100)


class VisualizeRequestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_mode: Literal[
        "auto",
        "svg",
        "chartjs",
        "mermaid",
        "html",
        "manim_video",
        "manim_image",
    ] = "auto"
    # Only meaningful when the routed render_type is manim_video / manim_image
    # (either chosen explicitly or selected by AnalysisAgent in auto mode).
    # Mirrors MathAnimatorRequestConfig defaults so the auto path stays
    # zero-config.
    quality: Literal["low", "medium", "high"] = "medium"
    style_hint: str = Field(default="", max_length=500)


def _clean_public_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    if raw_config is None:
        return {}
    if not isinstance(raw_config, dict):
        raise ValueError("Capability config must be an object.")
    cleaned = dict(raw_config)
    for key in _RUNTIME_ONLY_KEYS:
        cleaned.pop(key, None)
    return cleaned


def _validate_model(
    model_type: type[BaseModel],
    raw_config: dict[str, Any] | None,
    *,
    label: str,
) -> BaseModel:
    cleaned = _clean_public_config(raw_config)
    try:
        return model_type.model_validate(cleaned)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValueError(f"Invalid {label} config: {details}") from exc


def validate_chat_request_config(raw_config: dict[str, Any] | None) -> ChatRequestConfig:
    return _validate_model(ChatRequestConfig, raw_config, label="chat")


def validate_reasoning_override(value: Any) -> dict[str, Any]:
    """Validate the formal turn field and return its normalized shape."""

    if value is None:
        return {"mode": "inherit"}
    if isinstance(value, ReasoningOverride):
        return value.model_dump(exclude_none=True)
    if not isinstance(value, dict):
        raise ValueError("reasoning_override must be an object.")
    try:
        model = ReasoningOverride.model_validate(value)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValueError(f"Invalid reasoning_override: {details}") from exc
    normalized = model.model_dump(exclude_none=True)
    if normalized.get("effort") == "":
        normalized.pop("effort", None)
    return normalized


def validate_deep_solve_request_config(
    raw_config: dict[str, Any] | None,
) -> DeepSolveRequestConfig:
    return _validate_model(DeepSolveRequestConfig, raw_config, label="deep solve")


def validate_deep_question_request_config(
    raw_config: dict[str, Any] | None,
) -> DeepQuestionRequestConfig:
    return _validate_model(DeepQuestionRequestConfig, raw_config, label="deep question")


def validate_visualize_request_config(
    raw_config: dict[str, Any] | None,
) -> VisualizeRequestConfig:
    return _validate_model(VisualizeRequestConfig, raw_config, label="visualize")


def build_request_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    return model_type.model_json_schema(mode="validation")


CAPABILITY_CONFIG_VALIDATORS: dict[str, Callable[[dict[str, Any] | None], Any]] = {
    "chat": validate_chat_request_config,
    "deep_solve": validate_deep_solve_request_config,
    "deep_question": validate_deep_question_request_config,
    "deep_research": validate_research_request_config,
    "math_animator": validate_math_animator_request_config,
    "visualize": validate_visualize_request_config,
}

CAPABILITY_REQUEST_SCHEMAS: dict[str, dict[str, Any]] = {
    "chat": build_request_schema(ChatRequestConfig),
    "deep_solve": build_request_schema(DeepSolveRequestConfig),
    "deep_question": build_request_schema(DeepQuestionRequestConfig),
    "deep_research": build_request_schema(DeepResearchRequestConfig),
    "math_animator": build_request_schema(MathAnimatorRequestConfig),
    "visualize": build_request_schema(VisualizeRequestConfig),
}


def validate_capability_config(
    capability: str, raw_config: dict[str, Any] | None
) -> dict[str, Any]:
    validator = CAPABILITY_CONFIG_VALIDATORS.get(capability)
    if validator is None:
        return _clean_public_config(raw_config)
    model = validator(raw_config)
    if isinstance(model, BaseModel):
        normalized = model.model_dump(exclude_none=True)
    if normalized.get("effort") == "":
        normalized.pop("effort", None)
    return normalized
    return _clean_public_config(raw_config)


def get_capability_request_schema(capability: str) -> dict[str, Any]:
    return dict(CAPABILITY_REQUEST_SCHEMAS.get(capability, {}))


__all__ = [
    "CAPABILITY_CONFIG_VALIDATORS",
    "CAPABILITY_REQUEST_SCHEMAS",
    "ChatRequestConfig",
    "DeepQuestionRequestConfig",
    "DeepSolveRequestConfig",
    "ReasoningOverride",
    "VisualizeRequestConfig",
    "build_request_schema",
    "get_capability_request_schema",
    "validate_capability_config",
    "validate_chat_request_config",
    "validate_deep_question_request_config",
    "validate_deep_solve_request_config",
    "validate_reasoning_override",
    "validate_visualize_request_config",
]

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

ANTHROPIC_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
OPENAI_EVAL_MAX_OUTPUT_TOKENS = int(os.getenv("DS_RADAR_OPENAI_EVAL_MAX_OUTPUT_TOKENS", "1600"))
OPENAI_EVAL_RETRY_MAX_OUTPUT_TOKENS = int(
    os.getenv("DS_RADAR_OPENAI_EVAL_RETRY_MAX_OUTPUT_TOKENS", str(max(2200, OPENAI_EVAL_MAX_OUTPUT_TOKENS + 600)))
)

DEFAULT_PROVIDER_BY_TASK = {
    "eval": "anthropic",
    "cv": "anthropic",
    "brief": "anthropic",
    "interview": "anthropic",
    "outreach": "anthropic",
    "cover": "anthropic",
}


@dataclass(frozen=True)
class LLMUsage:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class EvaluationScores(BaseModel):
    role_match: float = Field(ge=0.0, le=5.0)
    skills_alignment: float = Field(ge=0.0, le=5.0)
    seniority: float = Field(ge=0.0, le=5.0)
    compensation: float = Field(ge=0.0, le=5.0)
    interview_likelihood: float = Field(ge=0.0, le=5.0)
    geography: float = Field(ge=0.0, le=5.0)
    company_stage: float = Field(ge=0.0, le=5.0)
    product_interest: float = Field(ge=0.0, le=5.0)
    growth_trajectory: float = Field(ge=0.0, le=5.0)
    timeline: float = Field(ge=0.0, le=5.0)


class EvaluationResult(BaseModel):
    title: str
    company: str
    location: str
    salary_visible: str | None = None
    scores: EvaluationScores
    summary: str
    top_keywords: list[str] = Field(default_factory=list, max_length=8)
    interview_angle: str | None = None


def _openai_debug_enabled() -> bool:
    return os.getenv("DS_RADAR_OPENAI_DEBUG", "").strip() == "1"


def _openai_debug(message: str) -> None:
    if _openai_debug_enabled():
        print(f"[OPENAI DEBUG] {message}")


def _env_name(task: str, suffix: str) -> str:
    return f"DS_RADAR_{task.upper()}_{suffix}"


def _provider_for_model(model: str) -> str:
    clean = (model or "").strip().lower()
    if clean.startswith("claude"):
        return "anthropic"
    if clean.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    return "anthropic"


def get_provider(task: str) -> str:
    model_override = os.getenv("MODEL_OVERRIDE", "").strip()
    if model_override:
        return _provider_for_model(model_override)

    task_model = os.getenv(_env_name(task, "MODEL"))
    if task_model:
        return _provider_for_model(task_model)

    shared_model = os.getenv("DS_RADAR_MODEL")
    if shared_model:
        return _provider_for_model(shared_model)

    raw = (
        os.getenv(_env_name(task, "PROVIDER"))
        or os.getenv("DS_RADAR_LLM_PROVIDER")
        or DEFAULT_PROVIDER_BY_TASK.get(task, "anthropic")
    ).strip().lower()
    if raw not in {"openai", "anthropic"}:
        raise ValueError(f"Unsupported provider '{raw}' for task '{task}'")
    return raw


def get_model(task: str, provider: str | None = None) -> str:
    provider = provider or get_provider(task)
    configured = (
        os.getenv("MODEL_OVERRIDE")
        or os.getenv(_env_name(task, "MODEL"))
        or os.getenv("DS_RADAR_MODEL")
    )
    if configured:
        return configured.strip()
    return ANTHROPIC_DEFAULT_MODEL


def describe_task_model(task: str) -> str:
    provider = get_provider(task)
    model = get_model(task, provider=provider)
    return f"{provider}/{model}"


def _get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def _openai_usage(response, *, task: str) -> LLMUsage:
    usage = getattr(response, "usage", None)
    provider = get_provider(task)
    model = get_model(task, provider=provider)
    return LLMUsage(
        provider=provider,
        model=model,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
    )


def _anthropic_usage(response, *, task: str) -> LLMUsage:
    usage = getattr(response, "usage", None)
    provider = get_provider(task)
    model = get_model(task, provider=provider)
    return LLMUsage(
        provider=provider,
        model=model,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
    )


def format_usage(usage: LLMUsage, *, label: str) -> str:
    return (
        f"[LLM] {label} {usage.provider}/{usage.model} | "
        f"{usage.input_tokens} in / {usage.output_tokens} out"
    )


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json|markdown)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned


def _safe_json_loads(raw: str) -> dict[str, Any]:
    raw_str = raw.strip()
    try:
        return json.loads(raw_str)
    except json.JSONDecodeError as original_error:
        last_brace = raw_str.rfind("}")
        last_bracket = raw_str.rfind("]")
        cutoff = max(last_brace, last_bracket)
        if cutoff == -1:
            raise original_error
        trimmed = raw_str[:cutoff + 1]
        return json.loads(trimmed)


def _to_plain_data(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_to_plain_data(item) for item in value]
    try:
        return dict(value)
    except Exception:
        return value


def _extract_openai_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _response_refusal_text(response) -> str:
    refusals: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            refusal = getattr(content, "refusal", None)
            if refusal:
                refusals.append(str(refusal).strip())
            if getattr(content, "type", None) == "refusal":
                text = getattr(content, "refusal", None)
                if text:
                    refusals.append(str(text).strip())
    return "\n".join(part for part in refusals if part).strip()


def _openai_output_types(response) -> list[str]:
    return [getattr(item, "type", "?") for item in getattr(response, "output", []) or []]


def _build_openai_parse_error(
    response,
    *,
    extra: str = "",
    initial_max_output_tokens: int | None = None,
    retry_max_output_tokens: int | None = None,
) -> RuntimeError:
    status = getattr(response, "status", None) or "unknown"
    incomplete = _to_plain_data(getattr(response, "incomplete_details", None))
    refusal = _response_refusal_text(response)
    output_types = _openai_output_types(response)
    raw_text = _extract_openai_text(response)
    parts = [
        f"OpenAI structured evaluation parse failed: status={status}",
        f"model={getattr(response, 'model', 'unknown')}",
    ]
    if initial_max_output_tokens is not None:
        parts.append(f"initial_max_output_tokens={initial_max_output_tokens}")
    if retry_max_output_tokens is not None:
        parts.append(f"retry_max_output_tokens={retry_max_output_tokens}")
    if incomplete:
        parts.append(f"incomplete={incomplete}")
    if refusal:
        parts.append(f"refusal={refusal}")
    if output_types:
        parts.append(f"output_types={output_types}")
    if extra:
        parts.append(extra)
    if raw_text:
        preview = raw_text.replace("\n", " ")[:240]
        parts.append(f"raw_text_preview={preview}")
    return RuntimeError(" | ".join(parts))


def _extract_openai_parsed(
    response,
    schema: type[BaseModel],
    *,
    initial_max_output_tokens: int | None = None,
    retry_max_output_tokens: int | None = None,
) -> dict[str, Any]:
    _openai_debug(
        f"model={getattr(response, 'model', 'unknown')} status={getattr(response, 'status', None)} "
        f"incomplete={_to_plain_data(getattr(response, 'incomplete_details', None)) or 'none'}"
    )

    direct_candidates = [
        getattr(response, "output_parsed", None),
        getattr(response, "parsed", None),
    ]
    for candidate in direct_candidates:
        plain = _to_plain_data(candidate)
        if plain:
            validated = schema.model_validate(plain).model_dump()
            _openai_debug("parsed content found directly on response object")
            return validated

    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            parsed = _to_plain_data(getattr(content, "parsed", None))
            if parsed:
                validated = schema.model_validate(parsed).model_dump()
                _openai_debug("parsed content found on message content")
                return validated

    refusal = _response_refusal_text(response)
    if refusal:
        _openai_debug("refusal marker found before fallback parsing")
        raise _build_openai_parse_error(
            response,
            extra="model returned a refusal",
            initial_max_output_tokens=initial_max_output_tokens,
            retry_max_output_tokens=retry_max_output_tokens,
        )

    raw_text = _extract_openai_text(response)
    if raw_text:
        cleaned = _strip_code_fences(raw_text)
        try:
            parsed_json = _safe_json_loads(cleaned)
            validated = schema.model_validate(parsed_json).model_dump()
            _openai_debug("fallback JSON extraction used from raw output_text")
            return validated
        except Exception as exc:
            _openai_debug(f"fallback JSON extraction failed: {exc}")

    incomplete = _to_plain_data(getattr(response, "incomplete_details", None))
    if incomplete:
        _openai_debug("response incomplete without recoverable parsed payload")
        raise _build_openai_parse_error(
            response,
            extra=f"response incomplete: {incomplete}",
            initial_max_output_tokens=initial_max_output_tokens,
            retry_max_output_tokens=retry_max_output_tokens,
        )

    raise _build_openai_parse_error(
        response,
        extra="no parsed payload found after direct and JSON fallback checks",
        initial_max_output_tokens=initial_max_output_tokens,
        retry_max_output_tokens=retry_max_output_tokens,
    )


def _openai_eval_max_output_tokens() -> int:
    return max(800, OPENAI_EVAL_MAX_OUTPUT_TOKENS)


def _openai_eval_retry_max_output_tokens(initial: int) -> int:
    return max(initial + 400, OPENAI_EVAL_RETRY_MAX_OUTPUT_TOKENS)


def _is_openai_max_output_incomplete(response) -> bool:
    if getattr(response, "status", None) != "incomplete":
        return False
    details = _to_plain_data(getattr(response, "incomplete_details", None)) or {}
    if isinstance(details, dict):
        return details.get("reason") == "max_output_tokens"
    return False


def _create_openai_eval_response(client, *, model: str, system: str, prompt: str, max_output_tokens: int):
    return client.responses.parse(
        model=model,
        instructions=system,
        input=prompt,
        max_output_tokens=max_output_tokens,
        text_format=EvaluationResult,
        reasoning={"effort": "low"},
        text={"verbosity": "low"},
    )


def _anthropic_create_with_retry(**kwargs):
    import anthropic

    client = _get_anthropic_client()
    delay = 15
    for attempt in range(4):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt == 3:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 120)


def run_text_prompt(
    *,
    task: str,
    system: str,
    prompt: str,
    max_output_tokens: int,
    temperature: float = 0.0,
    provider: str | None = None,
) -> tuple[str, LLMUsage]:
    provider = provider or get_provider(task)
    model = get_model(task, provider=provider)

    if provider == "openai":
        client = _get_openai_client()
        response = client.responses.create(
            model=model,
            instructions=system,
            input=prompt,
            max_output_tokens=max_output_tokens,
        )
        return _extract_openai_text(response).strip(), _openai_usage(response, task=task)

    response = _anthropic_create_with_retry(
        model=model,
        max_tokens=max_output_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in getattr(response, "content", []) if getattr(block, "type", "") == "text"
    ).strip()
    return text, _anthropic_usage(response, task=task)


def run_json_prompt(
    *,
    task: str,
    system: str,
    prompt: str,
    max_output_tokens: int,
    temperature: float = 0.0,
    provider: str | None = None,
) -> tuple[dict[str, Any], LLMUsage, str]:
    provider = provider or get_provider(task)
    model = get_model(task, provider=provider)
    attempts = 2 if provider == "anthropic" and task == "eval" else 1
    last_error: RuntimeError | None = None

    for attempt in range(1, attempts + 1):
        raw_text, usage = run_text_prompt(
            task=task,
            system=system,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            provider=provider,
        )
        cleaned = _strip_code_fences(raw_text)
        preview = cleaned.replace("\n", " ")[:240] if cleaned else "<empty>"

        if not cleaned:
            last_error = RuntimeError(
                f"{provider}/{model} returned empty text for JSON task '{task}' "
                f"(attempt {attempt}/{attempts})"
            )
            if attempt < attempts:
                continue
            raise last_error

        try:
            return _safe_json_loads(cleaned), usage, cleaned
        except json.JSONDecodeError as exc:
            last_error = RuntimeError(
                f"{provider}/{model} returned invalid JSON for task '{task}' "
                f"(attempt {attempt}/{attempts}): {exc}. raw_preview={preview}"
            )
            if attempt < attempts:
                continue
            raise last_error from exc

    assert last_error is not None
    raise last_error


def run_job_evaluation(*, system: str, prompt: str) -> tuple[dict[str, Any], LLMUsage]:
    provider = get_provider("eval")
    model = get_model("eval", provider=provider)

    if provider == "openai":
        client = _get_openai_client()
        initial_max_output_tokens = _openai_eval_max_output_tokens()
        retry_max_output_tokens: int | None = None
        _openai_debug(f"run_job_evaluation model={model} max_output_tokens={initial_max_output_tokens}")
        response = _create_openai_eval_response(
            client,
            model=model,
            system=system,
            prompt=prompt,
            max_output_tokens=initial_max_output_tokens,
        )
        if _is_openai_max_output_incomplete(response):
            retry_max_output_tokens = _openai_eval_retry_max_output_tokens(initial_max_output_tokens)
            _openai_debug(
                "eval response incomplete due to max_output_tokens; "
                f"retrying once with max_output_tokens={retry_max_output_tokens} "
                f"output_types={_openai_output_types(response)}"
            )
            response = _create_openai_eval_response(
                client,
                model=model,
                system=system,
                prompt=prompt,
                max_output_tokens=retry_max_output_tokens,
            )
        return _extract_openai_parsed(
            response,
            EvaluationResult,
            initial_max_output_tokens=initial_max_output_tokens,
            retry_max_output_tokens=retry_max_output_tokens,
        ), _openai_usage(response, task="eval")

    raw_result, usage, _ = run_json_prompt(
        task="eval",
        system=system,
        prompt=prompt,
        max_output_tokens=900,
        temperature=0,
        provider="anthropic",
    )
    validated = EvaluationResult.model_validate(raw_result)
    return validated.model_dump(), usage


def run_cv_tailoring(*, system: str, prompt: str, max_output_tokens: int) -> tuple[str, LLMUsage]:
    return run_text_prompt(
        task="cv",
        system=system,
        prompt=prompt,
        max_output_tokens=max_output_tokens,
        temperature=0,
    )

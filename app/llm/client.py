"""Talk to a language model and get back checked, structured answers.

The rest of the project only sees `LLM.generate(system, prompt, schema)`. This file hides
which provider is behind it, retries when the service is busy, and moves on to the next model
in the list when one is gone, too slow or out of quota. Free-tier models change names and
availability often, so the list of models comes from the settings and not from the code.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

BUSY_WAITS = (2.0, 5.0, 10.0)  # seconds to wait before each retry when a model is busy
FORMAT_RETRIES = 1  # extra tries when the reply is not valid for the schema
QUOTA_WAIT = 20.0  # seconds to wait before a second pass when every model was out of quota
PASSES = 2


class LLMUnavailable(RuntimeError):
    """No model could give a usable answer. The message lists what went wrong, never the key."""


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    value: T
    model: str
    tokens: int | None


class LLM(Protocol):
    def generate[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> LLMResult[T]: ...


def classify_error(error: Exception) -> str:
    """Sort an API error into: auth, missing, quota, busy, slow or other."""
    code = getattr(error, "code", None)
    text = f"{type(error).__name__} {error}"
    if code in (401, 403) or "API_KEY_INVALID" in text or "PERMISSION_DENIED" in text:
        return "auth"
    if code == 404 or "NOT_FOUND" in text:
        return "missing"
    if code == 429 or "RESOURCE_EXHAUSTED" in text:
        return "quota"
    if code == 503 or "UNAVAILABLE" in text:
        return "busy"
    if code == 504 or "DEADLINE" in text or "Timeout" in text or "timed out" in text:
        return "slow"
    return "other"


def _system_with_schema(system: str, schema: type[BaseModel]) -> str:
    return (
        f"{system}\n\nReply with a single JSON object and nothing else. It must match this "
        f"JSON Schema exactly:\n{json.dumps(schema.model_json_schema())}"
    )


class GeminiLLM:
    """Google Gemini through the google-genai library, with retries and model fallback."""

    def __init__(
        self,
        client: Any,
        models: list[str],
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not models:
            raise ValueError("at least one model name is needed (LLM_MODELS in .env)")
        self._client = client
        self._models = models
        self._sleep = sleep

    def generate[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> LLMResult[T]:
        problems: list[str] = []
        config = {
            "system_instruction": _system_with_schema(system, schema),
            "temperature": 0,
            "response_mime_type": "application/json",
        }
        for pass_number in range(PASSES):
            out_of_quota = False
            for model in self._models:
                outcome = self._try_model(model, prompt, config, schema, problems)
                if isinstance(outcome, LLMResult):
                    return outcome
                out_of_quota = out_of_quota or outcome == "quota"
            if not out_of_quota or pass_number == PASSES - 1:
                break
            self._sleep(QUOTA_WAIT)
        raise LLMUnavailable("no model answered: " + "; ".join(problems))

    def _try_model[T: BaseModel](
        self, model: str, prompt: str, config: dict, schema: type[T], problems: list[str]
    ) -> LLMResult[T] | str:
        busy_used = 0
        format_used = 0
        text_prompt = prompt
        while True:
            try:
                response = self._client.models.generate_content(
                    model=model, contents=text_prompt, config=config
                )
            except Exception as error:  # the library raises several kinds of error
                kind = classify_error(error)
                problems.append(f"{model}: {kind}")
                if kind == "auth":
                    raise LLMUnavailable("the API key was rejected (check LLM_API_KEY)") from None
                if kind == "busy" and busy_used < len(BUSY_WAITS):
                    self._sleep(BUSY_WAITS[busy_used])
                    busy_used += 1
                    continue
                return "quota" if kind == "quota" else "skip"
            try:
                value = schema.model_validate_json(response.text)
            except (ValidationError, ValueError, TypeError):
                problems.append(f"{model}: reply did not match the format")
                if format_used < FORMAT_RETRIES:
                    format_used += 1
                    text_prompt = (
                        f"{prompt}\n\nYour previous reply was not valid. Reply again with "
                        "valid JSON that matches the schema, and nothing else."
                    )
                    continue
                return "skip"
            usage = getattr(response, "usage_metadata", None)
            return LLMResult(value, model, getattr(usage, "total_token_count", None))


def build_llm(provider: str, api_key: str, models: str, timeout_ms: int = 45_000) -> GeminiLLM:
    """Create the language model client from the settings."""
    if provider != "gemini":
        raise ValueError(f"LLM_PROVIDER is {provider!r}; only 'gemini' is supported")
    if not api_key:
        raise ValueError("LLM_API_KEY is empty")
    names = [name.strip() for name in models.split(",") if name.strip()]
    if not names:
        raise ValueError("LLM_MODELS is empty; list one or more model names, comma separated")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))
    return GeminiLLM(client, names)

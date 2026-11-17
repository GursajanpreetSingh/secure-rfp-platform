import json

import pytest
from pydantic import BaseModel

from app.llm import client as llm


class Answer(BaseModel):
    answer: int
    reason: str


GOOD = json.dumps({"answer": 72, "reason": "3 x 24"})


class ApiError(Exception):
    def __init__(self, code: int, status: str) -> None:
        super().__init__(f"{code} {status}. {{'error': 'x'}}")
        self.code = code


class Reply:
    def __init__(self, text: str, tokens: int = 10) -> None:
        self.text = text
        self.usage_metadata = type("Usage", (), {"total_token_count": tokens})()


class FakeClient:
    """Plays back one scripted outcome per call: a Reply, or an exception to raise."""

    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.calls: list[dict] = []
        self.models = self

    def generate_content(self, model: str, contents: str, config: dict) -> Reply:
        self.calls.append({"model": model, "contents": contents, "config": config})
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make(script: list, models: list[str] | None = None) -> tuple[llm.GeminiLLM, FakeClient, list]:
    client = FakeClient(script)
    waits: list[float] = []
    return llm.GeminiLLM(client, models or ["m1", "m2"], sleep=waits.append), client, waits


def test_first_model_answers() -> None:
    model, client, waits = make([Reply(GOOD, tokens=33)])
    result = model.generate("be brief", "3 days in hours?", Answer)
    assert result.value == Answer(answer=72, reason="3 x 24")
    assert (result.model, result.tokens, waits) == ("m1", 33, [])
    assert len(client.calls) == 1


def test_schema_and_json_mode_are_sent() -> None:
    model, client, _ = make([Reply(GOOD)])
    model.generate("be brief", "question", Answer)
    config = client.calls[0]["config"]
    assert config["response_mime_type"] == "application/json"
    assert config["temperature"] == 0
    assert "be brief" in config["system_instruction"]
    assert '"answer"' in config["system_instruction"]
    assert client.calls[0]["contents"] == "question"


def test_busy_model_is_retried_with_waits_then_succeeds() -> None:
    busy = ApiError(503, "UNAVAILABLE")
    model, client, waits = make([busy, busy, Reply(GOOD)])
    assert model.generate("s", "p", Answer).model == "m1"
    assert waits == [2.0, 5.0]
    assert [c["model"] for c in client.calls] == ["m1", "m1", "m1"]


def test_model_that_stays_busy_is_skipped() -> None:
    busy = [ApiError(503, "UNAVAILABLE")] * 4
    model, client, waits = make([*busy, Reply(GOOD)])
    assert model.generate("s", "p", Answer).model == "m2"
    assert waits == list(llm.BUSY_WAITS)


@pytest.mark.parametrize(
    "error", [ApiError(404, "NOT_FOUND"), ApiError(504, "DEADLINE_EXCEEDED"), ValueError("boom")]
)
def test_missing_slow_or_broken_model_moves_on_at_once(error: Exception) -> None:
    model, client, waits = make([error, Reply(GOOD)])
    assert model.generate("s", "p", Answer).model == "m2"
    assert waits == []


def test_out_of_quota_moves_on_to_the_next_model() -> None:
    model, _, waits = make([ApiError(429, "RESOURCE_EXHAUSTED"), Reply(GOOD)])
    assert model.generate("s", "p", Answer).model == "m2"
    assert waits == []


def test_when_every_model_is_out_of_quota_it_waits_and_tries_again() -> None:
    quota = ApiError(429, "RESOURCE_EXHAUSTED")
    model, client, waits = make([quota, quota, Reply(GOOD)])
    assert model.generate("s", "p", Answer).model == "m1"
    assert waits == [llm.QUOTA_WAIT]
    assert len(client.calls) == 3


def test_rejected_key_stops_at_once_without_trying_other_models() -> None:
    model, client, _ = make([ApiError(403, "PERMISSION_DENIED"), Reply(GOOD)])
    with pytest.raises(llm.LLMUnavailable, match="API key was rejected"):
        model.generate("s", "p", Answer)
    assert len(client.calls) == 1


def test_bad_json_is_asked_for_again_once() -> None:
    model, client, _ = make([Reply("not json"), Reply(GOOD)])
    assert model.generate("s", "p", Answer).value.answer == 72
    assert "previous reply was not valid" in client.calls[1]["contents"]
    assert [c["model"] for c in client.calls] == ["m1", "m1"]


def test_reply_with_wrong_fields_counts_as_bad() -> None:
    model, _, _ = make([Reply('{"answer": "many"}'), Reply('{"wrong": 1}'), Reply(GOOD)])
    assert model.generate("s", "p", Answer).model == "m2"


def test_failure_lists_every_model_tried() -> None:
    errors = [ApiError(404, "NOT_FOUND"), ApiError(504, "DEADLINE_EXCEEDED")]
    model, _, _ = make(errors)
    with pytest.raises(llm.LLMUnavailable) as caught:
        model.generate("s", "p", Answer)
    message = str(caught.value)
    assert "m1: missing" in message and "m2: slow" in message


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (ApiError(401, "UNAUTHENTICATED"), "auth"),
        (ApiError(404, "NOT_FOUND"), "missing"),
        (ApiError(429, "RESOURCE_EXHAUSTED"), "quota"),
        (ApiError(503, "UNAVAILABLE"), "busy"),
        (ApiError(504, "DEADLINE_EXCEEDED"), "slow"),
        (TimeoutError("timed out"), "slow"),
        (RuntimeError("other"), "other"),
    ],
)
def test_error_classification(error: Exception, kind: str) -> None:
    assert llm.classify_error(error) == kind


def test_a_model_list_is_required() -> None:
    with pytest.raises(ValueError):
        llm.GeminiLLM(FakeClient([]), [])


@pytest.mark.parametrize(
    ("provider", "key", "models"),
    [("", "k", "m"), ("openai", "k", "m"), ("gemini", "", "m"), ("gemini", "k", " , ")],
)
def test_build_llm_rejects_incomplete_settings(provider: str, key: str, models: str) -> None:
    with pytest.raises(ValueError):
        llm.build_llm(provider, key, models)
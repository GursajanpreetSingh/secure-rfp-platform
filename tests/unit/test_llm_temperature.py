from unittest.mock import MagicMock

from pydantic import BaseModel

from app.llm.client import GeminiLLM
from app.qa.service import ANSWER_TEMPERATURE, for_answers


class Reply(BaseModel):
    ok: bool


def make_llm():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text='{"ok": true}')
    return GeminiLLM(client, ["model-a"], sleep=lambda _: None), client


def temperature_used(client):
    return client.models.generate_content.call_args.kwargs["config"]["temperature"]


def test_the_default_stays_at_zero_so_the_rfp_judge_is_repeatable():
    llm, client = make_llm()
    llm.generate("system", "prompt", Reply)
    assert temperature_used(client) == 0


def test_with_temperature_changes_only_the_copy():
    llm, client = make_llm()
    varied = llm.with_temperature(0.4)
    varied.generate("system", "prompt", Reply)
    assert temperature_used(client) == 0.4
    llm.generate("system", "prompt", Reply)
    assert temperature_used(client) == 0


def test_answers_use_a_varied_client_when_one_is_available():
    llm, client = make_llm()
    for_answers(llm).generate("system", "prompt", Reply)
    assert temperature_used(client) == ANSWER_TEMPERATURE


def test_a_client_without_the_option_is_used_as_it_is():
    plain = object()
    assert for_answers(plain) is plain

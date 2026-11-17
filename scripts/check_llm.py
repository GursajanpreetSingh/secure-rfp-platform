"""Check that the language model is set up: key found, model listed, one real call works.

Run it from the project folder with:  uv run python -m scripts.check_llm
The key is never printed. Google retires model names often, so if the first model is gone
the script tries the next one and tells you which name finally worked.
"""

import argparse
import json
import sys
import time

from app.core.config import get_settings

PREFERRED = ("gemini-3.8-flash", "gemini-3-flash", "gemini-2.5-flash")
SKIP_WORDS = ("image", "tts", "audio", "live", "embedding", "robotics", "computer", "omni")
MAX_ATTEMPTS = 6
RETRY_WAITS = (2, 5, 10)  # seconds to wait when the model is busy
REQUEST_TIMEOUT_MS = 45_000  # give up on one request after 45 seconds
PROMPT = (
    'Reply with JSON only: {"answer": <number>, "reason": <short text>}. '
    "Question: how many hours are in 3 days?"
)


def _clean(message: str, key: str) -> str:
    return message.replace(key, "***") if key else message


def _candidates(names: list[str], chosen: str | None) -> list[str]:
    """Models to try, best bet first: the usual names, then stable full models, then
    preview models, then the small 'lite' models (which are fast and often free)."""
    if chosen:
        return [chosen]
    usable = sorted(
        (n for n in names if "flash" in n and not any(w in n for w in SKIP_WORDS)), reverse=True
    )
    first = [m for m in PREFERRED if m in usable]
    rest = [n for n in usable if n not in first]
    rest.sort(key=lambda n: ("lite" in n, "preview" in n or "exp" in n))  # stable sort
    return (first + rest)[:MAX_ATTEMPTS]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="model name to use instead of the automatic choice")
    args = parser.parse_args()

    settings = get_settings()
    key = settings.llm_api_key.get_secret_value()
    print("1. Settings")
    if settings.llm_provider != "gemini":
        print(f"  FAIL  LLM_PROVIDER is {settings.llm_provider!r}, expected 'gemini' (see .env)")
        return 1
    if not key:
        print("  FAIL  LLM_API_KEY is empty (see .env)")
        return 1
    print(f"  ok    provider gemini, key found ({len(key)} characters)")

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  FAIL  the library is missing. Run: uv add google-genai")
        return 1

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    print("2. Models", flush=True)
    try:
        names = [
            model.name.removeprefix("models/")
            for model in client.models.list()
            if "generateContent" in (model.supported_actions or [])
        ]
    except Exception as error:  # the library raises several kinds of error
        print(f"  FAIL  could not list models: {_clean(str(error), key)[:300]}")
        return 1
    print(f"  ok    {len(names)} models can generate text")
    candidates = _candidates(names, args.model)
    if not candidates:
        print("  FAIL  no flash model found. Models you can use:")
        print("        " + ", ".join(names[:12]))
        print("        Run again with: --model <one of these>")
        return 1

    print("  will try, in this order: " + ", ".join(candidates))
    print("3. One real call", flush=True)
    for model in candidates:
        for attempt, wait in enumerate((*RETRY_WAITS, None)):
            print(f"  ...   asking {model} (attempt {attempt + 1})", flush=True)
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=PROMPT,
                    config=types.GenerateContentConfig(
                        temperature=0, response_mime_type="application/json"
                    ),
                )
                data = json.loads(response.text)
            except Exception as error:
                text = _clean(str(error), key)
                if "404" in text or "NOT_FOUND" in text:
                    print(f"  skip  {model}: not available to this key")
                    break
                busy = "503" in text or "UNAVAILABLE" in text
                slow = any(w in text for w in ("504", "DEADLINE", "timed out", "Timeout"))
                if "429" in text or "RESOURCE_EXHAUSTED" in text:
                    print(f"  skip  {model}: no free quota left for this model")
                    break
                if slow:
                    print(f"  skip  {model}: too slow to answer, trying the next model")
                    break
                if busy and wait is not None:
                    print(f"  wait  {model} is busy, trying again in {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                if busy:
                    print(f"  skip  {model}: still busy after {attempt} retries")
                    break
                print(f"  FAIL  {model}: {type(error).__name__}: {text[:300]}")
                return 1
            tokens = getattr(response.usage_metadata, "total_token_count", "unknown")
            print(f"  ok    {model} replied: {data}")
            print(f"  ok    tokens used: {tokens}")
            if data.get("answer") != 72:
                print("  warn  it replied, but not with 72")
            print(f"All checks passed. Use this model name: {model}")
            return 0
    print("  FAIL  none of the models worked. Tried: " + ", ".join(candidates))
    return 1


if __name__ == "__main__":
    sys.exit(main())

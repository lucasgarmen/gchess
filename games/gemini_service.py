import hashlib
import json
import logging
import os
from urllib import error, parse, request

from django.core.cache import cache

logger = logging.getLogger(__name__)


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


def gemini_enabled():
    return bool(os.environ.get("GEMINI_API_KEY")) and env_bool("GEMINI_ENABLED", True)


def gemini_model():
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")


def gemini_timeout():
    return float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "8"))


def gemini_max_output_tokens():
    return int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "350"))


def gemini_cache_seconds():
    return int(os.environ.get("GEMINI_CACHE_SECONDS", "120"))


def gemini_temperature():
    return float(os.environ.get("GEMINI_TEMPERATURE", "0.2"))


def cache_key_for_prompt(namespace, model, prompt):
    digest = hashlib.sha256(f"{model}\n{prompt}".encode("utf-8")).hexdigest()
    return f"gemini:{namespace}:{digest}"


def extract_text(response_payload):
    candidates = response_payload.get("candidates") or []

    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()

        if text:
            return text

    return ""


def generate_gemini_explanation(prompt, namespace="trainer_chat"):
    if not gemini_enabled():
        return None

    model = gemini_model()
    cache_key = cache_key_for_prompt(namespace, model, prompt)
    cached = cache.get(cache_key)

    if cached:
        return cached

    api_key = os.environ["GEMINI_API_KEY"]
    encoded_model = parse.quote(model, safe="")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": gemini_temperature(),
            "topP": 0.8,
            "maxOutputTokens": gemini_max_output_tokens(),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    gemini_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(gemini_request, timeout=gemini_timeout()) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:800]
        except OSError:
            body = ""
        logger.warning("Gemini HTTP error %s: %s %s", exc.code, exc.reason, body)
        return None
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Gemini request failed: %s", exc)
        return None

    text = extract_text(response_payload)

    if not text:
        logger.warning("Gemini returned an empty answer.")
        return None

    text = text.strip()[:1600]
    cache.set(cache_key, text, gemini_cache_seconds())
    return text

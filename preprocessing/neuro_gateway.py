"""Client for ai.rt.ru neuro-gateway (Леопольд / Qwen), based on api_нейрошлюз.ipynb."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://ai.rt.ru/api/1.0"
TIMEOUT = 300
DEFAULT_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct-FP8"
DEFAULT_SYSTEM_PROMPT = (
    "Ты — ассистент по нормализации наименований строительных ресурсов (МТР). "
    "Отвечай строго валидным JSON без markdown."
)

# Project root: .../Preprocessing
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_LOADED = False


def load_env_local(path: Path | None = None) -> None:
    """Load KEY=VALUE from .env.local into os.environ (does not override existing)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = path or (_PROJECT_ROOT / ".env.local")
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
    _ENV_LOADED = True


def get_token() -> str:
    load_env_local()
    token = (
        os.environ.get("NEIROSHLYUZ_TOKEN")
        or os.environ.get("AI_RT_TOKEN")
        or ""
    ).strip()
    if not token:
        raise RuntimeError(
            "Не задан токен нейрошлюза. Добавьте в .env.local строку "
            "NEIROSHLYUZ_TOKEN=... или задайте переменную окружения "
            "(см. .env.local.example)."
        )
    return token


def headers(token: str | None = None, json_content: bool = True) -> dict[str, str]:
    h = {"Authorization": f"Bearer {token or get_token()}"}
    if json_content:
        h["Content-Type"] = "application/json"
    else:
        h["accept"] = "*/*"
    return h


def extract_text(js: Any) -> str:
    """Достаёт текст ответа из типичных форматов нейрошлюза."""
    if isinstance(js, str):
        return js
    if isinstance(js, dict) and js.get("error"):
        return f"Error {js.get('status_code')}: {js.get('text')}"
    if isinstance(js, dict):
        message = js.get("message")
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"]).strip()
        choices = js.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message", {})
            return str(msg.get("content", "")).strip()
        return str(js)
    if isinstance(js, list) and js:
        first = js[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and "content" in message:
                return str(message["content"]).strip()
            if isinstance(message, str):
                return message.strip()
        return str(first)
    return str(js)


def post_json(
    url: str,
    payload: dict[str, Any],
    token: str | None = None,
    timeout: int = TIMEOUT,
) -> Any:
    r = requests.post(
        url,
        headers=headers(token),
        json=payload,
        verify=False,
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Error {r.status_code}: {r.text}")
    return r.json()


def llama_chat(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_new_tokens: int = 1024,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    token: str | None = None,
) -> str:
    """
    POST /lleopold/chatMulti — формат contents (как для Qwen в ноутбуке).
    Модель по умолчанию: Qwen/Qwen3-Next-80B-A3B-Instruct-FP8.
    """
    chat = {
        "model": model,
        "system_prompt": system_prompt,
        "max_new_tokens": max_new_tokens,
        "no_repeat_ngram_size": 15,
        "repetition_penalty": 1.1,
        "temperature": temperature,
        "top_k": 40,
        "top_p": 0.9,
        "contents": [{"type": "text", "text": prompt}],
    }
    payload = {"chat": chat}
    response = post_json(f"{BASE}/lleopold/chatMulti", payload, token=token)
    return extract_text(response)

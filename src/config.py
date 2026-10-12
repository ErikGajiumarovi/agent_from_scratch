# -*- coding: utf-8 -*-
"""Конфигурация агента: константы, окружение, модель."""

import os
import sys

from langchain_openai import ChatOpenAI

from src.chatgpt_model import ChatGPTResponsesModel

PROVIDER = os.getenv("AGENT_PROVIDER", "openrouter").strip().lower()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1"
# Проверенные бесплатные модели OpenRouter с поддержкой tools и русского.
OPENROUTER_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "dots-studio/dots-3-note-preview:free",
]
CHATGPT_MODEL = os.getenv("CHATGPT_MODEL", "gpt-6-luna")
# Проверенные модели ChatGPT-подписки (остальные имена Codex-бэкенд
# этого аккаунта отвергает — но можно вписать любое вручную).
CHATGPT_MODELS = ["gpt-6-luna", "gpt-5.5"]
MODEL = CHATGPT_MODEL if PROVIDER == "chatgpt" else OPENROUTER_MODEL
HISTORY_FILE = "history.json"
DB_PATH = os.getenv("AGENT_DB_PATH", "data/agent.db")
THREAD_ID = "console"
RECURSION_LIMIT = 12
WEB_HOST = os.getenv("AGENT_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("AGENT_PORT", "8000"))

OPENROUTER_KEY_URL = "https://openrouter.ai/settings/keys"


def get_api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def require_api_key() -> str:
    """Проверить авторизацию активного провайдера, выйти с подсказкой если нет."""
    if PROVIDER == "chatgpt":
        from src import chatgpt_auth
        try:
            chatgpt_auth.load_auth()
        except chatgpt_auth.ChatGPTAuthError as exc:
            print(f"[Ошибка] {exc}")
            sys.exit(1)
        return "chatgpt-subscription"
    api_key = get_api_key()
    if not api_key:
        print(f"[Ошибка] Задайте OPENROUTER_API_KEY. Ключ: {OPENROUTER_KEY_URL}")
        sys.exit(1)
    return api_key


def available_models() -> list:
    """Курированный список моделей активного провайдера."""
    return list(CHATGPT_MODELS if PROVIDER == "chatgpt" else OPENROUTER_MODELS)


def create_model():
    """Создать модель активного провайдера (openrouter | chatgpt)."""
    if PROVIDER == "chatgpt":
        require_api_key()
        return ChatGPTResponsesModel(model=MODEL)
    return ChatOpenAI(api_key=require_api_key(), base_url=OPENROUTER_URL,
                      model=MODEL, temperature=0)

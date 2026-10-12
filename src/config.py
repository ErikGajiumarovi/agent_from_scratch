# -*- coding: utf-8 -*-
"""Конфигурация агента: константы, окружение, модель."""

import os
import sys

from langchain_openai import ChatOpenAI

MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
BASE_URL = "https://openrouter.ai/api/v1"
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
    """Проверить наличие ключа, выйти с подсказкой если его нет."""
    api_key = get_api_key()
    if not api_key:
        print(f"[Ошибка] Задайте OPENROUTER_API_KEY. Ключ: {OPENROUTER_KEY_URL}")
        sys.exit(1)
    return api_key


def create_model() -> ChatOpenAI:
    """Создать модель через OpenRouter (OpenAI-совместимый API)."""
    return ChatOpenAI(api_key=require_api_key(), base_url=BASE_URL,
                      model=MODEL, temperature=0)

# -*- coding: utf-8 -*-
"""Конфигурация агента: константы, окружение, модель."""

import os
import sys

from langchain_ollama import ChatOllama

MODEL = "gemma4:31b"
BASE_URL = "https://ollama.com"
HISTORY_FILE = "history.json"
THREAD_ID = "console"
RECURSION_LIMIT = 12

OLLAMA_KEY_URL = "https://ollama.com/settings/keys"


def get_api_key() -> str:
    return os.getenv("OLLAMA_API_KEY", "")


def require_api_key() -> str:
    """Проверить наличие ключа, выйти с подсказкой если его нет."""
    api_key = get_api_key()
    if not api_key:
        print(f"[Ошибка] Задайте OLLAMA_API_KEY. Ключ: {OLLAMA_KEY_URL}")
        sys.exit(1)
    return api_key


def create_model() -> ChatOllama:
    """Создать ChatOllama. Ollama Cloud читает OLLAMA_API_KEY из окружения."""
    require_api_key()
    return ChatOllama(model=MODEL, base_url=BASE_URL, temperature=0)

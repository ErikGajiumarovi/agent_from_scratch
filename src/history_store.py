# -*- coding: utf-8 -*-
"""Сохранение и показ истории диалога."""

import json

from src import config


def save_history(messages: list) -> None:
    try:
        with open(config.HISTORY_FILE, "w", encoding="utf-8") as file:
            json.dump([message.model_dump() for message in messages], file,
                      ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        print(f"[Предупреждение] Не смог сохранить историю: {exc}")


def dump_messages(messages: list) -> list:
    """Сериализовать сообщения в JSON-совместимые словари (для API/веба)."""
    dumped = []
    for message in messages:
        try:
            data = message.model_dump()
        except Exception:
            data = {"type": getattr(message, "type", "?"),
                    "content": str(getattr(message, "content", ""))}
        dumped.append(json.loads(json.dumps(data, ensure_ascii=False, default=str)))
    return dumped


def print_history(messages: list) -> None:
    print(f"\n[История: {len(messages)} сообщений]")
    for index, message in enumerate(messages):
        role = {"ai": "assistant", "human": "user"}.get(message.type, message.type)
        calls = getattr(message, "tool_calls", []) or []
        if calls:
            for call in calls:
                print(f"{index:02d} [{role}] tool_call: {call['name']}({call['args']})")
        content = message.content
        if content:
            print(f"{index:02d} [{role}] {content}")

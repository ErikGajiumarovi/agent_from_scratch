# -*- coding: utf-8 -*-
"""Субагент и инструмент ask_subagent для изолированных подзадач."""

import datetime
import threading

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from src import config
from src.graph import build_agent, events_from_chunk
from src.tools import BASE_TOOLS

SUBAGENT_PROMPT = (
    "Ты вспомогательный агент. Реши только порученную задачу. "
    "Используй доступные инструменты при необходимости; отвечай кратко."
)

_subagent = None


def get_subagent():
    """Лениво создать субагента (чтобы импорт не требовал API-ключ)."""
    global _subagent
    if _subagent is None:
        model = config.create_model()
        _subagent = build_agent(model, BASE_TOOLS, SUBAGENT_PROMPT)
    return _subagent


def reset_subagent() -> None:
    """Сбросить субагента, чтобы следующий вызов собрал его заново."""
    global _subagent
    _subagent = None


# Журнал субчатов: каждый запуск ask_subagent пишется сюда с задачей,
# своими событиями и итогом. Читает веб-панель «Субчаты».
_subchats: list = []
_subchats_lock = threading.Lock()
_subchat_seq = 0


def list_subchats() -> list:
    """Краткие карточки всех субчатов (без полных событий)."""
    with _subchats_lock:
        return [{k: entry[k] for k in ("id", "task", "model", "status",
                                      "started_at", "result")
                 } | {"events": len(entry["events"])} for entry in _subchats]


def get_subchat(subchat_id: int) -> dict | None:
    """Полная карточка субчата с событиями."""
    with _subchats_lock:
        for entry in _subchats:
            if entry["id"] == subchat_id:
                return dict(entry, events=list(entry["events"]))
    return None


def clear_subchats() -> None:
    """Очистить журнал (вызывается при /reset нового чата)."""
    global _subchat_seq
    with _subchats_lock:
        _subchats.clear()
        _subchat_seq = 0


@tool
def ask_subagent(task: str) -> str:
    """Передать отдельную задачу вспомогательному агенту и получить результат."""
    global _subchat_seq
    with _subchats_lock:
        _subchat_seq += 1
        entry = {"id": _subchat_seq, "task": task, "model": config.MODEL,
                 "status": "running", "events": [], "result": None,
                 "started_at": datetime.datetime.now().isoformat(timespec="seconds")}
        _subchats.append(entry)
    try:
        answer = None
        for chunk in get_subagent().stream(
                {"messages": [HumanMessage(content=task)]},
                {"recursion_limit": config.RECURSION_LIMIT},
                stream_mode="updates"):
            for event in events_from_chunk(chunk):
                entry["events"].append(event)
                if event["type"] == "answer":
                    answer = event["text"]
        entry["result"] = answer if answer is not None else "[пустой результат]"
        entry["status"] = "done"
        return str(entry["result"])
    except Exception as exc:
        entry["status"] = "error"
        entry["result"] = str(exc)[:300]
        raise

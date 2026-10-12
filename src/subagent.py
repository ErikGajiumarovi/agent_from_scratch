# -*- coding: utf-8 -*-
"""Субагент и инструмент ask_subagent для изолированных подзадач."""

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from src import config
from src.graph import build_agent
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


@tool
def ask_subagent(task: str) -> str:
    """Передать отдельную задачу вспомогательному агенту и получить результат."""
    result = get_subagent().invoke(
        {"messages": [HumanMessage(content=task)]},
        {"recursion_limit": config.RECURSION_LIMIT},
    )
    return str(result["messages"][-1].content)

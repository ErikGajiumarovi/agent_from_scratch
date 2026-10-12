# -*- coding: utf-8 -*-
"""Главный агент: сборка графа, конфиг треда, выполнение ходов диалога."""

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from src import config
from src.graph import build_agent
from src.history_store import save_history
from src.subagent import ask_subagent
from src.tools import BASE_TOOLS

SYSTEM_PROMPT = (
    "Ты — помощник. Отвечай по-русски, коротко и по делу. "
    "Используй доступные инструменты для вычислений, конвертаций, дат, текста и JSON. "
    "Независимые инструменты вызывай одновременно в одном ходе, если это уместно. "
    "Отдельную сложную задачу можно передать через ask_subagent. "
    "Не выдумывай результаты инструментов."
)

checkpointer = InMemorySaver()
CONFIG = {
    "configurable": {"thread_id": config.THREAD_ID},
    "recursion_limit": config.RECURSION_LIMIT,
}

_agent = None


def get_agent():
    """Лениво создать главного агента (чтобы импорт не требовал API-ключ)."""
    global _agent
    if _agent is None:
        model = config.create_model()
        _agent = build_agent(
            model,
            [*BASE_TOOLS, ask_subagent],
            SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )
    return _agent


def current_messages() -> list:
    snapshot = get_agent().get_state(CONFIG)
    return snapshot.values.get("messages", []) if snapshot.values else []


def reset_thread() -> None:
    checkpointer.delete_thread(config.THREAD_ID)


def run_turn(user_text: str) -> str:
    messages = current_messages()
    new_messages = [HumanMessage(content=user_text)]
    if not messages:
        new_messages.insert(0, SystemMessage(content=SYSTEM_PROMPT))

    result = get_agent().invoke({"messages": new_messages}, CONFIG)
    save_history(result["messages"])
    answer = result["messages"][-1].content
    return str(answer)

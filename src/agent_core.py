# -*- coding: utf-8 -*-
"""Главный агент: сборка графа, конфиг треда, выполнение ходов диалога."""

from langchain_core.messages import HumanMessage, SystemMessage

from src import config, db
from src.graph import build_agent, events_from_chunk
from src.history_store import save_history
from src.subagent import ask_subagent, clear_subchats, reset_subagent
from src.tools import BASE_TOOLS

SYSTEM_PROMPT = (
    "Ты — помощник. Отвечай по-русски, коротко и по делу. "
    "Используй доступные инструменты для вычислений, конвертаций, дат, текста и JSON. "
    "Независимые инструменты вызывай одновременно в одном ходе, если это уместно. "
    "Отдельную сложную задачу можно передать через ask_subagent. "
    "Не выдумывай результаты инструментов."
)

checkpointer = None
CONFIG = {
    "configurable": {"thread_id": config.THREAD_ID},
    "recursion_limit": config.RECURSION_LIMIT,
}


def get_checkpointer():
    """Лениво вернуть SQLite-checkpointer (создаёт БД при первом вызове)."""
    global checkpointer
    if checkpointer is None:
        checkpointer = db.get_checkpointer()
    return checkpointer

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
            checkpointer=get_checkpointer(),
        )
    return _agent


def current_messages() -> list:
    snapshot = get_agent().get_state(CONFIG)
    return snapshot.values.get("messages", []) if snapshot.values else []


def reset_thread() -> None:
    get_checkpointer().delete_thread(config.THREAD_ID)
    clear_subchats()


def set_model(name: str) -> str:
    """Переключить модель на лету: пересобрать агента и субагента."""
    name = (name or "").strip()
    if not name:
        raise ValueError("пустое имя модели")
    config.MODEL = name
    global _agent
    _agent = None
    reset_subagent()
    get_agent()  # собрать сразу, чтобы ошибка вылезла здесь, а не в ходе
    return config.MODEL


def stream_turn(user_text: str):
    """Выполнить ход диалога, по ходу дела отдавая события (генератор).

    Через graph.stream наружу идут tool_call/tool_result/answer
    по мере их появления, в конце — done {message_count}.
    """
    messages = current_messages()
    new_messages = [HumanMessage(content=user_text)]
    if not messages:
        new_messages.insert(0, SystemMessage(content=SYSTEM_PROMPT))

    yield {"type": "status", "text": "запрос отправлен модели"}
    answer = None
    for chunk in get_agent().stream({"messages": new_messages}, CONFIG,
                                    stream_mode="updates"):
        for event in events_from_chunk(chunk):
            if event["type"] == "answer":
                answer = event["text"]
            yield event
    save_history(current_messages())
    yield {"type": "done", "message_count": len(current_messages()),
           "answer": answer}

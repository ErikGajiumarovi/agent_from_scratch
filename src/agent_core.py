# -*- coding: utf-8 -*-
"""Главный агент: сборка графа, конфиг треда, выполнение ходов диалога."""

from langchain_core.messages import HumanMessage, SystemMessage

from src import config, db
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


def run_turn(user_text: str) -> str:
    messages = current_messages()
    new_messages = [HumanMessage(content=user_text)]
    if not messages:
        new_messages.insert(0, SystemMessage(content=SYSTEM_PROMPT))

    result = get_agent().invoke({"messages": new_messages}, CONFIG)
    save_history(result["messages"])
    answer = result["messages"][-1].content
    return str(answer)


def events_from_chunk(chunk: dict) -> list:
    """Превратить обновление графа (stream_mode='updates') в плоские события.

    События: tool_call {name, args, id}, tool_result {name, content, tool_call_id},
    answer {text}. Используется веб-интерфейсом для панели «под капотом».
    """
    events = []
    for payload in chunk.values():
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        for message in messages:
            kind = getattr(message, "type", "")
            if kind == "ai":
                for call in getattr(message, "tool_calls", []) or []:
                    events.append({"type": "tool_call", "name": call.get("name", "?"),
                                   "args": call.get("args", {}), "id": call.get("id", "")})
                if getattr(message, "content", ""):
                    events.append({"type": "answer", "text": str(message.content)})
            elif kind == "tool":
                events.append({"type": "tool_result", "name": getattr(message, "name", ""),
                               "content": str(getattr(message, "content", "")),
                               "tool_call_id": getattr(message, "tool_call_id", "")})
    return events


def stream_turn(user_text: str):
    """Выполнить ход диалога, по ходу дела отдавая события (генератор).

    Тот же run_turn, но через graph.stream: наружу идут tool_call/tool_result/
    answer по мере их появления, в конце — done {message_count}.
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

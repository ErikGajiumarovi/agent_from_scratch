# -*- coding: utf-8 -*-
"""Минимальный агент на LangGraph и Ollama Cloud."""

import ast
import datetime
import json
import os
import sys

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

MODEL = "gemma4:31b"
HISTORY_FILE = "history.json"
THREAD_ID = "console"
API_KEY = os.getenv("OLLAMA_API_KEY", "")

if not API_KEY:
    print("[Ошибка] Задайте OLLAMA_API_KEY. Ключ: https://ollama.com/settings/keys")
    sys.exit(1)

# Ollama Cloud читает OLLAMA_API_KEY из окружения.
model = ChatOllama(model=MODEL, base_url="https://ollama.com", temperature=0)


@tool
def calculator(expression: str) -> str:
    """Безопасно вычислить простое математическое выражение."""
    try:
        tree = ast.parse(expression, mode="eval")
        allowed = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
            ast.USub, ast.UAdd, ast.FloorDiv, ast.Load,
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                return f"Ошибка: запрещённая операция {type(node).__name__}"
        return str(eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}))
    except Exception as exc:
        return f"Ошибка вычисления: {exc}"


@tool
def get_time() -> str:
    """Узнать текущие дату и время."""
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


@tool
def convert_temperature(value: float, from_unit: str, to_unit: str) -> str:
    """Перевести температуру между Celsius, Fahrenheit и Kelvin."""
    units = {"c": "c", "celsius": "c", "f": "f", "fahrenheit": "f",
             "k": "k", "kelvin": "k"}
    source = units.get(from_unit.strip().lower())
    target = units.get(to_unit.strip().lower())
    if source is None or target is None:
        return "Ошибка: единицы температуры — C, F или K."
    celsius = value if source == "c" else (value - 32) * 5 / 9 if source == "f" else value - 273.15
    if celsius < -273.15:
        return "Ошибка: температура ниже абсолютного нуля."
    result = celsius if target == "c" else celsius * 9 / 5 + 32 if target == "f" else celsius + 273.15
    return f"{value:g} {source.upper()} = {result:.2f} {target.upper()}"


@tool
def convert_distance(value: float, from_unit: str, to_unit: str) -> str:
    """Перевести расстояние между m, km, cm, mi и ft."""
    meters = {"m": 1, "meter": 1, "meters": 1,
              "km": 1000, "kilometer": 1000, "kilometers": 1000,
              "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
              "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
              "ft": 0.3048, "foot": 0.3048, "feet": 0.3048}
    source = from_unit.strip().lower()
    target = to_unit.strip().lower()
    if source not in meters or target not in meters:
        return "Ошибка: единицы расстояния — m, km, cm, mi или ft."
    return f"{value:g} {source} = {value * meters[source] / meters[target]:.4g} {target}"


@tool
def date_info(date: str) -> str:
    """Показать день недели и номер дня года для даты YYYY-MM-DD."""
    try:
        parsed = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        weekdays = ("понедельник", "вторник", "среда", "четверг",
                    "пятница", "суббота", "воскресенье")
        return f"{date} — {weekdays[parsed.weekday()]}, день года №{parsed.timetuple().tm_yday}."
    except ValueError:
        return "Ошибка: укажите дату в формате YYYY-MM-DD."


@tool
def count_words(text: str) -> str:
    """Посчитать слова, символы и символы без пробелов в тексте."""
    return (f"Слов: {len(text.split())}; символов: {len(text)}; "
            f"без пробелов: {len(''.join(text.split()))}.")


@tool
def format_json(json_text: str) -> str:
    """Проверить JSON и отформатировать его с отступами."""
    try:
        return json.dumps(json.loads(json_text), ensure_ascii=False, indent=2)
    except json.JSONDecodeError as exc:
        return f"Некорректный JSON: {exc.msg} (строка {exc.lineno}, столбец {exc.colno})."


BASE_TOOLS = [calculator, get_time, convert_temperature, convert_distance,
              date_info, count_words, format_json]


def build_agent(tools: list, system_prompt: str, checkpointer=None):
    """Создать простой цикл модель → инструменты → модель."""
    model_with_tools = model.bind_tools(tools)

    def call_model(state: MessagesState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt), *messages]
        return {"messages": [model_with_tools.invoke(messages)]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    builder.set_entry_point("agent")
    return builder.compile(checkpointer=checkpointer)


SUBAGENT_PROMPT = (
    "Ты вспомогательный агент. Реши только порученную задачу. "
    "Используй доступные инструменты при необходимости; отвечай кратко."
)
subagent = build_agent(BASE_TOOLS, SUBAGENT_PROMPT)


@tool
def ask_subagent(task: str) -> str:
    """Передать отдельную задачу вспомогательному агенту и получить результат."""
    result = subagent.invoke(
        {"messages": [HumanMessage(content=task)]}, {"recursion_limit": 12}
    )
    return str(result["messages"][-1].content)


SYSTEM_PROMPT = (
    "Ты — помощник. Отвечай по-русски, коротко и по делу. "
    "Используй доступные инструменты для вычислений, конвертаций, дат, текста и JSON. "
    "Независимые инструменты вызывай одновременно в одном ходе, если это уместно. "
    "Отдельную сложную задачу можно передать через ask_subagent. "
    "Не выдумывай результаты инструментов."
)

checkpointer = InMemorySaver()
agent = build_agent(
    [*BASE_TOOLS, ask_subagent],
    SYSTEM_PROMPT,
    checkpointer=checkpointer,
)
CONFIG = {"configurable": {"thread_id": THREAD_ID}, "recursion_limit": 12}


def current_messages() -> list:
    snapshot = agent.get_state(CONFIG)
    return snapshot.values.get("messages", []) if snapshot.values else []


def print_history() -> None:
    messages = current_messages()
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


def save_history(messages: list) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as file:
            json.dump([message.model_dump() for message in messages], file,
                      ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        print(f"[Предупреждение] Не смог сохранить историю: {exc}")


def run_turn(user_text: str) -> str:
    messages = current_messages()
    new_messages = [HumanMessage(content=user_text)]
    if not messages:
        new_messages.insert(0, SystemMessage(content=SYSTEM_PROMPT))

    result = agent.invoke({"messages": new_messages}, CONFIG)
    save_history(result["messages"])
    answer = result["messages"][-1].content
    return str(answer)


if __name__ == "__main__":
    print(f"LangGraph + Ollama Cloud ({MODEL})")
    print("Инструменты: calculator, get_time, convert_temperature, convert_distance,")
    print("            date_info, count_words, format_json, ask_subagent")
    print("Команды: /history, /reset; пустая строка — выход")

    while True:
        try:
            question = input("\nВы: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nПока!")
            break
        if not question:
            print("Пока!")
            break
        if question == "/history":
            print_history()
            continue
        if question == "/reset":
            checkpointer.delete_thread(THREAD_ID)
            print("[История очищена]")
            continue
        try:
            print(f"\nАгент: {run_turn(question)}")
        except Exception as exc:
            print(f"\n[Ошибка] {exc}")

# -*- coding: utf-8 -*-
"""
Примитивный ИИ-агент с нуля на Python + Ollama Cloud (gemma4:31b).
Для русскоязычной аудитории: как создаются агенты за 5 минут.

Что такое агент в этом примере?
  1. МОЗГ (LLM)       — модель gemma4:31b в Ollama Cloud, думает и решает.
  2. ИНСТРУМЕНТЫ      — обычные Python-функции + JSON-описание для модели.
  3. ИСТОРИЯ          — список messages: system, user, assistant, tool.
                        Хранится ВСЁ время работы и переживает вопросы.
  4. ЦИКЛ ReAct       — Думаю -> tool_calls -> Выполняю -> tool -> Повторяю.
  5. СИСТЕМНЫЙ ПРОМТ  — короткая инструкция, без JSON-костылей.

Запуск:
  pip install -r requirements.txt
  export OLLAMA_API_KEY="ваш_ключ"   # либо впишите ключ в переменную ниже
  python agent.py
  # внутри чата: /history — показать историю, /reset — очистить, пустая строка — выход
"""

import ast
import datetime
import json
import os
import sys

import requests

# ---------------------------------------------------------------------------
# 1. НАСТРОЙКИ ПРОВАЙДЕРА
# ---------------------------------------------------------------------------
API_URL = "https://ollama.com/api/chat"
MODEL = "gemma4:31b"
HISTORY_FILE = "history.json"

API_KEY = os.getenv("OLLAMA_API_KEY", "")

if not API_KEY:
    print("[Ошибка] Задайте OLLAMA_API_KEY. Пример:")
    print('  export OLLAMA_API_KEY="ваш_ключ_с_ollama.com/settings/keys"')
    print("  Ключ: https://ollama.com/settings/keys")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 2. ИНСТРУМЕНТЫ — Python-функции + описание для модели
# ---------------------------------------------------------------------------
def tool_calculator(expression: str) -> str:
    """Безопасно считает математическое выражение. Пример: '23*48 + 11'."""
    try:
        tree = ast.parse(expression, mode="eval")
        allowed = (
            ast.Expression, ast.BinOp, ast.UnaryOp,
            ast.Num, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div,
            ast.Mod, ast.Pow, ast.USub, ast.UAdd,
            ast.FloorDiv, ast.Load,
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                return f"Ошибка: запрещённая операция {type(node).__name__}"
        result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Ошибка вычисления: {e}"


def tool_get_time() -> str:
    """Возвращает текущие дату и время."""
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


# Реальные функции, которые выполняет Python
TOOLS_IMPL = {
    "calculator": tool_calculator,
    "get_time": tool_get_time,
}

# Описание инструментов для модели (формат Ollama / OpenAI function calling).
# Именно это уходит в API в поле "tools" — так модель узнаёт, что ей можно вызывать.
TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Посчитать математическое выражение",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Например: '137*46+11'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Узнать текущие дату и время. Без аргументов.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    """Вызывает Python-функцию по имени и возвращает строку-результат."""
    if name not in TOOLS_IMPL:
        return f"Ошибка: нет инструмента '{name}'"
    try:
        if name == "calculator":
            return TOOLS_IMPL[name](args.get("expression", ""))
        if name == "get_time":
            return TOOLS_IMPL[name]()
        return TOOLS_IMPL[name](**args)
    except Exception as e:
        return f"Ошибка инструмента {name}: {e}"


# ---------------------------------------------------------------------------
# 3. ИСТОРИЯ ПЕРЕПИСКИ — сердце агента
# ---------------------------------------------------------------------------
# Формат одного сообщения (как в Ollama / OpenAI API):
#   {"role": "system",    "content": "..."}          — инструкция (1 раз в начале)
#   {"role": "user",      "content": "..."}          — вопрос человека
#   {"role": "assistant", "content": "...",
#    "tool_calls": [{"id": "...", "function": {"name": "...", "arguments": {...}}}]}
#     — ответ модели; если решила вызвать инструмент, content пустой, а вызов в tool_calls
#   {"role": "tool",      "content": "..."}          — результат инструмента
#
# Вся история копится в одном списке и каждый раз целиком уходит в API.
# Поэтому модель "помнит" и прошлые вопросы, и прошлые вызовы инструментов.

SYSTEM_PROMPT = (
    "Ты — примитивный ИИ-агент-помощник. Отвечай по-русски, коротко и по делу. "
    "Если нужна точная математика — вызови calculator. "
    "Если спрашивают про текущее время/дату — вызови get_time. "
    "Не выдумывай результаты инструментов, дождись их ответа."
)

# Стартуем историю с системного сообщения
history: list = [{"role": "system", "content": SYSTEM_PROMPT}]


def print_history() -> None:
    """Показывает всю историю: сообщения и tool calls. Для обучения."""
    print(f"\n[История: {len(history)} сообщений]")
    print("-" * 60)
    for i, msg in enumerate(history):
        role = msg.get("role", "?")
        content = (msg.get("content") or "").strip()
        # Обрезаем длинные тексты, чтобы не спамить
        short = content[:300] + ("..." if len(content) > 300 else "")
        if role == "system":
            print(f"{i:02d} [system]    {short}")
        elif role == "user":
            print(f"{i:02d} [user]      {short}")
        elif role == "assistant":
            calls = msg.get("tool_calls") or []
            if calls:
                for c in calls:
                    fn = c.get("function", {})
                    print(f"{i:02d} [assistant] tool_call: {fn.get('name')}({fn.get('arguments')})")
                if short:
                    print(f"     content: {short}")
            else:
                print(f"{i:02d} [assistant] {short}")
        elif role == "tool":
            print(f"{i:02d} [tool]      {short}")
        else:
            print(f"{i:02d} [{role}] {short}")
    print("-" * 60)


def save_history() -> None:
    """Сохраняет историю в history.json — можно открыть и посмотреть руками."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Предупреждение] Не смог сохранить историю: {e}")


# ---------------------------------------------------------------------------
# 4. ВЫЗОВ МОДЕЛИ (Ollama Cloud, нативный function calling)
# ---------------------------------------------------------------------------
def call_ollama(messages: list) -> dict:
    """Шлёт ВСЮ историю + tools в Ollama Cloud. Возвращает message модели."""
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS_SPEC,
            "stream": False,
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama API {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    return data["message"]  # {"role": "assistant", "content": ..., "tool_calls": [...]}


# ---------------------------------------------------------------------------
# 5. ОДИН ХОД АГЕНТА (но история — общая и не сбрасывается!)
# ---------------------------------------------------------------------------
def run_turn(user_text: str, max_steps: int = 5) -> str:
    """Добавляет вопрос в общую историю, крутит цикл tool_calls и возвращает ответ."""
    # 1) Вопрос пользователя — тоже часть истории
    history.append({"role": "user", "content": user_text})
    print(f"\n[Вопрос] {user_text}")
    print(f"[Модель] {MODEL} | сообщений в истории: {len(history)}")

    for step in range(1, max_steps + 1):
        print(f"\n[Шаг {step}]")

        # 2) Каждый раз отправляем ВСЮ историю целиком — так модель всё помнит
        msg = call_ollama(history)

        # 3) Ответ модели тоже кладём в историю (включая tool_calls!)
        #    Это важно: без этого модель "забудет", что вызывала инструмент.
        history.append(msg)

        content = (msg.get("content") or "").strip()
        tool_calls = msg.get("tool_calls") or []
        if content:
            print(f"[Модель] {content}")
        if not tool_calls:
            print(f"\n[Ответ] {content}")
            save_history()
            return content

        # 4) Модель попросила вызвать инструменты — выполняем по очереди
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments") or {}
            # arguments иногда приходят строкой — распарсим
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except json.JSONDecodeError:
                    args = {}
            print(f"[Вызов инструмента] {name}({args})")
            result = execute_tool(name, args)
            print(f"[Результат инструмента] {result}")
            # 5) Результат инструмента — тоже сообщение истории с role="tool"
            history.append({"role": "tool", "content": str(result)})
        # ... и цикл повторяется: снова шлём историю, модель решает дальше

    save_history()
    return "Не смог решить за отведённые шаги."


if __name__ == "__main__":
    print("=" * 60)
    print("  ПРИМИТИВНЫЙ ИИ-АГЕНТ (Python + Ollama Cloud + gemma4:31b)")
    print("  Инструменты: calculator, get_time")
    print("  Команды: /history (показать историю), /reset (очистить),")
    print("           пустая строка (выход)")
    print("=" * 60)
    print("\nПримеры по порядку (история все помнит):")
    print("  1. Сколько будет 137 * 46 + 11? Посчитай калькулятором.")
    print("  2. Запомни это число как мое любимое.")
    print("  3. Какое мое любимое число? Прибавь к нему 100 (калькулятором).")
    print("  4. /history — посмотреть переписку и tool calls")

    while True:
        try:
            q = input("\nВаш вопрос: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nПока!")
            break
        if not q:
            print("Пока!")
            break
        if q == "/history":
            print_history()
            continue
        if q == "/reset":
            history.clear()
            history.append({"role": "system", "content": SYSTEM_PROMPT})
            print("[История очищена]")
            continue
        try:
            run_turn(q)
        except Exception as e:
            print(f"\n[Ошибка] {e}")

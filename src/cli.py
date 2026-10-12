# -*- coding: utf-8 -*-
"""Консольный интерфейс: цикл ввода, команды /history и /reset."""

from src import agent_core, config
from src.history_store import print_history as render_history


def main() -> None:
    config.require_api_key()
    print(f"LangGraph + Ollama Cloud ({config.MODEL})")
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
            render_history(agent_core.current_messages())
            continue
        if question == "/reset":
            agent_core.reset_thread()
            print("[История очищена]")
            continue
        try:
            print(f"\nАгент: {agent_core.run_turn(question)}")
        except Exception as exc:
            print(f"\n[Ошибка] {exc}")

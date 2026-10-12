# -*- coding: utf-8 -*-
"""Консольный интерфейс: цикл ввода, команды /history и /reset."""

from src import agent_core, config
from src.history_store import print_history as render_history


def main() -> None:
    config.require_api_key()
    print(f"LangGraph + {config.PROVIDER} ({config.MODEL})")
    print("Инструменты: calculator, get_time, convert_temperature, convert_distance,")
    print("            date_info, count_words, format_json, ask_subagent")
    print("Команды: /history, /reset, /model [имя]; пустая строка — выход")

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
        if question == "/model" or question.startswith("/model "):
            name = question[len("/model"):].strip()
            if not name:
                print(f"[Модель: {config.MODEL}]")
                print("Доступны: " + ", ".join(config.available_models()))
                print("Смена: /model <имя> (можно вписать любое имя вручную)")
            else:
                try:
                    print(f"[Модель: {agent_core.set_model(name)}]")
                except Exception as exc:
                    print(f"[Ошибка] {exc}")
            continue
        try:
            print(f"\nАгент: {agent_core.run_turn(question)}")
        except Exception as exc:
            print(f"\n[Ошибка] {exc}")

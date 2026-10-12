# -*- coding: utf-8 -*-
"""Точка входа: запуск консольного агента.

Вся логика разнесена по пакету src:
- src/config.py — константы, ключ, создание модели;
- src/tools.py — базовые инструменты;
- src/graph.py — построение графа LangGraph;
- src/subagent.py — субагент и ask_subagent;
- src/agent_core.py — главный агент и ходы диалога;
- src/history_store.py — сохранение и показ истории;
- src/cli.py — консольный цикл.
"""

from src.cli import main

if __name__ == "__main__":
    main()

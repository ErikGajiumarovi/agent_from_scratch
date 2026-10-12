# Простой ИИ-агент (Python + LangGraph + Ollama Cloud)

Минимальный пример агента с параллельным вызовом инструментов и одним субагентом.

## Запуск

```bash
# Нужен Python 3.10+
pip install -r requirements.txt
export OLLAMA_API_KEY="ваш_ключ_с_ollama.com/settings/keys"
python agent.py
```

Команды в чате: `/history` — показать текущий диалог, `/reset` — начать заново,
пустая строка — выход. Диалог хранится в SQLite (`data/agent.db`) и переживает
перезапуск программы; дополнительно каждый ход экспортируется в `history.json`
для просмотра.

## Структура

```
agent.py            # точка входа (тонкая обёртка над src.cli:main)
src/
  config.py         # константы, ключ OLLAMA_API_KEY, создание модели
  tools.py          # базовые инструменты + BASE_TOOLS
  graph.py          # построение графа LangGraph
  subagent.py       # субагент и инструмент ask_subagent
  agent_core.py     # главный агент, CONFIG, run_turn
  db.py             # SQLite: файл БД и checkpointer LangGraph
  history_store.py  # экспорт в history.json и печать истории
  cli.py            # консольный цикл (/history, /reset)
```

## Как устроено

- **LangGraph** повторяет цикл «модель → инструменты → модель» (сборка графа — `src/graph.py`, конфиг — `src/config.py`).
- **`ToolNode`** выполняет несколько вызовов инструмента параллельно, если модель
  вернула их в одном ответе. Модель сама решает, какие вызовы независимы.
- **Инструменты** (`src/tools.py`): `calculator`, `get_time`, `convert_temperature`,
  `convert_distance`, `date_info`, `count_words`, `format_json`.
- **`ask_subagent`** (`src/subagent.py`) передаёт отдельную задачу изолированному субагенту. У него
  свой короткий системный промпт и те же основные инструменты.
- **Главный агент** (`src/agent_core.py`): системный промпт, checkpointer, `run_turn`.
- **История** (`src/history_store.py`): экспорт в `history.json` и печать; консольный цикл — `src/cli.py`,
  точка входа — `agent.py`.
- **Память диалога** — SQLite через `SqliteSaver` (`src/db.py`, файл `data/agent.db`,
  путь меняется переменной `AGENT_DB_PATH`): состояние графа сохраняется между
  запусками, `/reset` очищает тред через `delete_thread`.

Примеры: «Переведи 100 F в C», «Сколько слов в этом тексте?»,
«Какой день недели был 2026-01-01?», «Отформатируй этот JSON». Если модель
вернёт несколько независимых вызовов инструментов вместе, граф выполнит их параллельно.

## Добавление инструмента

Создайте функцию с `@tool` в `src/tools.py` и добавьте её в список инструментов нужного агента:
в `BASE_TOOLS`, чтобы он был доступен обоим агентам; для главного агента добавьте его
в список рядом с `ask_subagent` в `src/agent_core.py`.

`history.json` — только читаемый экспорт текущего диалога для просмотра; источником
правды является SQLite-база (`data/agent.db`), которая подхватывается автоматически
при старте.

## Ключ

Не коммитьте `OLLAMA_API_KEY` в git. Если ключ опубликован, отзовите его в
[настройках Ollama](https://ollama.com/settings/keys).

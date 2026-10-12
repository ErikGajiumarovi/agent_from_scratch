# Простой ИИ-агент (Python + LangGraph + OpenRouter)

Минимальный пример агента с параллельным вызовом инструментов и одним субагентом.

## Запуск

```bash
# Нужен Python 3.10+
pip install -r requirements.txt
export OPENROUTER_API_KEY="ваш_ключ_с_openrouter.ai/settings/keys"
# по желанию: OPENROUTER_MODEL="другая_модель" (по умолчанию google/gemma-4-31b-it:free)
python agent.py
```

Команды в чате: `/history` — показать текущий диалог, `/reset` — начать заново,
пустая строка — выход. Диалог хранится в SQLite (`data/agent.db`) и переживает
перезапуск программы; дополнительно каждый ход экспортируется в `history.json`
для просмотра.

## Веб-интерфейс

```bash
python web.py
# открыть http://127.0.0.1:8000 (хост/порт: AGENT_HOST, AGENT_PORT)
```

Слева — обычный чат, справа — «под капотом»: сырые события текущего хода
(вызовы инструментов с аргументами, их результаты, ответы модели — всё в
реальном времени через SSE) и полное состояние треда (каждое сообщение
с полным JSON). Кнопки «Обновить» и «Сбросить диалог». История общая
с консольным клиентом — та же SQLite-база.

## Структура

```
agent.py            # точка входа консольного клиента (тонкая обёртка над src.cli:main)
web.py              # точка входа веб-интерфейса (тонкая обёртка над src.web:main)
frontend/
  index.html        # страница: чат + панель «под капотом» (без зависимостей)
src/
  config.py         # константы, ключ OPENROUTER_API_KEY, создание модели
  tools.py          # базовые инструменты + BASE_TOOLS
  graph.py          # построение графа LangGraph
  subagent.py       # субагент и инструмент ask_subagent
  agent_core.py     # главный агент, CONFIG, run_turn, stream_turn
  db.py             # SQLite: файл БД и checkpointer LangGraph
  history_store.py  # экспорт в history.json, печать и dump_messages для API
  cli.py            # консольный цикл (/history, /reset)
  web.py            # HTTP-сервер: статика + /api/status|history|chat(SSE)|reset
```

## Как устроено

- **LangGraph** повторяет цикл «модель → инструменты → модель» (сборка графа — `src/graph.py`, конфиг — `src/config.py`).
- **`ToolNode`** выполняет несколько вызовов инструмента параллельно, если модель
  вернула их в одном ответе. Модель сама решает, какие вызовы независимы.
- **Инструменты** (`src/tools.py`): `calculator`, `get_time`, `convert_temperature`,
  `convert_distance`, `date_info`, `count_words`, `format_json`.
- **`ask_subagent`** (`src/subagent.py`) передаёт отдельную задачу изолированному субагенту. У него
  свой короткий системный промпт и те же основные инструменты.
- **Главный агент** (`src/agent_core.py`): системный промпт, checkpointer, `run_turn`
  и `stream_turn` (тот же ход, но события `tool_call`/`tool_result`/`answer` идут
  наружу по мере появления через `graph.stream`).
- **Веб** (`src/web.py` + `frontend/index.html`, только стандартная библиотека):
  страница чата, сырые события хода через SSE (`GET /api/chat?text=...`),
  состояние треда (`GET /api/history`), статус (`GET /api/status`),
  сброс (`POST /api/reset`).
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

Не коммитьте `OPENROUTER_API_KEY` в git. Если ключ опубликован, отзовите его в
[настройках OpenRouter](https://openrouter.ai/settings/keys).

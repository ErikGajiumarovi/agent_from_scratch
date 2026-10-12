# Простой ИИ-агент (Python + LangGraph)

Минимальный пример агента с параллельным вызовом инструментов и одним субагентом.
Провайдер модели переключается переменной `AGENT_PROVIDER`: `openrouter`
(по умолчанию) или `chatgpt` (обычная ChatGPT-подписка через `auth.json`).

## Запуск (веб-интерфейс)

```bash
# Нужен Python 3.10+
pip install -r requirements.txt
export OPENROUTER_API_KEY="ваш_ключ_с_openrouter.ai/settings/keys"
# по желанию: OPENROUTER_MODEL="другая_модель" (по умолчанию google/gemma-4-31b-it:free)
python web.py
# открыть http://127.0.0.1:8000 (хост/порт: AGENT_HOST, AGENT_PORT)
# или всё сразу: ./run.sh
```

Слева — обычный чат, справа — «под капотом»: сырые события текущего хода
(вызовы инструментов с аргументами, их результаты, ответы модели — всё в
реальном времени через SSE) и полное состояние треда (каждое сообщение
с полным JSON). Кнопки «Обновить» и «Сбросить диалог», в шапке — селектор
модели (включая ввод произвольного имени).

Диалог хранится в SQLite (`data/agent.db`) и переживает перезапуск программы;
дополнительно каждый ход экспортируется в `history.json` для просмотра.

## Структура

```
web.py              # точка входа веб-интерфейса (тонкая обёртка над src.web:main)
login.py            # точка входа для входа через ChatGPT-подписку
run.sh              # установка зависимостей + запуск web.py
frontend/
  index.html        # страница: чат + панель «под капотом» (без зависимостей)
src/
  config.py         # константы, провайдер (AGENT_PROVIDER), создание модели
  tools.py          # базовые инструменты + BASE_TOOLS
  graph.py          # построение графа LangGraph + события из обновлений
  subagent.py       # субагент, ask_subagent и журнал субчатов
  agent_core.py     # главный агент, CONFIG, stream_turn, set_model
  db.py             # SQLite: файл БД и checkpointer LangGraph
  history_store.py  # экспорт в history.json и dump_messages для API
  web.py            # HTTP-сервер: статика + /api/status|history|chat(SSE)|reset
  chatgpt_auth.py   # auth.json подписки: чтение и refresh OAuth-токенов
  chatgpt_model.py  # LangChain-модель поверх Codex-бэкенда (Responses API + SSE)
  chatgpt_login.py  # вход через подписку без Codex CLI (точка входа — login.py)
```

## Как устроено

- **LangGraph** повторяет цикл «модель → инструменты → модель» (сборка графа — `src/graph.py`, конфиг — `src/config.py`).
- **`ToolNode`** выполняет несколько вызовов инструмента параллельно, если модель
  вернула их в одном ответе. Модель сама решает, какие вызовы независимы.
- **Инструменты** (`src/tools.py`): `calculator`, `get_time`, `convert_temperature`,
  `convert_distance`, `date_info`, `count_words`, `format_json`.
- **`ask_subagent`** (`src/subagent.py`) передаёт отдельную задачу изолированному субагенту. У него
  свой короткий системный промпт и те же основные инструменты.
- **Главный агент** (`src/agent_core.py`): системный промпт, checkpointer,
  `stream_turn` (события `tool_call`/`tool_result`/`answer` идут наружу
  по мере появления через `graph.stream`) и `set_model`.
- **Веб** (`src/web.py` + `frontend/index.html`, только стандартная библиотека):
  страница чата, сырые события хода через SSE (`GET /api/chat?text=...`),
  состояние треда (`GET /api/history`), статус (`GET /api/status`),
  сброс (`POST /api/reset`), смена модели (`POST /api/model {"name": "..."}`,
  список — `GET /api/models`), субчаты (`GET /api/subchats`,
  `GET /api/subchat?id=N`).
- **История** (`src/history_store.py`): экспорт диалога в `history.json`
  и сериализация сообщений для API.
- **Память диалога** — SQLite через `SqliteSaver` (`src/db.py`, файл `data/agent.db`,
  путь меняется переменной `AGENT_DB_PATH`): состояние графа сохраняется между
  запусками, `/reset` очищает тред через `delete_thread`.

## Провайдеры (`AGENT_PROVIDER`)

- `openrouter` (по умолчанию): нужен `OPENROUTER_API_KEY`, модель — `OPENROUTER_MODEL`.
- `chatgpt`: работает через обычную ChatGPT-подписку, читает OAuth-токены
  из `~/.codex/auth.json` (путь меняется через `CHATGPT_AUTH_FILE`).
  Файл создаётся либо `codex login`, либо нашим `python login.py` — тот же
  официальный OAuth-флоу (PKCE + локальный callback на :1455), ставить Codex
  не нужно; полученный файл совместим и с самим Codex.
  Модель — `CHATGPT_MODEL` (по умолчанию `gpt-6-luna`, проверена также `gpt-5.5`).
  Протухший `access_token` обновляется через `refresh_token` автоматически,
  запросы идут на Codex-бэкенд (`chatgpt.com/backend-api/codex/responses`,
  обязательно `stream: true`). Запуск: `AGENT_PROVIDER=chatgpt python web.py`.
  Токены из файла никуда не коммитятся и не печатаются в логи.

## Субчаты

Каждый запуск `ask_subagent` пишется в журнал (`src/subagent.py`): задача,
модель, свои события (вызовы/результаты инструментов, ответ) и итог.
В вебе — отдельная секция «Субчаты»: карточки обновляются сразу, как
субагент закончил (и в конце хода), `/reset` очищает журнал вместе с историей.

## Смена модели на лету

Без перезапуска: селектор в шапке страницы (имя можно вписать любое вручную)
или `POST /api/model {"name": "..."}`. Агент и субагент пересобираются сразу,
история диалога сохраняется. Стартовые значения — `OPENROUTER_MODEL`
и `CHATGPT_MODEL`.

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

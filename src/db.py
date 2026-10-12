# -*- coding: utf-8 -*-
"""SQLite-хранилище: файл БД и checkpointer LangGraph на его основе.

Память диалога (состояние графа) хранится в SQLite, поэтому переживает
перезапуск программы. Путь к файлу задаётся переменной AGENT_DB_PATH
(по умолчанию data/agent.db).
"""

import atexit
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from src import config

_conn: sqlite3.Connection | None = None
_saver: SqliteSaver | None = None


def get_checkpointer() -> SqliteSaver:
    """Вернуть синглтон SqliteSaver (создаёт файл БД и таблицы при первом вызове)."""
    global _conn, _saver
    if _saver is None:
        db_path = Path(config.DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _saver = SqliteSaver(_conn)
        _saver.setup()
        atexit.register(close_db)
    return _saver


def close_db() -> None:
    """Закрыть соединение с БД (вызывается автоматически при выходе)."""
    global _conn, _saver
    if _conn is not None:
        try:
            _conn.close()
        finally:
            _conn = None
            _saver = None

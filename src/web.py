# -*- coding: utf-8 -*-
"""Простой веб-интерфейс: чат + сырое представление работы агента.

Только стандартная библиотека: ThreadingHTTPServer отдаёт frontend/index.html
и JSON/SSE API:
- GET  /             — страница чата
- GET  /api/status   — провайдер, модель, тред, путь к БД, число сообщений
- GET  /api/models   — провайдер, текущая модель, курированный список
- GET  /api/history  — сырые сообщения текущего треда
- GET  /api/chat?text=... — ход диалога, события идут через SSE
- POST /api/reset    — очистить тред
- POST /api/model    — переключить модель (JSON {"name": "..."})
"""

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src import agent_core, config
from src.history_store import dump_messages

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _send_json(handler: BaseHTTPRequestHandler, obj, status: int = 200) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_sse(handler: BaseHTTPRequestHandler, event: dict) -> None:
    handler.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
    handler.wfile.flush()


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentUI/1.0"

    def log_message(self, fmt, *args):  # тихие логи: одна строка на запрос
        print(f"[web] {self.address_string()} {self.command} {self.path} -> {fmt % args}")

    def _route(self):
        return urllib.parse.urlparse(self.path)

    def do_GET(self):
        parsed = self._route()
        if parsed.path in ("/", "/index.html"):
            page = (FRONTEND_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        elif parsed.path == "/api/status":
            _send_json(self, {"provider": config.PROVIDER, "model": config.MODEL,
                              "thread_id": config.THREAD_ID,
                              "db_path": config.DB_PATH,
                              "message_count": len(agent_core.current_messages())})
        elif parsed.path == "/api/models":
            _send_json(self, {"provider": config.PROVIDER, "current": config.MODEL,
                              "models": config.available_models()})
        elif parsed.path == "/api/history":
            _send_json(self, {"messages": dump_messages(agent_core.current_messages())})
        elif parsed.path == "/api/chat":
            text = urllib.parse.parse_qs(parsed.query).get("text", [""])[0].strip()
            if not text:
                _send_json(self, {"error": "пустой параметр text"}, status=400)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            # Без Content-Length и без Connection: keep-alive: ответ ограничен
            # закрытием соединения (иначе stdlib решит держать его открытым,
            # а клиент будет вечно ждать конца потока).
            self.end_headers()
            try:
                for event in agent_core.stream_turn(text):
                    _send_sse(self, event)
            except (ConnectionError, BrokenPipeError):
                pass
            except Exception as exc:
                try:
                    _send_sse(self, {"type": "error", "text": str(exc)})
                except (ConnectionError, BrokenPipeError):
                    pass
        else:
            _send_json(self, {"error": "not found"}, status=404)

    def do_POST(self):
        parsed = self._route()
        if parsed.path == "/api/reset":
            agent_core.reset_thread()
            _send_json(self, {"ok": True})
        elif parsed.path == "/api/model":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                name = agent_core.set_model(body.get("name", ""))
                _send_json(self, {"ok": True, "model": name})
            except (ValueError, KeyError) as exc:
                _send_json(self, {"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                _send_json(self, {"ok": False, "error": str(exc)[:300]}, status=500)
        else:
            _send_json(self, {"error": "not found"}, status=404)


def main() -> None:
    config.require_api_key()
    server = ThreadingHTTPServer((config.WEB_HOST, config.WEB_PORT), Handler)
    print(f"Веб-интерфейс: http://{config.WEB_HOST}:{config.WEB_PORT}")
    print("Остановка: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nПока!")
    finally:
        server.server_close()

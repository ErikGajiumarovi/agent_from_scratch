# -*- coding: utf-8 -*-
"""Вход через ChatGPT-подписку без Codex CLI (свой codex login).

Повторяет официальный OAuth-флоу Codex: PKCE + локальный callback-сервер
на allow-listed порту (1455, запасной 1457) + обмен кода на токены.
Используются те же client_id и redirect_uri, что у Codex CLI, поэтому
полученный auth.json совместим и с самим Codex.

Запуск: python login.py — откроется браузер, после входа в ChatGPT
токены запишутся в ~/.codex/auth.json (или CHATGPT_AUTH_FILE).
"""

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from src import chatgpt_auth

ISSUER = "https://auth.openai.com"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
PORTS = (1455, 1457)
CALLBACK_PATH = "/auth/callback"
SCOPE = "openid profile email offline_access api.connectors.read api.connectors.invoke"
TIMEOUT_SECONDS = 300


def pkce_pair(verifier: str | None = None) -> tuple[str, str]:
    """Сгенерировать (verifier, challenge) по RFC 7636."""
    verifier = verifier or secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(port: int, challenge: str, state: str) -> tuple[str, str]:
    """Собрать authorize-URL и redirect_uri (как у Codex CLI)."""
    redirect_uri = f"http://127.0.0.1:{port}{CALLBACK_PATH}"
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex_cli_rs",
    }
    return f"{ISSUER}/oauth/authorize?" + urllib.parse.urlencode(params), redirect_uri


def parse_callback(path: str, expected_state: str) -> str:
    """Достать authorization code из callback-запроса, проверив state."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    if query.get("error"):
        desc = (query.get("error_description") or query.get("error"))[0]
        raise chatgpt_auth.ChatGPTAuthError(f"Вход отклонён: {desc}")
    if (query.get("state") or [""])[0] != expected_state:
        raise chatgpt_auth.ChatGPTAuthError("Несовпадение state — возможно, чужой запрос.")
    code = (query.get("code") or [""])[0]
    if not code:
        raise chatgpt_auth.ChatGPTAuthError("В callback нет authorization code.")
    return code


def exchange_code(code: str, redirect_uri: str, verifier: str,
                  token_url: str = f"{ISSUER}/oauth/token",
                  timeout: int = 30) -> dict:
    """Обменять code на токены (form-encoded, как у Codex). Возвращает поля ответа."""
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }).encode("ascii")
    req = urllib.request.Request(token_url, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception as exc:
        raise chatgpt_auth.ChatGPTAuthError(
            f"Обмен кода на токены не удался (HTTP {getattr(exc, 'code', '?')}). "
            "Код одноразовый — начните вход заново: python login.py"
        )
    if not data.get("access_token") or not data.get("refresh_token"):
        raise chatgpt_auth.ChatGPTAuthError("Сервер не вернул токены. Начните вход заново.")
    return data


def account_id_from_id_token(id_token: str) -> str:
    """Достать chatgpt_account_id из id_token (тот же путь, что у Codex)."""
    payload_b64 = id_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    auth = claims.get("https://api.openai.com/auth") or {}
    return auth.get("chatgpt_account_id") or ""


def id_email(id_token: str) -> str:
    """Email из id_token для приветствия (не секрет, но и не печатаем лишнего)."""
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        return claims.get("email") or ""
    except (IndexError, ValueError):
        return ""


class _CallbackHandler(BaseHTTPRequestHandler):
    expected_state = ""
    code: str | None = None
    error: Exception | None = None
    done = threading.Event()

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        try:
            if urllib.parse.urlparse(self.path).path != CALLBACK_PATH:
                self.send_error(404)
                return
            _CallbackHandler.code = parse_callback(self.path, _CallbackHandler.expected_state)
            body = ("<html><body style='font-family:sans-serif'>"
                    "<h2>Вход выполнен</h2><p>Вернитесь в терминал.</p></body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001 — показать ошибку в браузере
            _CallbackHandler.error = exc
            body = f"<html><body><h2>Ошибка входа</h2><p>{exc}</p></body></html>".encode()
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionError, BrokenPipeError):
                pass
        finally:
            _CallbackHandler.done.set()


def wait_for_code(port: int, state: str, timeout: int = TIMEOUT_SECONDS) -> str:
    """Поднять callback-сервер и дождаться кода из браузера."""
    _CallbackHandler.expected_state = state
    _CallbackHandler.code = None
    _CallbackHandler.error = None
    _CallbackHandler.done.clear()
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not _CallbackHandler.done.wait(timeout):
            raise chatgpt_auth.ChatGPTAuthError("Время вышло — начните вход заново.")
        if _CallbackHandler.error is not None:
            raise _CallbackHandler.error
        return _CallbackHandler.code
    finally:
        server.shutdown()
        thread.join(timeout=5)


def main() -> None:
    print("Вход через ChatGPT-подписку (без Codex CLI).")
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    server_port = None
    auth_url = ""
    redirect_uri = ""
    for port in PORTS:
        try:
            probe = HTTPServer(("127.0.0.1", port), _CallbackHandler)
            probe.server_close()
            server_port = port
            auth_url, redirect_uri = build_authorize_url(port, challenge, state)
            break
        except OSError:
            continue
    if server_port is None:
        print(f"[Ошибка] Порты {PORTS} заняты — освободите один и повторите.")
        raise SystemExit(1)
    print(f"Открываю браузер. Если не открылся — перейдите вручную:\n{auth_url}\n")
    print("Войдите в ChatGPT в браузере, затем вернитесь сюда.")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
    code = wait_for_code(server_port, state)
    print("Код получен, обмениваю на токены…")
    tokens = exchange_code(code, redirect_uri, verifier)
    account_id = account_id_from_id_token(tokens.get("id_token", ""))
    data = {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
            "tokens": {"id_token": tokens.get("id_token", ""),
                       "access_token": tokens["access_token"],
                       "refresh_token": tokens["refresh_token"],
                       "account_id": account_id},
            "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())}
    chatgpt_auth.save_auth(data)
    email = id_email(tokens.get("id_token", ""))
    print(f"Готово: вошли как {email or 'пользователь ChatGPT'}, "
          f"файл {chatgpt_auth.auth_file()}.")
    if not account_id:
        print("[Внимание] account_id не найден в токенах — при ошибках перелогиньтесь.")
    print("Проверка: AGENT_PROVIDER=chatgpt python web.py (открыть http://127.0.0.1:8000)")

# -*- coding: utf-8 -*-
"""Доступ к ChatGPT-подписке через auth.json (формат Codex CLI).

Читает OAuth-токены из ~/.codex/auth.json (путь меняется через CHATGPT_AUTH_FILE),
при необходимости обновляет access_token через refresh_token
(POST https://auth.openai.com/oauth/token) и сохраняет файл обратно.
Значения токенов никогда не печатаются в логи.
"""

import base64
import json
import os
import time
import urllib.request
from pathlib import Path

TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
# За сколько секунд до истечения считать access_token протухшим (как в Codex: 5 мин).
REFRESH_LEEWAY_SECONDS = 300


class ChatGPTAuthError(Exception):
    """Нет валидной авторизации ChatGPT-подписки."""


def auth_file() -> Path:
    return Path(os.getenv("CHATGPT_AUTH_FILE", "~/.codex/auth.json")).expanduser()


def load_auth() -> dict:
    """Прочитать auth.json. Бросает ChatGPTAuthError с подсказкой."""
    path = auth_file()
    if not path.exists():
        raise ChatGPTAuthError(
            f"Нет файла {path}. Войдите через Codex (`codex login`) "
            "или укажите путь в CHATGPT_AUTH_FILE."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ChatGPTAuthError(f"Не читается {path}: {exc}")
    tokens = data.get("tokens") or {}
    if not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise ChatGPTAuthError(
            f"В {path} нет токенов. Перелогиньтесь (`codex login`)."
        )
    return data


def token_expiry(jwt: str) -> int | None:
    """Достать exp из JWT. None — не разобрать."""
    try:
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64)).get("exp")
    except (IndexError, ValueError):
        return None


def is_expired(access_token: str) -> bool:
    exp = token_expiry(access_token)
    return exp is None or exp <= time.time() + REFRESH_LEEWAY_SECONDS


def refresh_tokens(refresh_token: str, timeout: int = 30) -> dict:
    """Обменять refresh_token на новые токены. Возвращает поля ответа OAuth."""
    body = json.dumps({
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except Exception as exc:
        code = getattr(exc, "code", "?")
        raise ChatGPTAuthError(
            f"Не удалось обновить токены (HTTP {code}). "
            "Возможно, refresh_token протух — перелогиньтесь (`codex login`)."
        )


def save_auth(data: dict) -> None:
    """Атомарно записать auth.json обратно, сохранив права 600."""
    path = auth_file()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def get_credentials() -> tuple[str, str]:
    """Вернуть (access_token, account_id), обновив токены при необходимости."""
    data = load_auth()
    tokens = data["tokens"]
    if is_expired(tokens["access_token"]):
        print("[auth] access_token истёк, обновляю через refresh_token…")
        fresh = refresh_tokens(tokens["refresh_token"])
        tokens["access_token"] = fresh["access_token"]
        tokens["id_token"] = fresh.get("id_token", tokens.get("id_token"))
        if fresh.get("refresh_token"):
            tokens["refresh_token"] = fresh["refresh_token"]
        data["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
        save_auth(data)
    account_id = tokens.get("account_id") or ""
    if not account_id:
        raise ChatGPTAuthError("В auth.json нет account_id. Перелогиньтесь (`codex login`).")
    return tokens["access_token"], account_id

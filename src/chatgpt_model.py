# -*- coding: utf-8 -*-
"""Чат-модель через ChatGPT-подписку (Codex-бэкенд, Responses API + SSE).

Бэкенд требует stream=true, ходим на
https://chatgpt.com/backend-api/codex/responses
с заголовками Authorization: Bearer <access_token> и
ChatGPT-Account-ID: <account_id> (см. открытый репозиторий openai/codex).

Реализует интерфейс LangChain BaseChatModel, поэтому работает с
bind_tools и графом LangGraph без изменений остального кода.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Iterator, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from src import chatgpt_auth

RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
TOOL_OUTPUT_LIMIT = 32000


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


def messages_to_input(messages: list[BaseMessage]) -> list[dict]:
    """LangChain-сообщения -> input[] Responses API (чистая функция)."""
    items: list[dict] = []
    for message in messages:
        kind = getattr(message, "type", "")
        if kind == "system":
            items.append({"role": "developer",
                          "content": [{"type": "input_text",
                                       "text": _text_of(message.content)}]})
        elif kind == "human":
            items.append({"role": "user",
                          "content": [{"type": "input_text",
                                       "text": _text_of(message.content)}]})
        elif kind == "ai":
            if _text_of(message.content):
                items.append({"role": "assistant",
                              "content": [{"type": "output_text",
                                           "text": _text_of(message.content)}]})
            for call in getattr(message, "tool_calls", []) or []:
                args = call.get("args", {})
                items.append({"type": "function_call",
                              "call_id": call.get("id", ""),
                              "name": call.get("name", ""),
                              "arguments": args if isinstance(args, str)
                              else json.dumps(args, ensure_ascii=False)})
        elif kind == "tool":
            output = _text_of(message.content)
            if len(output) > TOOL_OUTPUT_LIMIT:
                output = output[:TOOL_OUTPUT_LIMIT] + "\n…[обрезано]"
            items.append({"type": "function_call_output",
                          "call_id": getattr(message, "tool_call_id", ""),
                          "output": output})
    return items


def normalize_tools(tools: list) -> list[dict]:
    """Инструменты bind_tools -> плоский формат Responses API (чистая функция).

    LangChain отдаёт чат-формат {"type": "function", "function": {...}},
    Responses API ждёт поля на верхнем уровне.
    """
    normalized = []
    for tool in tools or []:
        if isinstance(tool, dict) and isinstance(tool.get("function"), dict):
            flat = {"type": "function", **tool["function"]}
            normalized.append(flat)
        else:
            normalized.append(tool)
    return normalized


def collect_sse(lines: Iterator[str]) -> tuple[str, list[dict], dict]:
    """Собрать текст, вызовы функций и usage из SSE-потока (чистая функция)."""
    text_parts: list[str] = []
    calls: list[dict] = []
    usage: dict = {}
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except ValueError:
            continue
        etype = event.get("type", "")
        if etype == "response.output_text.delta":
            delta = event.get("delta", "")
            if isinstance(delta, str):
                text_parts.append(delta)
        elif etype == "response.output_item.done":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                calls.append({"call_id": item.get("call_id", ""),
                              "name": item.get("name", ""),
                              "arguments": item.get("arguments", "")})
        elif etype == "response.completed":
            usage = event.get("response", {}).get("usage") or {}
        elif etype in ("response.failed", "error"):
            err = event.get("error") or event.get("response", {})
            raise RuntimeError(f"Codex-бэкенд вернул ошибку: {err}")
    return "".join(text_parts), calls, usage


class ChatGPTResponsesModel(BaseChatModel):
    """LangChain-модель поверх ChatGPT-подписки."""

    model: str
    timeout: int = 180

    @property
    def _llm_type(self) -> str:
        return "chatgpt-responses"

    def bind_tools(self, tools, tool_choice=None, **kwargs):
        """Привязать инструменты (конвертация в OpenAI-формат, как у ChatOpenAI)."""
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        return super().bind(tools=formatted, tool_choice=tool_choice, **kwargs)

    def _headers(self) -> dict[str, str]:
        access_token, account_id = chatgpt_auth.get_credentials()
        return {"Authorization": f"Bearer {access_token}",
                "ChatGPT-Account-ID": account_id}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "store": False,
            "stream": True,
            "input": messages_to_input(messages),
        }
        tools = normalize_tools(kwargs.get("tools"))
        if tools:
            payload["tools"] = tools
            if kwargs.get("tool_choice"):
                payload["tool_choice"] = kwargs["tool_choice"]
        headers = self._headers()
        try:
            text, calls, usage = collect_sse(
                self._stream_with_headers(payload, headers))
        except RuntimeError as exc:
            if "HTTP 401" not in str(exc):
                raise
            # Токен могли отозвать: обновить принудительно и повторить один раз.
            data = chatgpt_auth.load_auth()
            fresh = chatgpt_auth.refresh_tokens(data["tokens"]["refresh_token"])
            data["tokens"]["access_token"] = fresh["access_token"]
            chatgpt_auth.save_auth(data)
            headers = self._headers()
            text, calls, usage = collect_sse(
                self._stream_with_headers(payload, headers))

        tool_calls = []
        invalid_tool_calls = []
        for call in calls:
            try:
                args = json.loads(call["arguments"] or "{}")
            except ValueError:
                invalid_tool_calls.append({"name": call["name"], "args": call["arguments"],
                                           "id": call["call_id"],
                                           "error": "arguments — не JSON"})
                continue
            tool_calls.append({"name": call["name"], "args": args,
                               "id": call["call_id"], "type": "tool_call"})
        message = AIMessage(content=text, tool_calls=tool_calls,
                            invalid_tool_calls=invalid_tool_calls,
                            response_metadata={"model": self.model})
        if isinstance(usage, dict) and usage.get("total_tokens") is not None:
            try:
                message.usage_metadata = {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)}
            except Exception:
                pass
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream_with_headers(self, payload: dict, headers: dict) -> Iterator[str]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(RESPONSES_URL, data=body,
                                     headers={**headers,
                                              "Content-Type": "application/json",
                                              "Accept": "text/event-stream"})
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        with resp:
            for raw in resp:
                yield raw.decode("utf-8", "replace")

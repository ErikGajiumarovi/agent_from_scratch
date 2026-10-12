# -*- coding: utf-8 -*-
"""Построение графа LangGraph: цикл «модель → инструменты → модель»."""

from langchain_core.messages import SystemMessage
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


def build_agent(model, tools: list, system_prompt: str, checkpointer=None):
    """Создать простой цикл модель → инструменты → модель."""
    model_with_tools = model.bind_tools(tools)

    def call_model(state: MessagesState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt), *messages]
        return {"messages": [model_with_tools.invoke(messages)]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    builder.set_entry_point("agent")
    return builder.compile(checkpointer=checkpointer)


def events_from_chunk(chunk: dict) -> list:
    """Превратить обновление графа (stream_mode='updates') в плоские события.

    События: tool_call {name, args, id}, tool_result {name, content, tool_call_id},
    answer {text}. Используются веб-интерфейсом и журналом субчатов.
    """
    events = []
    for payload in chunk.values():
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        for message in messages:
            kind = getattr(message, "type", "")
            if kind == "ai":
                for call in getattr(message, "tool_calls", []) or []:
                    events.append({"type": "tool_call", "name": call.get("name", "?"),
                                   "args": call.get("args", {}), "id": call.get("id", "")})
                if getattr(message, "content", ""):
                    events.append({"type": "answer", "text": str(message.content)})
            elif kind == "tool":
                events.append({"type": "tool_result", "name": getattr(message, "name", ""),
                               "content": str(getattr(message, "content", "")),
                               "tool_call_id": getattr(message, "tool_call_id", "")})
    return events

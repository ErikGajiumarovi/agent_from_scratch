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

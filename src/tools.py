# -*- coding: utf-8 -*-
"""Базовые инструменты главного агента и субагента."""

import ast
import datetime
import json

from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """Безопасно вычислить простое математическое выражение."""
    try:
        tree = ast.parse(expression, mode="eval")
        allowed = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
            ast.USub, ast.UAdd, ast.FloorDiv, ast.Load,
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                return f"Ошибка: запрещённая операция {type(node).__name__}"
        return str(eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}))
    except Exception as exc:
        return f"Ошибка вычисления: {exc}"


@tool
def get_time() -> str:
    """Узнать текущие дату и время."""
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


@tool
def convert_temperature(value: float, from_unit: str, to_unit: str) -> str:
    """Перевести температуру между Celsius, Fahrenheit и Kelvin."""
    units = {"c": "c", "celsius": "c", "f": "f", "fahrenheit": "f",
             "k": "k", "kelvin": "k"}
    source = units.get(from_unit.strip().lower())
    target = units.get(to_unit.strip().lower())
    if source is None or target is None:
        return "Ошибка: единицы температуры — C, F или K."
    celsius = value if source == "c" else (value - 32) * 5 / 9 if source == "f" else value - 273.15
    if celsius < -273.15:
        return "Ошибка: температура ниже абсолютного нуля."
    result = celsius if target == "c" else celsius * 9 / 5 + 32 if target == "f" else celsius + 273.15
    return f"{value:g} {source.upper()} = {result:.2f} {target.upper()}"


@tool
def convert_distance(value: float, from_unit: str, to_unit: str) -> str:
    """Перевести расстояние между m, km, cm, mi и ft."""
    meters = {"m": 1, "meter": 1, "meters": 1,
              "km": 1000, "kilometer": 1000, "kilometers": 1000,
              "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
              "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
              "ft": 0.3048, "foot": 0.3048, "feet": 0.3048}
    source = from_unit.strip().lower()
    target = to_unit.strip().lower()
    if source not in meters or target not in meters:
        return "Ошибка: единицы расстояния — m, km, cm, mi или ft."
    return f"{value:g} {source} = {value * meters[source] / meters[target]:.4g} {target}"


@tool
def date_info(date: str) -> str:
    """Показать день недели и номер дня года для даты YYYY-MM-DD."""
    try:
        parsed = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        weekdays = ("понедельник", "вторник", "среда", "четверг",
                    "пятница", "суббота", "воскресенье")
        return f"{date} — {weekdays[parsed.weekday()]}, день года №{parsed.timetuple().tm_yday}."
    except ValueError:
        return "Ошибка: укажите дату в формате YYYY-MM-DD."


@tool
def count_words(text: str) -> str:
    """Посчитать слова, символы и символы без пробелов в тексте."""
    return (f"Слов: {len(text.split())}; символов: {len(text)}; "
            f"без пробелов: {len(''.join(text.split()))}.")


@tool
def format_json(json_text: str) -> str:
    """Проверить JSON и отформатировать его с отступами."""
    try:
        return json.dumps(json.loads(json_text), ensure_ascii=False, indent=2)
    except json.JSONDecodeError as exc:
        return f"Некорректный JSON: {exc.msg} (строка {exc.lineno}, столбец {exc.colno})."


BASE_TOOLS = [calculator, get_time, convert_temperature, convert_distance,
              date_info, count_words, format_json]

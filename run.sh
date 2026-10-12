#!/usr/bin/env bash
# Простой запуск примитивного ИИ-агента:
# устанавливает зависимости и запускает agent.py
# Использование:
#   chmod +x run.sh
#   ./run.sh
#   OPENROUTER_API_KEY="ваш_ключ" ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "== 1/3 Проверка Python =="
if ! command -v python3 >/dev/null 2>&1; then
  echo "ОШИБКА: python3 не найден. Установите Python 3.10+."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "ОШИБКА: для LangGraph нужен Python 3.10 или новее."
  exit 1
fi
python3 --version

echo ""
echo "== 2/3 Установка зависимостей =="
python3 -m pip install -q -r requirements.txt
echo "OK: зависимости установлены."

echo ""
echo "== 3/3 Запуск агента (OpenRouter, модель: ${OPENROUTER_MODEL:-google/gemma-4-31b-it:free}) =="
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "ВНИМАНИЕ: OPENROUTER_API_KEY не задан."
  echo "Задайте его так: OPENROUTER_API_KEY=\"ваш_ключ\" ./run.sh"
  echo "Ключ: https://openrouter.ai/settings/keys"
  echo ""
fi

exec python3 agent.py "$@"

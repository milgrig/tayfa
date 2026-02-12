#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление историей переписки с агентами.

Каждый агент имеет свой файл chat_history.json в папке .tayfa/{agent_name}/.
Файл содержит список сообщений (максимум 500 последних) с метаданными.

Формат сообщения:
{
    "id": "msg_001",
    "timestamp": "2026-02-12T10:45:00",
    "direction": "to_agent",
    "prompt": "Текст отправленного промпта",
    "result": "Ответ агента",
    "runtime": "claude",
    "cost_usd": 0.05,
    "duration_sec": 12.5,
    "task_id": "T002",
    "success": true
}

Использование:
    from chat_history_manager import save_message, get_history, clear_history

    # Сохранить сообщение
    msg = save_message(
        agent_name="developer_backend",
        prompt="Создай функцию...",
        result="Готово, создал...",
        runtime="claude",
        cost_usd=0.03,
        duration_sec=5.2,
        task_id="T001",
        success=True
    )

    # Получить историю с пагинацией
    history = get_history("developer_backend", limit=50, offset=0)

    # Очистить историю
    clear_history("developer_backend")
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Путь к .tayfa текущего проекта (устанавливается извне)
_TAYFA_DIR: Path | None = None

# Максимальное количество сообщений в истории (FIFO)
MAX_HISTORY_SIZE = 500


def set_tayfa_dir(path: str | Path) -> None:
    """Установить путь к .tayfa текущего проекта."""
    global _TAYFA_DIR
    _TAYFA_DIR = Path(path) if path else None


def get_tayfa_dir() -> Path | None:
    """Получить путь к .tayfa текущего проекта."""
    return _TAYFA_DIR


def _get_history_file(agent_name: str) -> Path | None:
    """Получить путь к файлу истории агента."""
    if _TAYFA_DIR is None:
        return None
    return _TAYFA_DIR / agent_name / "chat_history.json"


def _load_history(agent_name: str) -> list[dict]:
    """Загрузить историю из файла. Возвращает пустой список если файла нет."""
    history_file = _get_history_file(agent_name)
    if history_file is None or not history_file.exists():
        return []
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "messages" in data:
            return data["messages"]
        return []
    except Exception:
        return []


def _save_history(agent_name: str, messages: list[dict]) -> bool:
    """
    Сохранить историю в файл. Использует атомарную запись (temp + rename).
    Возвращает True при успехе.
    """
    history_file = _get_history_file(agent_name)
    if history_file is None:
        return False

    # Создаём директорию агента если её нет
    history_file.parent.mkdir(parents=True, exist_ok=True)

    # Атомарная запись: пишем во временный файл, затем переименовываем
    try:
        fd, temp_path = tempfile.mkstemp(
            suffix=".json",
            prefix="chat_history_",
            dir=str(history_file.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            # Переименовываем (атомарно на большинстве FS)
            os.replace(temp_path, history_file)
            return True
        except Exception:
            # Удаляем временный файл при ошибке
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise
    except Exception:
        return False


def _generate_message_id(messages: list[dict]) -> str:
    """Генерирует уникальный ID сообщения."""
    if not messages:
        return "msg_001"

    # Находим максимальный номер
    max_num = 0
    for msg in messages:
        msg_id = msg.get("id", "")
        if msg_id.startswith("msg_"):
            try:
                num = int(msg_id[4:])
                max_num = max(max_num, num)
            except ValueError:
                pass

    return f"msg_{max_num + 1:03d}"


def _now_iso() -> str:
    """Текущее время в ISO 8601 формате."""
    return datetime.now().isoformat(timespec="seconds")


def save_message(
    agent_name: str,
    prompt: str,
    result: str = "",
    runtime: str = "claude",
    cost_usd: float | None = None,
    duration_sec: float | None = None,
    task_id: str | None = None,
    success: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict | None:
    """
    Сохранить сообщение в историю чата с агентом.

    Args:
        agent_name: Имя агента (например, "developer_backend")
        prompt: Текст отправленного промпта
        result: Ответ агента
        runtime: "claude" или "cursor"
        cost_usd: Стоимость запроса в USD (если доступна)
        duration_sec: Время выполнения в секундах
        task_id: ID задачи (если сообщение в рамках задачи)
        success: True если запрос успешен
        extra: Дополнительные поля для сохранения

    Returns:
        Сохранённое сообщение или None при ошибке
    """
    if _TAYFA_DIR is None:
        return None

    messages = _load_history(agent_name)

    message = {
        "id": _generate_message_id(messages),
        "timestamp": _now_iso(),
        "direction": "to_agent",  # Запрос всегда "к агенту", result содержит ответ
        "prompt": prompt,
        "result": result,
        "runtime": runtime,
        "success": success,
    }

    # Добавляем опциональные поля только если они заданы
    if cost_usd is not None:
        message["cost_usd"] = cost_usd
    if duration_sec is not None:
        message["duration_sec"] = round(duration_sec, 2)
    if task_id:
        message["task_id"] = task_id
    if extra:
        message.update(extra)

    messages.append(message)

    # FIFO: оставляем только последние MAX_HISTORY_SIZE сообщений
    if len(messages) > MAX_HISTORY_SIZE:
        messages = messages[-MAX_HISTORY_SIZE:]

    if _save_history(agent_name, messages):
        return message
    return None


def get_history(
    agent_name: str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Получить историю переписки с агентом.

    Args:
        agent_name: Имя агента
        limit: Максимальное количество сообщений (default 50)
        offset: Смещение от начала (для пагинации)

    Returns:
        {"messages": [...], "total": int, "limit": int, "offset": int}
    """
    messages = _load_history(agent_name)
    total = len(messages)

    # Возвращаем сообщения в хронологическом порядке (от старых к новым)
    # Пагинация работает от конца (новые сообщения последние)
    if offset > 0:
        messages = messages[:-offset] if offset < len(messages) else []

    if limit > 0:
        messages = messages[-limit:] if limit < len(messages) else messages

    return {
        "messages": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def clear_history(agent_name: str) -> dict:
    """
    Очистить историю переписки с агентом.

    Returns:
        {"status": "cleared", "deleted_count": int}
    """
    messages = _load_history(agent_name)
    deleted_count = len(messages)

    if _save_history(agent_name, []):
        return {"status": "cleared", "deleted_count": deleted_count}
    return {"status": "error", "deleted_count": 0, "error": "Failed to save empty history"}


def get_last_messages(agent_name: str, count: int = 5) -> list[dict]:
    """
    Получить последние N сообщений (для контекста).

    Args:
        agent_name: Имя агента
        count: Количество сообщений

    Returns:
        Список последних сообщений
    """
    messages = _load_history(agent_name)
    return messages[-count:] if count < len(messages) else messages


def search_history(
    agent_name: str,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """
    Поиск в истории по тексту промпта или результата.

    Args:
        agent_name: Имя агента
        query: Строка поиска (регистронезависимый)
        limit: Максимальное количество результатов

    Returns:
        Список найденных сообщений
    """
    messages = _load_history(agent_name)
    query_lower = query.lower()

    results = []
    for msg in reversed(messages):  # От новых к старым
        prompt = msg.get("prompt", "").lower()
        result = msg.get("result", "").lower()
        if query_lower in prompt or query_lower in result:
            results.append(msg)
            if len(results) >= limit:
                break

    return results

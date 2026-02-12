#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для chat_history_manager.py

Проверка задачи T002: Хранение истории переписки (backend)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent.parent / "kok" / "template_tayfa" / "common"))

from chat_history_manager import (
    save_message,
    get_history,
    clear_history,
    get_last_messages,
    search_history,
    set_tayfa_dir,
    get_tayfa_dir,
    MAX_HISTORY_SIZE,
)


class TestResults:
    """Класс для сбора результатов тестов"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  ✅ {name}")

    def fail(self, name, reason):
        self.failed += 1
        self.errors.append(f"{name}: {reason}")
        print(f"  ❌ {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"Итого: {self.passed}/{total} тестов пройдено")
        if self.errors:
            print("\nОшибки:")
            for e in self.errors:
                print(f"  - {e}")
        return self.failed == 0


def test_chat_history():
    """Основные тесты модуля chat_history_manager"""
    results = TestResults()

    # Создаём временную директорию для тестов
    with tempfile.TemporaryDirectory() as temp_dir:
        tayfa_dir = Path(temp_dir)
        set_tayfa_dir(tayfa_dir)

        test_agent = "test_agent"

        # ═══ Тест 1: Проверка set_tayfa_dir ═══
        print("\n1. Проверка set_tayfa_dir/get_tayfa_dir")
        if get_tayfa_dir() == tayfa_dir:
            results.ok("set_tayfa_dir корректно устанавливает путь")
        else:
            results.fail("set_tayfa_dir", f"Ожидалось {tayfa_dir}, получено {get_tayfa_dir()}")

        # ═══ Тест 2: Сохранение сообщения ═══
        print("\n2. Сохранение сообщения (save_message)")
        msg = save_message(
            agent_name=test_agent,
            prompt="Тестовый промпт",
            result="Тестовый результат",
            runtime="claude",
            cost_usd=0.05,
            duration_sec=5.5,
            task_id="T001",
            success=True
        )

        if msg is not None:
            results.ok("save_message возвращает сообщение")
        else:
            results.fail("save_message", "Вернул None")

        # Проверяем обязательные поля
        required_fields = ["id", "timestamp", "direction", "prompt", "result", "runtime", "success"]
        missing = [f for f in required_fields if f not in (msg or {})]
        if not missing:
            results.ok("Все обязательные поля присутствуют")
        else:
            results.fail("Обязательные поля", f"Отсутствуют: {missing}")

        # Проверяем опциональные поля
        if msg and msg.get("cost_usd") == 0.05:
            results.ok("cost_usd сохранено корректно")
        else:
            results.fail("cost_usd", f"Ожидалось 0.05, получено {msg.get('cost_usd') if msg else 'None'}")

        if msg and msg.get("duration_sec") == 5.5:
            results.ok("duration_sec сохранено корректно")
        else:
            results.fail("duration_sec", f"Ожидалось 5.5, получено {msg.get('duration_sec') if msg else 'None'}")

        if msg and msg.get("task_id") == "T001":
            results.ok("task_id сохранено корректно")
        else:
            results.fail("task_id", f"Ожидалось T001, получено {msg.get('task_id') if msg else 'None'}")

        # ═══ Тест 3: Проверка файла истории ═══
        print("\n3. Проверка файла истории")
        history_file = tayfa_dir / test_agent / "chat_history.json"
        if history_file.exists():
            results.ok("Файл chat_history.json создан")
        else:
            results.fail("Файл истории", f"Файл {history_file} не создан")

        # ═══ Тест 4: Получение истории ═══
        print("\n4. Получение истории (get_history)")
        history = get_history(test_agent)

        if "messages" in history and "total" in history:
            results.ok("get_history возвращает корректную структуру")
        else:
            results.fail("get_history структура", f"Получено: {history.keys() if isinstance(history, dict) else type(history)}")

        if history.get("total") == 1:
            results.ok("total = 1 после одного сообщения")
        else:
            results.fail("total", f"Ожидалось 1, получено {history.get('total')}")

        # ═══ Тест 5: Пагинация ═══
        print("\n5. Пагинация")
        # Добавим ещё несколько сообщений
        for i in range(5):
            save_message(test_agent, f"Промпт {i+2}", f"Результат {i+2}", "claude")

        # Проверяем limit
        limited = get_history(test_agent, limit=3)
        if len(limited.get("messages", [])) == 3:
            results.ok("limit работает корректно")
        else:
            results.fail("limit", f"Ожидалось 3, получено {len(limited.get('messages', []))}")

        if limited.get("total") == 6:
            results.ok("total отражает все сообщения")
        else:
            results.fail("total после добавления", f"Ожидалось 6, получено {limited.get('total')}")

        # ═══ Тест 6: get_last_messages ═══
        print("\n6. get_last_messages")
        last = get_last_messages(test_agent, count=2)
        if len(last) == 2:
            results.ok("get_last_messages возвращает нужное кол-во")
        else:
            results.fail("get_last_messages", f"Ожидалось 2, получено {len(last)}")

        # ═══ Тест 7: search_history ═══
        print("\n7. search_history")
        # Добавим сообщение с уникальным текстом
        save_message(test_agent, "Уникальный запрос XYZ123", "Ответ на XYZ123", "claude")

        found = search_history(test_agent, "XYZ123")
        if len(found) == 1:
            results.ok("search_history находит по точному совпадению")
        else:
            results.fail("search_history", f"Ожидалось 1, найдено {len(found)}")

        not_found = search_history(test_agent, "НЕСУЩЕСТВУЮЩИЙ_ТЕКСТ_999")
        if len(not_found) == 0:
            results.ok("search_history не находит несуществующий текст")
        else:
            results.fail("search_history false positive", f"Найдено {len(not_found)} вместо 0")

        # ═══ Тест 8: clear_history ═══
        print("\n8. clear_history")
        clear_result = clear_history(test_agent)

        if clear_result.get("status") == "cleared":
            results.ok("clear_history возвращает status=cleared")
        else:
            results.fail("clear_history status", f"Получено: {clear_result.get('status')}")

        if clear_result.get("deleted_count") == 7:  # 6 + 1 уникальный
            results.ok("clear_history возвращает правильный deleted_count")
        else:
            results.fail("deleted_count", f"Ожидалось 7, получено {clear_result.get('deleted_count')}")

        # Проверяем, что история пуста
        after_clear = get_history(test_agent)
        if after_clear.get("total") == 0:
            results.ok("История пуста после clear_history")
        else:
            results.fail("История после очистки", f"total={after_clear.get('total')}")

        # ═══ Тест 9: FIFO (максимум 500 сообщений) ═══
        print("\n9. FIFO (лимит MAX_HISTORY_SIZE)")
        # Добавим MAX_HISTORY_SIZE + 10 сообщений
        for i in range(MAX_HISTORY_SIZE + 10):
            save_message(test_agent, f"Bulk {i}", f"Result {i}", "claude")

        fifo_history = get_history(test_agent, limit=9999)
        if len(fifo_history.get("messages", [])) == MAX_HISTORY_SIZE:
            results.ok(f"FIFO ограничивает историю до {MAX_HISTORY_SIZE} сообщений")
        else:
            results.fail("FIFO", f"Ожидалось {MAX_HISTORY_SIZE}, получено {len(fifo_history.get('messages', []))}")

        # Проверяем, что самое старое сообщение удалено (Bulk 0-9 должны быть удалены)
        messages = fifo_history.get("messages", [])
        if messages and "Bulk 10" in messages[0].get("prompt", ""):
            results.ok("FIFO удаляет самые старые сообщения")
        else:
            first_prompt = messages[0].get("prompt", "") if messages else "пусто"
            results.fail("FIFO порядок", f"Первое сообщение: {first_prompt}")

        # ═══ Тест 10: Атомарная запись ═══
        print("\n10. Атомарная запись (проверка целостности файла)")
        # Читаем файл напрямую и проверяем JSON
        try:
            content = history_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list):
                results.ok("Файл содержит валидный JSON (список)")
            else:
                results.fail("JSON формат", f"Ожидался список, получен {type(data)}")
        except json.JSONDecodeError as e:
            results.fail("JSON парсинг", str(e))

        # ═══ Тест 11: Работа без tayfa_dir ═══
        print("\n11. Работа без установленного tayfa_dir")
        set_tayfa_dir(None)
        null_msg = save_message("any_agent", "test", "test", "claude")
        if null_msg is None:
            results.ok("save_message возвращает None без tayfa_dir")
        else:
            results.fail("save_message без tayfa_dir", f"Вернул: {null_msg}")

        null_history = get_history("any_agent")
        if null_history.get("messages") == [] and null_history.get("total") == 0:
            results.ok("get_history возвращает пустой результат без tayfa_dir")
        else:
            results.fail("get_history без tayfa_dir", f"Вернул: {null_history}")

    return results.summary()


def test_integration_with_app():
    """Проверка интеграции с app.py (статический анализ)"""
    print("\n" + "="*50)
    print("Интеграция с app.py (статический анализ)")
    print("="*50)

    results = TestResults()

    app_path = Path(__file__).parent.parent / "kok" / "app.py"
    if not app_path.exists():
        results.fail("app.py", "Файл не найден")
        return results.summary()

    app_content = app_path.read_text(encoding="utf-8")

    # Проверяем импорты
    print("\n1. Проверка импортов")
    if "from chat_history_manager import" in app_content:
        results.ok("chat_history_manager импортирован")
    else:
        results.fail("Импорт", "chat_history_manager не импортирован")

    # Проверяем API эндпоинты
    print("\n2. Проверка API эндпоинтов")
    if 'def api_get_chat_history' in app_content and '@app.get("/api/chat-history/{agent_name}")' in app_content:
        results.ok("GET /api/chat-history/{agent_name} определён")
    else:
        results.fail("GET chat-history", "Эндпоинт не найден")

    if 'def api_clear_chat_history' in app_content and '/api/chat-history/{agent_name}/clear' in app_content:
        results.ok("POST /api/chat-history/{agent_name}/clear определён")
    else:
        results.fail("POST clear", "Эндпоинт не найден")

    # Проверяем вызов save_chat_message
    print("\n3. Проверка сохранения истории")
    if "save_chat_message(" in app_content:
        # Проверяем, что вызывается в send_prompt, send_prompt_cursor и api_trigger_task
        count = app_content.count("save_chat_message(")
        if count >= 3:
            results.ok(f"save_chat_message вызывается {count} раз (ожидается >= 3)")
        else:
            results.fail("save_chat_message вызовы", f"Найдено {count} вызовов, ожидается >= 3")
    else:
        results.fail("save_chat_message", "Функция не используется")

    # Проверяем set_chat_history_tayfa_dir
    print("\n4. Проверка инициализации tayfa_dir")
    if "set_chat_history_tayfa_dir" in app_content:
        results.ok("set_chat_history_tayfa_dir используется для инициализации")
    else:
        results.fail("set_chat_history_tayfa_dir", "Не найден вызов инициализации")

    return results.summary()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  ТЕСТИРОВАНИЕ: T002 — Хранение истории переписки (backend)")
    print("="*60)

    test1_ok = test_chat_history()
    test2_ok = test_integration_with_app()

    print("\n" + "="*60)
    if test1_ok and test2_ok:
        print("  ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО")
        exit_code = 0
    else:
        print("  ❌ ЕСТЬ ОШИБКИ")
        exit_code = 1
    print("="*60 + "\n")

    sys.exit(exit_code)

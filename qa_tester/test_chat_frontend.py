#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для T003: Отображение истории переписки (frontend)

Статический анализ index.html на наличие требуемых компонентов.
"""

import re
import sys
from pathlib import Path


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


def test_frontend():
    """Проверка frontend компонентов для истории чата"""
    results = TestResults()

    index_path = Path(__file__).parent.parent / "kok" / "static" / "index.html"
    if not index_path.exists():
        results.fail("index.html", "Файл не найден")
        return results.summary()

    content = index_path.read_text(encoding="utf-8")

    # ═══ 1. CSS стили для чата ═══
    print("\n1. CSS стили для чата")

    # Проверяем .message.user и .message.agent
    if ".message.user" in content and "align-self: flex-end" in content:
        results.ok(".message.user — пользователь справа (flex-end)")
    else:
        results.fail(".message.user", "Не найден стиль или неправильное выравнивание")

    if ".message.agent" in content and "align-self: flex-start" in content:
        results.ok(".message.agent — агент слева (flex-start)")
    else:
        results.fail(".message.agent", "Не найден стиль или неправильное выравнивание")

    # Проверяем .chat-loading
    if ".chat-loading" in content and "chat-loading-spinner" in content:
        results.ok(".chat-loading — индикатор загрузки есть")
    else:
        results.fail(".chat-loading", "Индикатор загрузки не найден")

    # Проверяем .chat-empty
    if ".chat-empty" in content:
        results.ok(".chat-empty — пустое состояние есть")
    else:
        results.fail(".chat-empty", "Стиль пустого состояния не найден")

    # Проверяем стили bubbles (border-radius для user/agent)
    if "border-bottom-right-radius: 2px" in content:
        results.ok(".message.user — bubble shape (border-bottom-right-radius)")
    else:
        results.fail(".message.user bubble", "Не найден border-radius для bubble")

    if "border-bottom-left-radius: 2px" in content:
        results.ok(".message.agent — bubble shape (border-bottom-left-radius)")
    else:
        results.fail(".message.agent bubble", "Не найден border-radius для bubble")

    # Проверяем метаданные
    if ".message .meta" in content:
        results.ok(".message .meta — стили для метаданных")
    else:
        results.fail(".message .meta", "Стили метаданных не найдены")

    # ═══ 2. JavaScript функции ═══
    print("\n2. JavaScript функции")

    # loadChatHistory
    if "async function loadChatHistory(agentName)" in content:
        results.ok("loadChatHistory() — async функция определена")
    else:
        results.fail("loadChatHistory", "Функция не найдена или не async")

    # Проверяем вызов API в loadChatHistory
    if "/api/chat-history/" in content and "limit=50" in content:
        results.ok("loadChatHistory — вызов API /api/chat-history/{agent}?limit=50")
    else:
        results.fail("loadChatHistory API", "Вызов API не найден")

    # selectAgent — async
    if "async function selectAgent(name)" in content:
        results.ok("selectAgent() — async функция")
    else:
        results.fail("selectAgent", "Функция не async или не найдена")

    # selectAgent вызывает loadChatHistory
    select_agent_match = re.search(
        r"async function selectAgent\(name\).*?await loadChatHistory\(name\)",
        content,
        re.DOTALL
    )
    if select_agent_match:
        results.ok("selectAgent() — вызывает loadChatHistory()")
    else:
        results.fail("selectAgent -> loadChatHistory", "selectAgent не вызывает loadChatHistory")

    # formatChatTime
    if "function formatChatTime(isoString)" in content:
        results.ok("formatChatTime() — функция форматирования времени")
    else:
        results.fail("formatChatTime", "Функция не найдена")

    # buildChatMeta
    if "function buildChatMeta(msg)" in content:
        results.ok("buildChatMeta() — функция построения метаданных")
    else:
        results.fail("buildChatMeta", "Функция не найдена")

    # Проверяем содержимое buildChatMeta
    if all(x in content for x in ["msg.runtime", "msg.cost_usd", "msg.duration_sec", "msg.task_id"]):
        results.ok("buildChatMeta — включает runtime, cost_usd, duration_sec, task_id")
    else:
        results.fail("buildChatMeta содержимое", "Не все поля включены")

    # clearChatHistory
    if "async function clearChatHistory()" in content:
        results.ok("clearChatHistory() — async функция определена")
    else:
        results.fail("clearChatHistory", "Функция не найдена")

    # clearChatHistory вызывает API
    if '/api/chat-history/${currentAgent}/clear' in content:
        results.ok("clearChatHistory — вызов API /api/chat-history/{agent}/clear")
    else:
        results.fail("clearChatHistory API", "Вызов API очистки не найден")

    # renderChat
    if "function renderChat()" in content:
        results.ok("renderChat() — функция рендеринга")
    else:
        results.fail("renderChat", "Функция не найдена")

    # ═══ 3. HTML структура ═══
    print("\n3. HTML структура")

    # Кнопка очистки истории
    if 'onclick="clearChatHistory()"' in content:
        results.ok("Кнопка очистки истории — onclick=clearChatHistory()")
    else:
        results.fail("Кнопка очистки", "onclick=clearChatHistory() не найден")

    if "Очистить историю" in content:
        results.ok("Кнопка очистки — текст 'Очистить историю'")
    else:
        results.fail("Текст кнопки", "'Очистить историю' не найден")

    # chatArea
    if 'id="chatArea"' in content and 'class="chat-area"' in content:
        results.ok("chatArea — контейнер для сообщений")
    else:
        results.fail("chatArea", "Контейнер не найден")

    # chatScreen
    if 'id="chatScreen"' in content:
        results.ok("chatScreen — экран чата")
    else:
        results.fail("chatScreen", "Экран чата не найден")

    # ═══ 4. Логика отображения сообщений ═══
    print("\n4. Логика отображения сообщений")

    # Проверяем разделение prompt/result
    if "msg.prompt" in content and "type: 'user'" in content:
        results.ok("Промпты отображаются как 'user'")
    else:
        results.fail("Промпты user", "Логика не найдена")

    if "msg.result" in content and "type: msg.success === false ? 'error' : 'agent'" in content:
        results.ok("Результаты — 'agent' или 'error' в зависимости от success")
    else:
        results.fail("Результаты agent/error", "Логика не найдена")

    # Индикатор загрузки в loadChatHistory
    if "chat-loading-spinner" in content and "Загрузка истории" in content:
        results.ok("Индикатор загрузки в loadChatHistory (spinner + текст)")
    else:
        results.fail("Индикатор загрузки", "Spinner или текст не найдены")

    # Пустое состояние
    if 'class="chat-empty"' in content and "История пуста" in content:
        results.ok("Пустое состояние — 'История пуста'")
    else:
        results.fail("Пустое состояние", "Текст 'История пуста' не найден")

    # ═══ 5. Форматирование времени ═══
    print("\n5. Форматирование времени")

    if "toLocaleTimeString" in content and "hour: '2-digit'" in content:
        results.ok("formatChatTime — использует toLocaleTimeString (HH:MM)")
    else:
        results.fail("formatChatTime формат", "toLocaleTimeString не найден")

    return results.summary()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  ТЕСТИРОВАНИЕ: T003 — Отображение истории переписки (frontend)")
    print("="*60)

    success = test_frontend()

    print("\n" + "="*60)
    if success:
        print("  ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО")
        exit_code = 0
    else:
        print("  ❌ ЕСТЬ ОШИБКИ")
        exit_code = 1
    print("="*60 + "\n")

    sys.exit(exit_code)

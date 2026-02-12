#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для T006: Авто-релиз в GitHub при завершении спринта

Статический анализ index.html и app.py на наличие требуемых компонентов.
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
    """Проверка frontend компонентов для авто-релиза"""
    results = TestResults()

    index_path = Path(__file__).parent.parent / "kok" / "static" / "index.html"
    if not index_path.exists():
        results.fail("index.html", "Файл не найден")
        return results.summary()

    content = index_path.read_text(encoding="utf-8")

    # ═══ 1. CSS стили ═══
    print("\n1. CSS стили")

    if ".btn.success" in content and "background: var(--success)" in content:
        results.ok(".btn.success — зелёная кнопка определена")
    else:
        results.fail(".btn.success", "Стиль не найден")

    if ".btn.success:hover" in content:
        results.ok(".btn.success:hover — hover эффект")
    else:
        results.fail(".btn.success:hover", "Hover стиль не найден")

    # ═══ 2. renderSprintToolbar() ═══
    print("\n2. renderSprintToolbar()")

    if "function renderSprintToolbar(sprint, sprintTasks)" in content:
        results.ok("renderSprintToolbar() — функция определена")
    else:
        results.fail("renderSprintToolbar", "Функция не найдена")

    # Проверяем логику: allDone && sprint.status === 'завершён'
    if "allDone && sprint.status === 'завершён'" in content:
        results.ok("renderSprintToolbar — проверка завершённого спринта")
    else:
        results.fail("renderSprintToolbar", "Логика проверки завершённого спринта не найдена")

    # Проверяем показ "Релиз vX.Y.Z выпущен"
    if "✓ Релиз" in content and "выпущен" in content:
        results.ok("renderSprintToolbar — показ 'Релиз vX.Y.Z выпущен'")
    else:
        results.fail("renderSprintToolbar", "Текст 'Релиз выпущен' не найден")

    # Проверяем кнопку "Выпустить релиз"
    if "🚀 Выпустить релиз" in content:
        results.ok("renderSprintToolbar — кнопка '🚀 Выпустить релиз'")
    else:
        results.fail("renderSprintToolbar", "Кнопка 'Выпустить релиз' не найдена")

    # Проверяем вызов showReleaseModal
    if "showReleaseModal('" in content:
        results.ok("renderSprintToolbar — вызов showReleaseModal()")
    else:
        results.fail("renderSprintToolbar", "Вызов showReleaseModal не найден")

    # ═══ 3. showReleaseModal() ═══
    print("\n3. showReleaseModal()")

    if "async function showReleaseModal(sprintId)" in content:
        results.ok("showReleaseModal() — async функция определена")
    else:
        results.fail("showReleaseModal", "Функция не найдена")

    # Проверяем вызов API release-ready
    if "/api/sprints/${sprintId}/release-ready" in content:
        results.ok("showReleaseModal — вызов GET /api/sprints/{id}/release-ready")
    else:
        results.fail("showReleaseModal", "API release-ready не вызывается")

    # Проверяем проверку ready
    if "releaseInfo.ready" in content:
        results.ok("showReleaseModal — проверка releaseInfo.ready")
    else:
        results.fail("showReleaseModal", "Проверка ready не найдена")

    # Проверяем индикатор загрузки
    if "Проверка готовности к релизу" in content:
        results.ok("showReleaseModal — индикатор 'Проверка готовности...'")
    else:
        results.fail("showReleaseModal", "Индикатор загрузки не найден")

    # Проверяем поле ввода версии
    if 'id="releaseVersion"' in content:
        results.ok("showReleaseModal — поле ввода версии (releaseVersion)")
    else:
        results.fail("showReleaseModal", "Поле ввода версии не найдено")

    # Проверяем информацию о спринте
    if "Спринт" in content and "Выполнено задач" in content:
        results.ok("showReleaseModal — информация о спринте и задачах")
    else:
        results.fail("showReleaseModal", "Информация о спринте не отображается")

    # Проверяем кнопку выпустить в модале
    if 'onclick="executeRelease(' in content:
        results.ok("showReleaseModal — кнопка 'Выпустить' вызывает executeRelease()")
    else:
        results.fail("showReleaseModal", "Кнопка executeRelease не найдена")

    # ═══ 4. executeRelease() ═══
    print("\n4. executeRelease()")

    if "async function executeRelease(sprintId)" in content:
        results.ok("executeRelease() — async функция определена")
    else:
        results.fail("executeRelease", "Функция не найдена")

    # Проверяем вызов API /api/git/release
    if "/api/git/release" in content:
        results.ok("executeRelease — вызов POST /api/git/release")
    else:
        results.fail("executeRelease", "API /api/git/release не вызывается")

    # Проверяем передачу sprint_id и version
    if "sprint_id: sprintId" in content and "version:" in content:
        results.ok("executeRelease — передаёт sprint_id и version")
    else:
        results.fail("executeRelease", "Параметры sprint_id/version не передаются")

    # Проверяем индикатор загрузки
    if "Создание релиза" in content:
        results.ok("executeRelease — индикатор 'Создание релиза...'")
    else:
        results.fail("executeRelease", "Индикатор загрузки не найден")

    # Проверяем показ результата
    if "result.version" in content and "result.commit" in content:
        results.ok("executeRelease — показ версии и коммита")
    else:
        results.fail("executeRelease", "Показ результата не найден")

    # Проверяем обновление UI после релиза
    if "refreshTasksBoardNew()" in content and "loadSprints()" in content:
        results.ok("executeRelease — обновление UI (refreshTasksBoardNew, loadSprints)")
    else:
        results.fail("executeRelease", "Обновление UI не найдено")

    if "loadGitStatus()" in content:
        results.ok("executeRelease — обновление git статуса (loadGitStatus)")
    else:
        results.fail("executeRelease", "loadGitStatus не вызывается")

    return results.summary()


def test_backend_api():
    """Проверка backend API для релиза"""
    results = TestResults()

    app_path = Path(__file__).parent.parent / "kok" / "app.py"
    if not app_path.exists():
        results.fail("app.py", "Файл не найден")
        return results.summary()

    content = app_path.read_text(encoding="utf-8")

    # ═══ 5. Backend API ═══
    print("\n5. Backend API")

    # POST /api/git/release
    if '@app.post("/api/git/release")' in content:
        results.ok("POST /api/git/release — endpoint определён")
    else:
        results.fail("POST /api/git/release", "Endpoint не найден")

    # GET /api/sprints/{sprint_id}/release-ready
    if '/api/sprints/{sprint_id}/release-ready' in content:
        results.ok("GET /api/sprints/{id}/release-ready — endpoint определён")
    else:
        results.fail("GET release-ready", "Endpoint не найден")

    # Проверяем логику release (merge, tag, push)
    if 'git merge' in content.lower() or '"merge"' in content:
        results.ok("api_git_release — выполняет merge")
    else:
        results.fail("api_git_release", "Merge не найден")

    if '"tag"' in content or 'git tag' in content.lower():
        results.ok("api_git_release — создаёт tag")
    else:
        results.fail("api_git_release", "Tag не найден")

    if '"push"' in content or 'git push' in content.lower():
        results.ok("api_git_release — выполняет push")
    else:
        results.fail("api_git_release", "Push не найден")

    # Проверяем сохранение версии в спринт
    if "sprint['version']" in content or 'sprint["version"]' in content:
        results.ok("api_git_release — сохраняет версию в спринт")
    else:
        results.fail("api_git_release", "Сохранение версии не найдено")

    return results.summary()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  ТЕСТИРОВАНИЕ: T006 — Авто-релиз в GitHub при завершении спринта")
    print("="*60)

    test1_ok = test_frontend()
    test2_ok = test_backend_api()

    print("\n" + "="*60)
    if test1_ok and test2_ok:
        print("  ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО")
        exit_code = 0
    else:
        print("  ❌ ЕСТЬ ОШИБКИ")
        exit_code = 1
    print("="*60 + "\n")

    sys.exit(exit_code)

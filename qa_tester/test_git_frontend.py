#!/usr/bin/env python3
"""
Тестирование Git Frontend (T004)
QA-тестировщик: статический анализ HTML/JS кода
"""

import re
import sys
from pathlib import Path

results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def test_passed(name, details=""):
    results["passed"].append({"name": name, "details": details})
    print(f"✅ PASS: {name}")
    if details:
        print(f"   {details}")

def test_failed(name, details=""):
    results["failed"].append({"name": name, "details": details})
    print(f"❌ FAIL: {name}")
    if details:
        print(f"   {details}")

def test_warning(name, details=""):
    results["warnings"].append({"name": name, "details": details})
    print(f"⚠️  WARN: {name}")
    if details:
        print(f"   {details}")


def analyze_git_panel():
    """Анализ Git-панели в интерфейсе"""
    print("\n=== Анализ Git-панели (index.html) ===")

    html_path = Path(__file__).parent.parent / "kok" / "static" / "index.html"
    if not html_path.exists():
        test_failed("index.html не найден", str(html_path))
        return False

    code = html_path.read_text(encoding="utf-8")

    # ═══════════════════════════════════════════════════════════════════
    # ТРЕБОВАНИЕ 1: Панель статуса — текущая ветка, изменённые файлы
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- Требование 1: Панель статуса ---")

    # 1.1 Функция renderGitSection
    if "function renderGitSection(data)" in code:
        test_passed("renderGitSection() определена")
    else:
        test_failed("renderGitSection() не найдена")

    # 1.2 Отображение ветки
    if "git-branch-name" in code and "data.branch" in code:
        test_passed("Отображение текущей ветки реализовано")
    else:
        test_failed("Отображение ветки не найдено")

    # 1.3 Отображение staged файлов
    if "stagedCount" in code and "staged" in code:
        test_passed("Подсчёт staged файлов")
    else:
        test_failed("Подсчёт staged не найден")

    # 1.4 Отображение unstaged (modified)
    if "unstagedCount" in code and "unstaged" in code:
        test_passed("Подсчёт unstaged/modified файлов")
    else:
        test_failed("Подсчёт unstaged не найден")

    # 1.5 Отображение untracked
    if "untrackedCount" in code and "untracked" in code:
        test_passed("Подсчёт untracked файлов")
    else:
        test_failed("Подсчёт untracked не найден")

    # 1.6 CSS класс для untracked
    if ".git-changes .untracked" in code:
        test_passed("CSS стиль для untracked")
    else:
        test_warning("CSS стиль для untracked не найден")

    # 1.7 Индикатор clean/dirty
    if "git-status-dot" in code and "isClean" in code:
        test_passed("Индикатор clean/dirty статуса")
    else:
        test_warning("Индикатор clean/dirty не найден")

    # ═══════════════════════════════════════════════════════════════════
    # ТРЕБОВАНИЕ 2: Форма коммита — выбор файлов, commit message, кнопка
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- Требование 2: Форма коммита ---")

    # 2.1 Функция showGitCommitModal
    if "async function showGitCommitModal()" in code:
        test_passed("showGitCommitModal() определена")
    else:
        test_failed("showGitCommitModal() не найдена")

    # 2.2 Поле commit message
    if 'id="commitMessage"' in code:
        test_passed("Поле commitMessage существует")
    else:
        test_failed("Поле commitMessage не найдено")

    # 2.3 Выбор файлов (чекбоксы)
    if 'name="commitFiles"' in code and 'type="checkbox"' in code:
        test_passed("Чекбоксы для выбора файлов")
    else:
        test_failed("Чекбоксы для файлов не найдены")

    # 2.4 Кнопка Commit
    if "submitGitCommit()" in code and "Commit" in code:
        test_passed("Кнопка Commit с submitGitCommit()")
    else:
        test_failed("Кнопка Commit не найдена")

    # 2.5 Отправка POST /api/git/commit
    if "/api/git/commit" in code and "message:" in code and "files:" in code:
        test_passed("Интеграция с POST /api/git/commit")
    else:
        test_failed("Интеграция с /api/git/commit не найдена")

    # 2.6 Conventional commits (feat, fix, etc.)
    if 'id="commitType"' in code and "feat" in code and "fix" in code:
        test_passed("Conventional Commits (feat/fix/...)")
    else:
        test_warning("Conventional Commits не реализованы")

    # 2.7 Отображение untracked в модалке
    if 'Untracked' in code and 'untracked.map' in code:
        test_passed("Секция Untracked в модалке коммита")
    else:
        test_warning("Секция Untracked в модалке не найдена")

    # 2.8 renderCommitFileItem принимает строки
    if "function renderCommitFileItem(file" in code:
        test_passed("renderCommitFileItem() определена")
        # Проверяем что работает со строками
        if "typeof file === 'string'" in code:
            test_passed("renderCommitFileItem() поддерживает строки")
        else:
            test_warning("renderCommitFileItem() может не работать со строками")
    else:
        test_failed("renderCommitFileItem() не найдена")

    # ═══════════════════════════════════════════════════════════════════
    # ТРЕБОВАНИЕ 3: История коммитов — последние 20 коммитов
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- Требование 3: История коммитов ---")

    # 3.1 Функция loadGitHistory
    if "async function loadGitHistory()" in code:
        test_passed("loadGitHistory() определена")
    else:
        test_failed("loadGitHistory() не найдена")

    # 3.2 limit=20 в запросе
    if "/api/git/log?limit=20" in code:
        test_passed("История запрашивает 20 коммитов")
    else:
        # Проверим альтернативные варианты
        if "limit=20" in code or "limit: 20" in code:
            test_passed("История запрашивает 20 коммитов (альтернативный синтаксис)")
        else:
            test_failed("limit=20 не найден в запросе git/log")

    # 3.3 Текст "последние 20"
    if "последние 20" in code:
        test_passed("Текст 'История (последние 20)' обновлён")
    else:
        test_warning("Текст 'последние 20' не найден")

    # 3.4 CSS max-height для прокрутки
    if "max-height: 300px" in code or "max-height:300px" in code:
        test_passed("CSS max-height: 300px для истории")
    else:
        test_warning("CSS max-height не найден")

    # 3.5 overflow-y: auto
    if "overflow-y: auto" in code or "overflow-y:auto" in code:
        test_passed("CSS overflow-y: auto для истории")
    else:
        test_warning("CSS overflow-y: auto не найден")

    # 3.6 Отображение коммитов (hash, message, date)
    if "git-commit-hash" in code and "git-commit-msg" in code and "git-commit-time" in code:
        test_passed("Элементы коммита (hash, msg, time)")
    else:
        test_warning("Элементы коммита неполные")

    # 3.7 Сворачиваемая история
    if "toggleGitHistory()" in code and "gitHistoryExpanded" in code:
        test_passed("Сворачиваемая история (toggle)")
    else:
        test_warning("Сворачивание истории не найдено")

    # ═══════════════════════════════════════════════════════════════════
    # ТРЕБОВАНИЕ 4: Кнопка Init Git — если не инициализирован
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- Требование 4: Кнопка Init Git ---")

    # 4.1 Функция renderGitUnavailable
    if "function renderGitUnavailable(" in code:
        test_passed("renderGitUnavailable() определена")
    else:
        test_failed("renderGitUnavailable() не найдена")

    # 4.2 Кнопка инициализации в renderGitUnavailable
    if "initGitRepo()" in code and "Инициализировать Git" in code:
        test_passed("Кнопка 'Инициализировать Git' существует")
    else:
        test_failed("Кнопка инициализации не найдена")

    # 4.3 Функция initGitRepo
    if "async function initGitRepo()" in code:
        test_passed("initGitRepo() определена")
    else:
        test_failed("initGitRepo() не найдена")

    # 4.4 POST /api/git/init с create_gitignore
    if "/api/git/init" in code and "create_gitignore" in code:
        test_passed("POST /api/git/init с create_gitignore=true")
    else:
        test_failed("/api/git/init с create_gitignore не найден")

    # 4.5 Обновление после инициализации
    if "loadGitStatus()" in code:
        test_passed("loadGitStatus() вызывается после init")
    else:
        test_warning("Обновление после init не найдено")

    # ═══════════════════════════════════════════════════════════════════
    # ТРЕБОВАНИЕ 5: Интеграция с существующим дизайном
    # ═══════════════════════════════════════════════════════════════════
    print("\n--- Требование 5: Интеграция с дизайном ---")

    # 5.1 CSS переменные используются
    css_vars = ["var(--success)", "var(--warning)", "var(--text-dim)", "var(--accent)", "var(--border)"]
    css_vars_found = sum(1 for v in css_vars if v in code)
    if css_vars_found >= 4:
        test_passed(f"CSS переменные используются ({css_vars_found}/5)")
    else:
        test_warning(f"Мало CSS переменных ({css_vars_found}/5)")

    # 5.2 Класс .btn используется
    if 'class="btn' in code and 'class="btn primary"' in code:
        test_passed("Стандартные классы .btn используются")
    else:
        test_warning("Классы .btn могут не использоваться")

    # 5.3 escapeHtml используется для XSS-защиты
    escape_count = code.count("escapeHtml(")
    if escape_count >= 5:
        test_passed(f"escapeHtml() используется ({escape_count} раз)")
    else:
        test_warning(f"escapeHtml() используется мало ({escape_count} раз)")

    # 5.4 openModal/closeModal для модалки
    if "openModal(" in code and "closeModal()" in code:
        test_passed("Стандартные openModal/closeModal используются")
    else:
        test_warning("openModal/closeModal не найдены")

    # 5.5 showNotification для уведомлений
    if "showNotification(" in code:
        test_passed("showNotification() для уведомлений")
    else:
        test_warning("showNotification() не найден")

    return True


def check_api_integration():
    """Проверка интеграции с API"""
    print("\n=== Проверка интеграции с Git API ===")

    html_path = Path(__file__).parent.parent / "kok" / "static" / "index.html"
    code = html_path.read_text(encoding="utf-8")

    api_endpoints = [
        ("/api/git/status", "GET", "loadGitStatus"),
        ("/api/git/init", "POST", "initGitRepo"),
        ("/api/git/log", "GET", "loadGitHistory"),
        ("/api/git/commit", "POST", "submitGitCommit"),
        ("/api/git/branches", "GET", "showGitPRModal"),
        ("/api/git/push", "POST", "gitPush"),
    ]

    for endpoint, method, func in api_endpoints:
        if endpoint in code:
            test_passed(f"Интеграция {method} {endpoint}")
        else:
            test_warning(f"Эндпоинт {endpoint} не используется")


def print_summary():
    """Вывод итогов тестирования"""
    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ Git Frontend (T004)")
    print("=" * 60)

    print(f"\n✅ Пройдено: {len(results['passed'])}")
    print(f"❌ Провалено: {len(results['failed'])}")
    print(f"⚠️  Предупреждений: {len(results['warnings'])}")

    if results['failed']:
        print("\n--- ПРОВАЛЕННЫЕ ТЕСТЫ ---")
        for t in results['failed']:
            print(f"  • {t['name']}: {t['details']}")

    if results['warnings']:
        print("\n--- ПРЕДУПРЕЖДЕНИЯ ---")
        for t in results['warnings']:
            print(f"  • {t['name']}: {t['details']}")

    print("\n" + "=" * 60)
    if len(results['failed']) == 0:
        print("✅ ВЕРДИКТ: ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        return True
    else:
        print(f"❌ ВЕРДИКТ: ЕСТЬ ОШИБКИ ({len(results['failed'])} тестов провалено)")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("QA-ТЕСТИРОВАНИЕ: Git Frontend (T004)")
    print("=" * 60)

    analyze_git_panel()
    check_api_integration()

    success = print_summary()
    sys.exit(0 if success else 1)

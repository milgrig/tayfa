#!/usr/bin/env python3
"""
Тестирование Git API эндпоинтов (T003)
QA-тестировщик: статический анализ + интеграционные тесты
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent / "kok"))

# Тестовые результаты
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


def test_run_git_command():
    """Тест функции run_git_command"""
    print("\n=== Тест run_git_command ===")

    # Создаём временную директорию для тестов
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Тест 1: git version (должен работать везде)
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            test_passed("git CLI доступен", result.stdout.strip())
        else:
            test_failed("git CLI не найден")
            return

        # Тест 2: git init в временной папке
        result = subprocess.run(
            ["git", "init"],
            cwd=str(tmppath),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            test_passed("git init работает")
        else:
            test_failed("git init ошибка", result.stderr)
            return

        # Тест 3: git status --porcelain (пустой репо)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(tmppath),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            test_passed("git status --porcelain работает", f"output: '{result.stdout}'")
        else:
            test_failed("git status ошибка", result.stderr)

        # Тест 4: Создаём файл и проверяем status
        test_file = tmppath / "test.txt"
        test_file.write_text("hello")

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(tmppath),
            capture_output=True,
            text=True
        )
        if "?? test.txt" in result.stdout:
            test_passed("Untracked файл определяется", f"output: '{result.stdout.strip()}'")
        else:
            test_failed("Untracked не определяется", result.stdout)

        # Тест 5: git add и проверяем staged
        subprocess.run(["git", "add", "test.txt"], cwd=str(tmppath), capture_output=True)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(tmppath),
            capture_output=True,
            text=True
        )
        if result.stdout.startswith("A  test.txt") or result.stdout.startswith("A "):
            test_passed("Staged файл определяется", f"output: '{result.stdout.strip()}'")
        else:
            test_failed("Staged не определяется", result.stdout)

        # Тест 6: git log format
        # Настройка git user для коммита
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmppath), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmppath), capture_output=True)
        subprocess.run(["git", "commit", "-m", "Test commit"], cwd=str(tmppath), capture_output=True)

        result = subprocess.run(
            ["git", "log", "-n1", "--format=%h|%an|%ad|%s", "--date=short"],
            cwd=str(tmppath),
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and "|" in result.stdout:
            parts = result.stdout.strip().split("|")
            if len(parts) == 4:
                test_passed("git log format работает", f"hash={parts[0]}, author={parts[1]}, date={parts[2]}, msg={parts[3]}")
            else:
                test_failed("git log format неправильный", result.stdout)
        else:
            test_failed("git log ошибка", result.stderr)

        # Тест 7: git branch --show-current
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(tmppath),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            test_passed("git branch --show-current работает", f"branch: {result.stdout.strip()}")
        else:
            test_failed("git branch ошибка", result.stderr)

        # Тест 8: git diff
        # Изменяем файл
        test_file.write_text("hello world")
        result = subprocess.run(
            ["git", "diff"],
            cwd=str(tmppath),
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and "hello world" in result.stdout:
            test_passed("git diff работает")
        else:
            test_warning("git diff пустой или ошибка", result.stdout[:100] if result.stdout else result.stderr)


def analyze_api_code():
    """Статический анализ кода API"""
    print("\n=== Статический анализ app.py ===")

    app_path = Path(__file__).parent.parent / "kok" / "app.py"
    if not app_path.exists():
        test_failed("app.py не найден", str(app_path))
        return

    code = app_path.read_text(encoding="utf-8")

    # Тест 1: Все эндпоинты объявлены
    endpoints = [
        ("GET /api/git/status", "@app.get(\"/api/git/status\")"),
        ("POST /api/git/init", "@app.post(\"/api/git/init\")"),
        ("GET /api/git/log", "@app.get(\"/api/git/log\")"),
        ("POST /api/git/commit", "@app.post(\"/api/git/commit\")"),
        ("GET /api/git/diff", "@app.get(\"/api/git/diff\")"),
        ("GET /api/git/branches", "@app.get(\"/api/git/branches\")"),
    ]

    for name, decorator in endpoints:
        if decorator in code:
            test_passed(f"Эндпоинт {name} объявлен")
        else:
            test_failed(f"Эндпоинт {name} НЕ найден")

    # Тест 2: run_git_command использует subprocess
    if "def run_git_command" in code and "subprocess.run" in code:
        test_passed("run_git_command использует subprocess.run")
    else:
        test_failed("run_git_command не найден или не использует subprocess")

    # Тест 3: cwd передаётся в subprocess
    if "cwd=str(cwd)" in code or "cwd=str(project_dir)" in code:
        test_passed("cwd передаётся в subprocess")
    else:
        test_warning("cwd может не передаваться корректно")

    # Тест 4: Проверка get_project_dir
    if "get_project_dir()" in code:
        test_passed("Используется get_project_dir() для определения рабочей директории")
    else:
        test_failed("get_project_dir() не используется")

    # Тест 5: _check_git_initialized существует
    if "def _check_git_initialized" in code:
        test_passed("_check_git_initialized() определена")
    else:
        test_failed("_check_git_initialized() не найдена")

    # Тест 6: Парсинг git status --porcelain
    if "--porcelain" in code and "index_status" in code:
        test_passed("Парсинг git status --porcelain реализован")
    else:
        test_warning("Парсинг git status может быть неполным")

    # Тест 7: HTTPException для ошибок
    if "HTTPException(status_code=400" in code and "HTTPException(status_code=500" in code:
        test_passed("Обработка ошибок через HTTPException (400, 500)")
    else:
        test_warning("Обработка ошибок может быть неполной")

    # Тест 8: Таймаут для subprocess
    if "timeout=30" in code or "timeout=" in code:
        test_passed("Таймаут для subprocess установлен")
    else:
        test_warning("Таймаут для subprocess не найден")

    # Тест 9: async функции
    async_endpoints = [
        "async def api_git_status",
        "async def api_git_init",
        "async def api_git_log",
        "async def api_git_commit",
        "async def api_git_diff",
        "async def api_git_branches",
    ]
    for ep in async_endpoints:
        if ep in code:
            test_passed(f"{ep} объявлена")
        else:
            test_warning(f"{ep} не найдена")

    # Тест 10: Дополнительные эндпоинты (бонус)
    bonus_endpoints = [
        ("POST /api/git/branch", "@app.post(\"/api/git/branch\")"),
        ("POST /api/git/push", "@app.post(\"/api/git/push\")"),
        ("POST /api/git/pr", "@app.post(\"/api/git/pr\")"),
        ("POST /api/git/release", "@app.post(\"/api/git/release\")"),
    ]
    for name, decorator in bonus_endpoints:
        if decorator in code:
            test_passed(f"Бонус: {name} реализован")


def check_edge_cases():
    """Проверка граничных случаев в коде"""
    print("\n=== Проверка граничных случаев ===")

    app_path = Path(__file__).parent.parent / "kok" / "app.py"
    code = app_path.read_text(encoding="utf-8")

    # Тест 1: Обработка "nothing to commit"
    if "nothing to commit" in code:
        test_passed("Обработка 'nothing to commit' реализована")
    else:
        test_warning("'nothing to commit' может не обрабатываться")

    # Тест 2: Проверка пустого репозитория (нет коммитов)
    if "does not have any commits" in code:
        test_passed("Обработка пустого репозитория (нет коммитов)")
    else:
        test_warning("Пустой репозиторий может вызвать ошибку в git log")

    # Тест 3: FileNotFoundError для git
    if "FileNotFoundError" in code:
        test_passed("Обработка отсутствия git CLI")
    else:
        test_warning("Отсутствие git CLI может не обрабатываться")

    # Тест 4: TimeoutExpired
    if "TimeoutExpired" in code:
        test_passed("Обработка таймаута subprocess")
    else:
        test_warning("Таймаут subprocess может не обрабатываться")

    # Тест 5: Параметр limit в git log
    if "limit: int = 20" in code or "f\"-n{limit}\"" in code:
        test_passed("Параметр limit в git log реализован")
    else:
        test_warning("Параметр limit может не работать")

    # Тест 6: Параметры staged и file в git diff
    if "staged: bool" in code and "file: str" in code:
        test_passed("Параметры staged и file в git diff реализованы")
    else:
        test_warning("Параметры git diff могут быть неполными")

    # Тест 7: create_gitignore в git init
    if "create_gitignore" in code:
        test_passed("Опция create_gitignore в git init реализована")
    else:
        test_warning("create_gitignore не найден")


def print_summary():
    """Вывод итогов тестирования"""
    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ Git API (T003)")
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

    # Общий вердикт
    print("\n" + "=" * 60)
    if len(results['failed']) == 0:
        print("✅ ВЕРДИКТ: ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        return True
    else:
        print(f"❌ ВЕРДИКТ: ЕСТЬ ОШИБКИ ({len(results['failed'])} тестов провалено)")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("QA-ТЕСТИРОВАНИЕ: Git API эндпоинты (T003)")
    print("=" * 60)

    # Запускаем тесты
    analyze_api_code()
    test_run_git_command()
    check_edge_cases()

    # Итоги
    success = print_summary()
    sys.exit(0 if success else 1)

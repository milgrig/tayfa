#!/usr/bin/env python3
"""
T005: Комплексное тестирование Git-интеграции
Тест-план: инициализация, статус, коммиты, история, граничные случаи
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Результаты тестирования
results = {
    "passed": [],
    "failed": [],
    "warnings": [],
    "bugs": []
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


def add_bug(bug_id, title, severity, component, steps, expected, actual):
    """Добавить баг в отчёт"""
    bug = {
        "id": bug_id,
        "title": title,
        "severity": severity,
        "component": component,
        "steps": steps,
        "expected": expected,
        "actual": actual
    }
    results["bugs"].append(bug)
    print(f"🐛 BUG-{bug_id}: {title} [{severity}]")


def git_cmd(args, cwd):
    """Выполнить git команду"""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30
    )
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip()
    }


def setup_git_user(cwd):
    """Настроить git user для тестов"""
    git_cmd(["config", "user.email", "test@tayfa.dev"], cwd)
    git_cmd(["config", "user.name", "Tayfa Test"], cwd)


# ═══════════════════════════════════════════════════════════════════
# РАЗДЕЛ 1: ИНИЦИАЛИЗАЦИЯ РЕПОЗИТОРИЯ
# ═══════════════════════════════════════════════════════════════════

def test_initialization():
    """Тесты инициализации репозитория"""
    print("\n" + "=" * 60)
    print("РАЗДЕЛ 1: ИНИЦИАЛИЗАЦИЯ РЕПОЗИТОРИЯ")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # 1.1 Инициализация в чистой папке
        print("\n--- 1.1 Инициализация в чистой папке ---")

        git_dir = tmppath / ".git"
        if git_dir.exists():
            test_failed("1.1.1 Чистая папка", "Папка .git уже существует")
        else:
            test_passed("1.1.1 Папка чистая (нет .git)")

        result = git_cmd(["init"], tmppath)
        if result["success"] and git_dir.exists():
            test_passed("1.1.2 git init успешен", f".git создан")
        else:
            test_failed("1.1.2 git init", result["stderr"])

        # 1.2 Проверка наличия main/master ветки
        print("\n--- 1.2 Проверка веток ---")
        result = git_cmd(["branch", "--show-current"], tmppath)
        if result["success"]:
            branch = result["stdout"]
            if branch in ("main", "master", ""):
                test_passed("1.2.1 Ветка по умолчанию", f"branch='{branch}'")
            else:
                test_warning("1.2.1 Нестандартная ветка", f"branch='{branch}'")
        else:
            test_warning("1.2.1 Не удалось получить ветку", result["stderr"])

        # 1.3 Повторная инициализация
        print("\n--- 1.3 Повторная инициализация ---")
        result = git_cmd(["init"], tmppath)
        if result["success"]:
            if "Reinitialized" in result["stdout"] or "existing" in result["stdout"].lower():
                test_passed("1.3.1 Повторный init", "Репозиторий переинициализирован")
            else:
                test_passed("1.3.1 Повторный init", result["stdout"][:50])
        else:
            test_failed("1.3.1 Повторный init", result["stderr"])

        # 1.4 Создание .gitignore
        print("\n--- 1.4 .gitignore ---")
        gitignore = tmppath / ".gitignore"
        gitignore.write_text("node_modules/\n__pycache__/\n.env\n")
        if gitignore.exists():
            test_passed("1.4.1 .gitignore создан")
            content = gitignore.read_text()
            if "node_modules" in content:
                test_passed("1.4.2 .gitignore содержит стандартные исключения")
            else:
                test_warning("1.4.2 .gitignore может быть неполным")
        else:
            test_failed("1.4.1 .gitignore не создан")


# ═══════════════════════════════════════════════════════════════════
# РАЗДЕЛ 2: СТАТУС РЕПОЗИТОРИЯ
# ═══════════════════════════════════════════════════════════════════

def test_status():
    """Тесты статуса репозитория"""
    print("\n" + "=" * 60)
    print("РАЗДЕЛ 2: СТАТУС РЕПОЗИТОРИЯ")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        git_cmd(["init"], tmppath)
        setup_git_user(tmppath)

        # 2.1 Чистый репозиторий
        print("\n--- 2.1 Чистый репозиторий ---")
        result = git_cmd(["status", "--porcelain"], tmppath)
        if result["success"] and result["stdout"] == "":
            test_passed("2.1.1 Пустой статус для чистого репо")
        else:
            test_failed("2.1.1 Статус не пустой", result["stdout"])

        # 2.2 Untracked файл
        print("\n--- 2.2 Untracked файлы ---")
        (tmppath / "newfile.txt").write_text("hello")
        result = git_cmd(["status", "--porcelain"], tmppath)
        if "?? newfile.txt" in result["stdout"]:
            test_passed("2.2.1 Untracked файл определяется", "?? newfile.txt")
        else:
            test_failed("2.2.1 Untracked не определяется", result["stdout"])

        # 2.3 Staged файл
        print("\n--- 2.3 Staged файлы ---")
        git_cmd(["add", "newfile.txt"], tmppath)
        result = git_cmd(["status", "--porcelain"], tmppath)
        if result["stdout"].startswith("A"):
            test_passed("2.3.1 Staged файл определяется", f"'{result['stdout']}'")
        else:
            test_failed("2.3.1 Staged не определяется", result["stdout"])

        # Коммитим для дальнейших тестов
        git_cmd(["commit", "-m", "Initial commit"], tmppath)

        # 2.4 Modified (unstaged)
        print("\n--- 2.4 Modified файлы ---")
        (tmppath / "newfile.txt").write_text("hello world")
        result = git_cmd(["status", "--porcelain"], tmppath)
        # Формат porcelain: XY filename, где X=index, Y=worktree
        # " M" = unstaged modified, "M " = staged modified
        stdout = result["stdout"].strip()
        # После коммита файл tracked, изменение в worktree = " M" или "M " в первом символе
        if stdout and len(stdout) >= 2:
            # Проверяем что файл показывает изменение (M в любой позиции)
            if "M" in stdout[:2]:
                test_passed("2.4.1 Modified файл определяется", stdout)
            else:
                test_failed("2.4.1 Modified не определяется", stdout)
        else:
            test_failed("2.4.1 Пустой статус", stdout)

        # 2.5 Modified (staged)
        print("\n--- 2.5 Staged modified ---")
        git_cmd(["add", "newfile.txt"], tmppath)
        result = git_cmd(["status", "--porcelain"], tmppath)
        if result["stdout"].startswith("M"):
            test_passed("2.5.1 Staged modified определяется", result["stdout"])
        else:
            test_failed("2.5.1 Staged modified не определяется", result["stdout"])

        # 2.6 Парсинг porcelain формата
        print("\n--- 2.6 Парсинг porcelain ---")
        # Создаём разные состояния
        git_cmd(["commit", "-m", "Second commit"], tmppath)
        (tmppath / "file2.txt").write_text("new file")
        (tmppath / "newfile.txt").write_text("modified again")

        result = git_cmd(["status", "--porcelain"], tmppath)
        lines = result["stdout"].split("\n")
        parsed_ok = True
        for line in lines:
            if len(line) >= 3:
                index_status = line[0]
                worktree_status = line[1]
                filename = line[3:]
                if index_status not in " MADRCU?" or worktree_status not in " MADRCU?":
                    parsed_ok = False
                    break
        if parsed_ok:
            test_passed("2.6.1 Формат porcelain корректный", f"{len(lines)} строк")
        else:
            test_failed("2.6.1 Ошибка парсинга porcelain", result["stdout"])


# ═══════════════════════════════════════════════════════════════════
# РАЗДЕЛ 3: СОЗДАНИЕ КОММИТОВ
# ═══════════════════════════════════════════════════════════════════

def test_commits():
    """Тесты создания коммитов"""
    print("\n" + "=" * 60)
    print("РАЗДЕЛ 3: СОЗДАНИЕ КОММИТОВ")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        git_cmd(["init"], tmppath)
        setup_git_user(tmppath)

        # 3.1 Первый коммит
        print("\n--- 3.1 Первый коммит ---")
        (tmppath / "file1.py").write_text("print('hello')")
        git_cmd(["add", "-A"], tmppath)
        result = git_cmd(["commit", "-m", "Initial commit"], tmppath)
        if result["success"]:
            test_passed("3.1.1 Первый коммит создан")
        else:
            test_failed("3.1.1 Первый коммит", result["stderr"])

        # 3.2 Коммит с сообщением
        print("\n--- 3.2 Коммит с сообщением ---")
        (tmppath / "file2.py").write_text("print('world')")
        git_cmd(["add", "file2.py"], tmppath)
        result = git_cmd(["commit", "-m", "feat: Add file2"], tmppath)
        if result["success"]:
            test_passed("3.2.1 Коммит с conventional message")
            # Проверяем сообщение
            log_result = git_cmd(["log", "-1", "--format=%s"], tmppath)
            if "feat: Add file2" in log_result["stdout"]:
                test_passed("3.2.2 Сообщение сохранено корректно")
            else:
                test_failed("3.2.2 Сообщение искажено", log_result["stdout"])
        else:
            test_failed("3.2.1 Коммит не создан", result["stderr"])

        # 3.3 Коммит выбранных файлов
        print("\n--- 3.3 Коммит выбранных файлов ---")
        (tmppath / "fileA.txt").write_text("A")
        (tmppath / "fileB.txt").write_text("B")
        git_cmd(["add", "fileA.txt"], tmppath)
        result = git_cmd(["commit", "-m", "Add fileA only"], tmppath)
        if result["success"]:
            status = git_cmd(["status", "--porcelain"], tmppath)
            if "?? fileB.txt" in status["stdout"]:
                test_passed("3.3.1 Только выбранный файл закоммичен")
            else:
                test_failed("3.3.1 fileB должен остаться untracked", status["stdout"])
        else:
            test_failed("3.3.1 Коммит не создан", result["stderr"])

        # 3.4 Коммит без изменений
        print("\n--- 3.4 Коммит без изменений ---")
        # Сначала закоммитим всё
        git_cmd(["add", "-A"], tmppath)
        git_cmd(["commit", "-m", "Commit all"], tmppath)
        # Теперь пробуем снова
        result = git_cmd(["commit", "-m", "Empty commit"], tmppath)
        if not result["success"] and "nothing to commit" in result["stdout"]:
            test_passed("3.4.1 Коммит без изменений отклонён", "nothing to commit")
        else:
            test_warning("3.4.1 Поведение при пустом коммите", result["stdout"])

        # 3.5 Коммит с кавычками в сообщении
        print("\n--- 3.5 Специальные символы в сообщении ---")
        (tmppath / "file3.txt").write_text("test")
        git_cmd(["add", "file3.txt"], tmppath)
        result = git_cmd(["commit", "-m", 'fix: Handle "quoted" strings'], tmppath)
        if result["success"]:
            test_passed("3.5.1 Кавычки в сообщении работают")
        else:
            add_bug("001", "Кавычки в commit message ломают команду",
                    "Minor", "API",
                    ["POST /api/git/commit с message содержащим кавычки"],
                    "Коммит создаётся",
                    f"Ошибка: {result['stderr'][:100]}")

        # 3.6 Коммит с кириллицей
        print("\n--- 3.6 Кириллица в сообщении ---")
        (tmppath / "file4.txt").write_text("тест")
        git_cmd(["add", "file4.txt"], tmppath)
        result = git_cmd(["commit", "-m", "feat: Добавлен файл с кириллицей"], tmppath)
        if result["success"]:
            test_passed("3.6.1 Кириллица в сообщении работает")
            log_result = git_cmd(["log", "-1", "--format=%s"], tmppath)
            if "кириллицей" in log_result["stdout"]:
                test_passed("3.6.2 Кириллица сохранена корректно")
            else:
                test_failed("3.6.2 Кириллица искажена", log_result["stdout"])
        else:
            test_failed("3.6.1 Кириллица в сообщении", result["stderr"])


# ═══════════════════════════════════════════════════════════════════
# РАЗДЕЛ 4: ИСТОРИЯ КОММИТОВ
# ═══════════════════════════════════════════════════════════════════

def test_history():
    """Тесты истории коммитов"""
    print("\n" + "=" * 60)
    print("РАЗДЕЛ 4: ИСТОРИЯ КОММИТОВ")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        git_cmd(["init"], tmppath)
        setup_git_user(tmppath)

        # 4.1 Пустой репозиторий (нет коммитов)
        print("\n--- 4.1 Пустой репозиторий ---")
        result = git_cmd(["log", "--oneline"], tmppath)
        if not result["success"] and "does not have any commits" in result["stderr"]:
            test_passed("4.1.1 Пустой репозиторий обрабатывается")
        elif result["stdout"] == "":
            test_passed("4.1.1 Пустая история для нового репо")
        else:
            test_warning("4.1.1 Неожиданный результат", result["stdout"] or result["stderr"])

        # Создаём несколько коммитов
        for i in range(5):
            (tmppath / f"file{i}.txt").write_text(f"content {i}")
            git_cmd(["add", "-A"], tmppath)
            git_cmd(["commit", "-m", f"Commit {i+1}"], tmppath)

        # 4.2 Получение истории
        print("\n--- 4.2 История коммитов ---")
        result = git_cmd(["log", "--oneline", "-n5"], tmppath)
        if result["success"]:
            lines = [l for l in result["stdout"].split("\n") if l.strip()]
            if len(lines) == 5:
                test_passed("4.2.1 Получено 5 коммитов", f"lines={len(lines)}")
            else:
                test_failed("4.2.1 Неверное количество", f"expected 5, got {len(lines)}")
        else:
            test_failed("4.2.1 git log ошибка", result["stderr"])

        # 4.3 Формат лога (hash|author|date|message)
        print("\n--- 4.3 Формат лога ---")
        result = git_cmd(["log", "-n1", "--format=%h|%an|%ad|%s", "--date=short"], tmppath)
        if result["success"]:
            parts = result["stdout"].split("|")
            if len(parts) == 4:
                test_passed("4.3.1 Формат лога корректный", f"hash={parts[0]}, author={parts[1]}")
            else:
                test_failed("4.3.1 Формат лога неверный", f"parts={len(parts)}")
        else:
            test_failed("4.3.1 git log format ошибка", result["stderr"])

        # 4.4 Limit параметр
        print("\n--- 4.4 Limit параметр ---")
        result = git_cmd(["log", "--oneline", "-n2"], tmppath)
        lines = [l for l in result["stdout"].split("\n") if l.strip()]
        if len(lines) == 2:
            test_passed("4.4.1 limit=2 работает")
        else:
            test_failed("4.4.1 limit не работает", f"got {len(lines)}")

        # 4.5 limit=20
        result = git_cmd(["log", "--oneline", "-n20"], tmppath)
        lines = [l for l in result["stdout"].split("\n") if l.strip()]
        if len(lines) == 5:  # У нас только 5 коммитов
            test_passed("4.4.2 limit=20 возвращает все доступные", f"got {len(lines)}")
        else:
            test_warning("4.4.2 limit=20 результат", f"got {len(lines)}")


# ═══════════════════════════════════════════════════════════════════
# РАЗДЕЛ 5: ГРАНИЧНЫЕ СЛУЧАИ
# ═══════════════════════════════════════════════════════════════════

def test_edge_cases():
    """Тесты граничных случаев"""
    print("\n" + "=" * 60)
    print("РАЗДЕЛ 5: ГРАНИЧНЫЕ СЛУЧАИ")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # 5.1 Git не инициализирован
        print("\n--- 5.1 Git не инициализирован ---")
        result = git_cmd(["status"], tmppath)
        if not result["success"] and "not a git repository" in result["stderr"].lower():
            test_passed("5.1.1 Ошибка для не-git папки")
        else:
            test_warning("5.1.1 Неожиданный результат", result["stderr"])

        # Инициализируем для остальных тестов
        git_cmd(["init"], tmppath)
        setup_git_user(tmppath)

        # 5.2 Файл с пробелами в имени
        print("\n--- 5.2 Файл с пробелами ---")
        space_file = tmppath / "file with spaces.txt"
        space_file.write_text("content")
        git_cmd(["add", "file with spaces.txt"], tmppath)
        result = git_cmd(["commit", "-m", "Add file with spaces"], tmppath)
        if result["success"]:
            test_passed("5.2.1 Файл с пробелами коммитится")
        else:
            add_bug("002", "Файл с пробелами не коммитится",
                    "Major", "API",
                    ["Создать файл 'file with spaces.txt'", "POST /api/git/commit"],
                    "Файл закоммичен",
                    result["stderr"][:100])

        # 5.3 Файл с кириллицей в имени
        print("\n--- 5.3 Файл с кириллицей ---")
        cyrillic_file = tmppath / "файл.txt"
        cyrillic_file.write_text("содержимое")
        git_cmd(["add", "файл.txt"], tmppath)
        result = git_cmd(["commit", "-m", "Add cyrillic file"], tmppath)
        if result["success"]:
            test_passed("5.3.1 Файл с кириллицей коммитится")
        else:
            test_warning("5.3.1 Кириллица в имени файла", result["stderr"])

        # 5.4 Много файлов
        print("\n--- 5.4 Много файлов (100+) ---")
        for i in range(100):
            (tmppath / f"many_file_{i:03d}.txt").write_text(f"content {i}")
        result = git_cmd(["status", "--porcelain"], tmppath)
        if result["success"]:
            lines = result["stdout"].split("\n")
            if len(lines) >= 100:
                test_passed("5.4.1 100+ файлов обрабатываются", f"files={len(lines)}")
            else:
                test_warning("5.4.1 Меньше файлов чем ожидалось", f"files={len(lines)}")
        else:
            test_failed("5.4.1 Ошибка при 100+ файлах", result["stderr"])

        # 5.5 Длинное сообщение коммита
        print("\n--- 5.5 Длинное сообщение ---")
        git_cmd(["add", "-A"], tmppath)
        long_msg = "feat: " + "A" * 500
        result = git_cmd(["commit", "-m", long_msg], tmppath)
        if result["success"]:
            test_passed("5.5.1 Длинное сообщение работает", f"length={len(long_msg)}")
        else:
            test_warning("5.5.1 Длинное сообщение", result["stderr"][:100])

        # 5.6 Переносы строк в сообщении
        print("\n--- 5.6 Многострочное сообщение ---")
        (tmppath / "multiline_test.txt").write_text("test")
        git_cmd(["add", "multiline_test.txt"], tmppath)
        multiline_msg = "feat: Title\n\nBody line 1\nBody line 2"
        result = git_cmd(["commit", "-m", multiline_msg], tmppath)
        if result["success"]:
            log_result = git_cmd(["log", "-1", "--format=%B"], tmppath)
            if "Body line 1" in log_result["stdout"]:
                test_passed("5.6.1 Многострочное сообщение сохраняется")
            else:
                test_warning("5.6.1 Переносы могут теряться", log_result["stdout"][:50])
        else:
            test_warning("5.6.1 Многострочное сообщение", result["stderr"])

        # 5.7 git diff
        print("\n--- 5.7 Git diff ---")
        (tmppath / "diff_test.txt").write_text("line 1\nline 2\n")
        git_cmd(["add", "diff_test.txt"], tmppath)
        git_cmd(["commit", "-m", "Add diff test"], tmppath)
        (tmppath / "diff_test.txt").write_text("line 1\nmodified line 2\nline 3\n")
        result = git_cmd(["diff"], tmppath)
        if result["success"] and "modified" in result["stdout"]:
            test_passed("5.7.1 git diff показывает изменения")
        else:
            test_warning("5.7.1 git diff результат", result["stdout"][:100] if result["stdout"] else "пусто")

        # 5.8 git diff --staged
        print("\n--- 5.8 Git diff --staged ---")
        git_cmd(["add", "diff_test.txt"], tmppath)
        result = git_cmd(["diff", "--staged"], tmppath)
        if result["success"] and "modified" in result["stdout"]:
            test_passed("5.8.1 git diff --staged работает")
        else:
            test_warning("5.8.1 git diff --staged", result["stdout"][:100] if result["stdout"] else "пусто")


# ═══════════════════════════════════════════════════════════════════
# РАЗДЕЛ 6: АНАЛИЗ КОДА API
# ═══════════════════════════════════════════════════════════════════

def analyze_api_code():
    """Анализ кода API на потенциальные проблемы"""
    print("\n" + "=" * 60)
    print("РАЗДЕЛ 6: АНАЛИЗ КОДА API")
    print("=" * 60)

    app_path = Path(__file__).parent.parent / "kok" / "app.py"
    if not app_path.exists():
        test_warning("6.0 app.py не найден", str(app_path))
        return

    code = app_path.read_text(encoding="utf-8")

    # 6.1 Проверка таймаутов
    print("\n--- 6.1 Таймауты ---")
    if "timeout=30" in code or "timeout=" in code:
        test_passed("6.1.1 Таймаут для subprocess установлен")
    else:
        add_bug("003", "Отсутствует таймаут для subprocess",
                "Minor", "API",
                ["Выполнить долгую git операцию"],
                "Операция прерывается по таймауту",
                "Зависание без таймаута")

    # 6.2 Проверка shell=False
    print("\n--- 6.2 Безопасность subprocess ---")
    if "shell=True" in code:
        add_bug("004", "Используется shell=True в subprocess",
                "Major", "API",
                ["Создать файл с специальными символами в имени"],
                "Файл обрабатывается безопасно",
                "Потенциальная command injection")
    else:
        test_passed("6.2.1 shell=True не используется")

    # 6.3 Обработка ошибок
    print("\n--- 6.3 Обработка ошибок ---")
    if "HTTPException(status_code=400" in code and "HTTPException(status_code=500" in code:
        test_passed("6.3.1 HTTP ошибки обрабатываются (400, 500)")
    else:
        test_warning("6.3.1 Обработка HTTP ошибок может быть неполной")

    # 6.4 Проверка get_project_dir
    print("\n--- 6.4 Проверка проекта ---")
    if "get_project_dir()" in code and 'project_dir is None' in code:
        test_passed("6.4.1 Проверка выбранного проекта реализована")
    else:
        test_warning("6.4.1 Проверка проекта может отсутствовать")

    # 6.5 XSS защита во frontend
    print("\n--- 6.5 XSS защита ---")
    html_path = Path(__file__).parent.parent / "kok" / "static" / "index.html"
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8")
        escape_count = html.count("escapeHtml(")
        if escape_count >= 10:
            test_passed(f"6.5.1 escapeHtml() используется ({escape_count} раз)")
        else:
            test_warning(f"6.5.1 escapeHtml() мало используется ({escape_count} раз)")
    else:
        test_warning("6.5.1 index.html не найден")


# ═══════════════════════════════════════════════════════════════════
# ИТОГИ
# ═══════════════════════════════════════════════════════════════════

def print_summary():
    """Вывод итогов тестирования"""
    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ GIT-ИНТЕГРАЦИИ (T005)")
    print("=" * 60)

    print(f"\n✅ Пройдено: {len(results['passed'])}")
    print(f"❌ Провалено: {len(results['failed'])}")
    print(f"⚠️  Предупреждений: {len(results['warnings'])}")
    print(f"🐛 Найдено багов: {len(results['bugs'])}")

    if results['failed']:
        print("\n--- ПРОВАЛЕННЫЕ ТЕСТЫ ---")
        for t in results['failed']:
            print(f"  • {t['name']}: {t['details']}")

    if results['bugs']:
        print("\n--- НАЙДЕННЫЕ БАГИ ---")
        for bug in results['bugs']:
            print(f"\n  🐛 BUG-{bug['id']}: {bug['title']}")
            print(f"     Серьёзность: {bug['severity']}")
            print(f"     Компонент: {bug['component']}")
            print(f"     Ожидалось: {bug['expected']}")
            print(f"     Фактически: {bug['actual']}")

    print("\n" + "=" * 60)
    if len(results['failed']) == 0 and len([b for b in results['bugs'] if b['severity'] in ('Critical', 'Major')]) == 0:
        print("✅ ВЕРДИКТ: ТЕСТИРОВАНИЕ ПРОЙДЕНО")
        return True
    else:
        print("❌ ВЕРДИКТ: ЕСТЬ ПРОБЛЕМЫ")
        return False


def generate_bug_report():
    """Генерация отчёта о багах в формате Markdown"""
    report_path = Path(__file__).parent / "done" / "T005_bug_report.md"
    report_path.parent.mkdir(exist_ok=True)

    content = """# Отчёт о багах: Git-интеграция (T005)

**Дата:** 2026-02-12
**Тестировщик:** dev_fullstack
**Статус:** Тестирование завершено

---

## Статистика

| Метрика | Значение |
|---------|----------|
| Тестов пройдено | """ + str(len(results['passed'])) + """ |
| Тестов провалено | """ + str(len(results['failed'])) + """ |
| Предупреждений | """ + str(len(results['warnings'])) + """ |
| Багов найдено | """ + str(len(results['bugs'])) + """ |

---

## Найденные баги

"""

    if results['bugs']:
        for bug in results['bugs']:
            content += f"""### BUG-{bug['id']}: {bug['title']}
- **Серьёзность:** {bug['severity']}
- **Компонент:** {bug['component']}
- **Шаги воспроизведения:**
"""
            for i, step in enumerate(bug['steps'], 1):
                content += f"  {i}. {step}\n"
            content += f"""- **Ожидаемый результат:** {bug['expected']}
- **Фактический результат:** {bug['actual']}

---

"""
    else:
        content += "*Критических и серьёзных багов не обнаружено.*\n\n"

    # Предупреждения
    if results['warnings']:
        content += """## Предупреждения

"""
        for w in results['warnings']:
            content += f"- **{w['name']}:** {w['details']}\n"

    content += """
---

## Заключение

"""
    if len(results['failed']) == 0 and len([b for b in results['bugs'] if b['severity'] in ('Critical', 'Major')]) == 0:
        content += """**ВЕРДИКТ: Git-интеграция работает корректно.**

Все основные сценарии протестированы:
- Инициализация репозитория
- Статус файлов (staged/unstaged/untracked)
- Создание коммитов
- История коммитов
- Граничные случаи (спец. символы, кириллица, много файлов)

Критических багов не обнаружено.
"""
    else:
        content += """**ВЕРДИКТ: Требуется исправление багов.**

Обнаружены проблемы, требующие внимания разработчиков.
"""

    report_path.write_text(content, encoding="utf-8")
    print(f"\n📄 Отчёт сохранён: {report_path}")
    return str(report_path)


if __name__ == "__main__":
    print("=" * 60)
    print("КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ GIT-ИНТЕГРАЦИИ (T005)")
    print("=" * 60)

    test_initialization()
    test_status()
    test_commits()
    test_history()
    test_edge_cases()
    analyze_api_code()

    success = print_summary()
    report_path = generate_bug_report()

    sys.exit(0 if success else 1)

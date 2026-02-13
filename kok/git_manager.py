"""
Git Manager — модуль для работы с git в Tayfa Orchestrator.

Содержит все git-операции: status, commit, push, branch, release и т.д.
Использует subprocess для выполнения git команд.
"""

import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

# Настройка путей для импорта модулей
KOK_DIR = Path(__file__).resolve().parent
TEMPLATE_COMMON_DIR = KOK_DIR / "template_tayfa" / "common"
if str(TEMPLATE_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_COMMON_DIR))
if str(KOK_DIR) not in sys.path:
    sys.path.insert(0, str(KOK_DIR))

from settings_manager import (
    load_settings, get_next_version, save_version,
)
from task_manager import get_sprint, update_sprint_release
from project_manager import get_project_dir

# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/git", tags=["git"])


# ── Helper Functions ──────────────────────────────────────────────────────────

def _to_wsl_path(path: Path | str) -> str:
    """
    Конвертирует Windows путь в WSL путь для работы с subprocess.

    C:\\Users\\... -> /mnt/c/Users/...
    /mnt/c/Users/... -> /mnt/c/Users/... (без изменений)
    """
    path_str = str(path).strip()

    # Уже WSL-путь
    if path_str.startswith("/mnt/"):
        return path_str

    # Windows-путь: C:\Users\... или C:/Users/...
    if len(path_str) >= 2 and path_str[1] == ':':
        drive = path_str[0].lower()
        rest = path_str[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"

    # Другие пути (относительные, Unix) — оставляем как есть
    return path_str


def _get_git_env() -> dict:
    """
    Возвращает переменные окружения для Git с user.name и user.email из настроек.
    """
    import os
    env = os.environ.copy()
    settings = load_settings()
    git_settings = settings.get("git", {})

    user_name = git_settings.get("userName", "").strip()
    user_email = git_settings.get("userEmail", "").strip()

    if user_name:
        env["GIT_AUTHOR_NAME"] = user_name
        env["GIT_COMMITTER_NAME"] = user_name
    if user_email:
        env["GIT_AUTHOR_EMAIL"] = user_email
        env["GIT_COMMITTER_EMAIL"] = user_email

    return env


def _get_git_settings() -> dict:
    """Возвращает Git-настройки из settings.json."""
    settings = load_settings()
    return settings.get("git", {})


def _get_authenticated_remote_url(remote_url: str) -> str:
    """
    Возвращает URL с токеном для аутентификации на GitHub.
    Формат: https://TOKEN@github.com/user/repo.git
    """
    git_settings = _get_git_settings()
    token = git_settings.get("githubToken", "").strip()

    if not token or not remote_url:
        return remote_url

    # Поддерживаем только HTTPS URLs
    if remote_url.startswith("https://github.com/"):
        # https://github.com/user/repo.git -> https://TOKEN@github.com/user/repo.git
        return remote_url.replace("https://github.com/", f"https://{token}@github.com/")
    elif remote_url.startswith("https://") and "github.com" in remote_url:
        # Уже может быть с токеном, заменяем
        return re.sub(r"https://[^@]*@github\.com/", f"https://{token}@github.com/", remote_url)

    return remote_url


def run_git_command(args: list[str], cwd: Path | None = None, use_config: bool = True) -> dict:
    """
    Выполняет git команду через subprocess.
    Возвращает {"success": bool, "stdout": str, "stderr": str}.
    По умолчанию cwd = get_project_dir() (корень проекта).
    use_config: применять user.name/user.email из настроек приложения.
    """
    if cwd is None:
        cwd = get_project_dir()
        if cwd is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Проект не выбран. Откройте проект через /api/projects/open",
            }

    try:
        env = _get_git_env() if use_config else None
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Таймаут выполнения git команды"}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "git не найден в системе"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def _setup_git_remote() -> dict:
    """
    Настраивает git remote origin из настроек приложения.
    Возвращает {"success": bool, "message": str}.
    """
    git_settings = _get_git_settings()
    remote_url = git_settings.get("remoteUrl", "").strip()

    if not remote_url:
        return {"success": False, "message": "Remote URL не настроен в настройках"}

    # Получаем URL с токеном
    auth_url = _get_authenticated_remote_url(remote_url)

    # Проверяем, есть ли уже origin
    check = run_git_command(["remote", "get-url", "origin"], use_config=False)
    if check["success"]:
        # Origin существует, обновляем URL
        result = run_git_command(["remote", "set-url", "origin", auth_url], use_config=False)
    else:
        # Добавляем новый remote
        result = run_git_command(["remote", "add", "origin", auth_url], use_config=False)

    if result["success"]:
        return {"success": True, "message": "Remote origin настроен"}
    else:
        return {"success": False, "message": result["stderr"]}


def _check_git_initialized() -> dict | None:
    """Проверяет, инициализирован ли git. Возвращает ошибку или None."""
    project_dir = get_project_dir()
    if project_dir is None:
        return {"error": "Проект не выбран"}
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {"error": "Git not initialized"}
    return None


def check_git_state() -> dict:
    """
    Проверяет состояние git для создания ветки спринта.

    Возвращает:
    {
        "initialized": bool,
        "has_remote": bool,
        "main_branch": str | None,  # "main" или "master" или None
        "error": str | None,  # Критическая ошибка
        "warning": str | None  # Предупреждение (не блокирует)
    }
    """
    result = {
        "initialized": False,
        "has_remote": False,
        "main_branch": None,
        "error": None,
        "warning": None,
    }

    project_dir = get_project_dir()
    if project_dir is None:
        result["error"] = "Проект не выбран. Откройте проект через интерфейс"
        return result

    # Проверка 1: git инициализирован?
    git_check = run_git_command(["rev-parse", "--git-dir"])
    if not git_check["success"]:
        result["error"] = "Git не инициализирован. Выполните git init или используйте кнопку 'Инициализировать Git'"
        return result
    result["initialized"] = True

    # Проверка 2: remote origin существует?
    remote_check = run_git_command(["remote", "get-url", "origin"], use_config=False)
    if remote_check["success"]:
        result["has_remote"] = True
    else:
        result["warning"] = "Remote origin не настроен. Ветка будет создана локально"

    # Проверка 3: какая главная ветка существует (main или master)?
    main_check = run_git_command(["show-ref", "--verify", "refs/heads/main"])
    if main_check["success"]:
        result["main_branch"] = "main"
    else:
        master_check = run_git_command(["show-ref", "--verify", "refs/heads/master"])
        if master_check["success"]:
            result["main_branch"] = "master"
        else:
            # Нет ни main, ни master — проверяем, есть ли вообще коммиты
            log_check = run_git_command(["log", "-1"])
            if not log_check["success"]:
                result["error"] = "В репозитории нет коммитов. Создайте первый коммит перед созданием спринта"
            else:
                # Есть коммиты, но нет main/master — используем текущую ветку
                branch_check = run_git_command(["branch", "--show-current"])
                if branch_check["success"] and branch_check["stdout"]:
                    result["main_branch"] = branch_check["stdout"]
                    result["warning"] = f"Ветки main/master не найдены, используется текущая ветка '{branch_check['stdout']}'"
                else:
                    result["error"] = "Не удалось определить базовую ветку"

    return result


def check_branch_exists(branch_name: str) -> bool:
    """Проверяет, существует ли локальная ветка."""
    result = run_git_command(["show-ref", "--verify", f"refs/heads/{branch_name}"])
    return result["success"]


def create_sprint_branch(sprint_id: str) -> dict:
    """
    Создаёт ветку для спринта от главной ветки (main/master).

    Возвращает:
    {
        "success": bool,
        "branch": str | None,
        "git_status": "ok" | "warning" | "error",
        "git_warning": str | None,
        "error": str | None
    }
    """
    branch_name = f"sprint/{sprint_id}"
    result = {
        "success": False,
        "branch": None,
        "git_status": "error",
        "git_warning": None,
        "error": None,
    }

    # Проверяем состояние git
    state = check_git_state()

    if state["error"]:
        result["error"] = state["error"]
        return result

    # Сохраняем предупреждение (если есть)
    if state["warning"]:
        result["git_warning"] = state["warning"]

    main_branch = state["main_branch"]

    # Проверяем, не существует ли уже ветка
    if check_branch_exists(branch_name):
        result["error"] = f"Ветка {branch_name} уже существует"
        return result

    # Переключаемся на main branch
    checkout_main = run_git_command(["checkout", main_branch])
    if not checkout_main["success"]:
        result["error"] = f"Не удалось переключиться на {main_branch}: {checkout_main['stderr']}"
        return result

    # Делаем pull если есть remote
    if state["has_remote"]:
        pull_result = run_git_command(["pull", "origin", main_branch])
        if not pull_result["success"]:
            # Pull не удался — предупреждаем, но продолжаем
            if result["git_warning"]:
                result["git_warning"] += f"; Pull не удался: {pull_result['stderr']}"
            else:
                result["git_warning"] = f"Не удалось выполнить pull (возможно, offline): {pull_result['stderr']}"

    # Создаём ветку спринта
    create_branch = run_git_command(["checkout", "-b", branch_name])
    if not create_branch["success"]:
        result["error"] = f"Не удалось создать ветку {branch_name}: {create_branch['stderr']}"
        return result

    # Успех!
    result["success"] = True
    result["branch"] = branch_name
    result["git_status"] = "warning" if result["git_warning"] else "ok"

    return result


def commit_task(task_id: str, title: str) -> dict:
    """
    Коммитит все изменения с сообщением 'T001: title'.

    Возвращает:
    {
        "success": bool,
        "commit": str | None,  # short hash
        "message": str | None,
        "error": str | None
    }
    """
    result = {
        "success": False,
        "commit": None,
        "message": None,
        "error": None,
    }

    commit_message = f"{task_id}: {title}"

    # git add -A
    add_result = run_git_command(["add", "-A"])
    if not add_result["success"]:
        result["error"] = f"Ошибка git add: {add_result['stderr']}"
        return result

    # git commit
    commit_result = run_git_command(["commit", "-m", commit_message])
    if not commit_result["success"]:
        # Проверяем, есть ли что коммитить
        if "nothing to commit" in commit_result.get("stdout", "") + commit_result.get("stderr", ""):
            result["error"] = "Нечего коммитить — нет изменений"
            return result
        result["error"] = f"Ошибка git commit: {commit_result['stderr']}"
        return result

    # Получаем hash коммита
    hash_result = run_git_command(["rev-parse", "--short", "HEAD"])

    result["success"] = True
    result["commit"] = hash_result["stdout"] if hash_result["success"] else None
    result["message"] = commit_message

    return result


def release_sprint(sprint_id: str, version: str | None = None, skip_checks: bool = False) -> dict:
    """
    Выполняет релиз спринта: merge sprint branch в main, создаёт тег, push.

    Args:
        sprint_id: ID спринта (например, "S001")
        version: Версия релиза (опционально, автоинкремент если не указана)
        skip_checks: Пропустить проверки git-статуса (по умолчанию False)

    Возвращает:
    {
        "success": bool,
        "version": str | None,
        "commit": str | None,
        "message": str | None,
        "tag_created": bool,
        "pushed": bool,
        "warnings": list | None,
        "error": str | None
    }
    """
    result = {
        "success": False,
        "version": None,
        "commit": None,
        "message": None,
        "tag_created": False,
        "pushed": False,
        "warnings": None,
        "error": None,
    }

    # Проверяем готовность git к release
    if not skip_checks:
        git_check = check_git_ready_for_release()
        if not git_check["ready"]:
            result["error"] = "; ".join(git_check["errors"])
            return result
        if git_check.get("warnings"):
            result["warnings"] = git_check["warnings"]

    # Проверяем git
    err = _check_git_initialized()
    if err:
        result["error"] = err["error"]
        return result

    # Получаем информацию о спринте
    sprint = get_sprint(sprint_id)
    if not sprint:
        result["error"] = f"Спринт {sprint_id} не найден"
        return result

    sprint_title = sprint.get("title", "")
    source_branch = f"sprint/{sprint_id}"
    target_branch = "main"

    # Определяем версию
    if not version:
        tag_result = run_git_command(["describe", "--tags", "--abbrev=0"])
        if tag_result["success"] and tag_result["stdout"]:
            version = get_next_version()
        else:
            version = "v0.1.0"

    result["version"] = version

    # Формируем сообщение
    merge_message = f"Release {version}: {sprint_title}" if sprint_title else f"Release {version}"
    result["message"] = merge_message

    try:
        # 0. Настроить remote
        _setup_git_remote()

        # 1. Переключиться на source_branch и обновить
        checkout_src = run_git_command(["checkout", source_branch])
        if not checkout_src["success"]:
            result["error"] = f"Ветка {source_branch} не найдена: {checkout_src['stderr']}"
            return result
        run_git_command(["pull", "origin", source_branch])

        # 2. Переключиться на target_branch
        checkout_tgt = run_git_command(["checkout", target_branch])
        if not checkout_tgt["success"]:
            # Создаём main если не существует
            create_tgt = run_git_command(["checkout", "-b", target_branch])
            if not create_tgt["success"]:
                result["error"] = f"Не удалось создать ветку {target_branch}: {create_tgt['stderr']}"
                run_git_command(["checkout", source_branch])
                return result
        else:
            run_git_command(["pull", "origin", target_branch])

        # 3. Merge
        merge_result = run_git_command(["merge", source_branch, "--no-ff", "-m", merge_message])
        if not merge_result["success"]:
            run_git_command(["merge", "--abort"])
            run_git_command(["checkout", source_branch])
            result["error"] = f"Merge conflict: {merge_result['stderr']}"
            return result

        # 4. Получаем hash
        hash_result = run_git_command(["rev-parse", "--short", "HEAD"])
        result["commit"] = hash_result["stdout"] if hash_result["success"] else None

        # 5. Создаём тег
        tag_msg = f"Sprint: {sprint_title}" if sprint_title else f"Release {version}"
        tag_result = run_git_command(["tag", "-a", version, "-m", tag_msg])
        result["tag_created"] = tag_result["success"]

        # 6. Push
        push_result = run_git_command(["push", "origin", target_branch, "--tags"])
        result["pushed"] = push_result["success"]

        if not result["pushed"]:
            # Повторная попытка: сначала ветка, потом теги
            push_branch = run_git_command(["push", "origin", target_branch])
            if push_branch["success"]:
                run_git_command(["push", "origin", "--tags"])
                result["pushed"] = True

        # 7. Если push не удался — откатываем merge и тег
        if not result["pushed"]:
            # Удаляем локальный тег
            run_git_command(["tag", "-d", version])
            # Откатываем merge (возвращаем main в состояние до merge)
            run_git_command(["reset", "--hard", "HEAD~1"])
            # Возвращаемся на ветку спринта
            run_git_command(["checkout", source_branch])
            result["error"] = f"Push failed: {push_result.get('stderr', 'Unknown error')}. Merge and tag rolled back."
            return result

        # 8. Сохраняем версию (только при успешном push)
        save_version(version)

        # 9. Обновляем спринт (только при успешном push)
        update_sprint_release(sprint_id, version, pushed=result["pushed"])

        # 10. Возвращаемся на source_branch
        run_git_command(["checkout", source_branch])

        result["success"] = True
        return result

    except Exception as e:
        run_git_command(["checkout", source_branch])
        result["error"] = str(e)
        return result


def _check_gh_cli() -> dict | None:
    """Проверяет, установлен ли gh CLI. Возвращает ошибку или None."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"error": "gh CLI not found"}
        return None
    except FileNotFoundError:
        return {"error": "gh CLI not found"}
    except Exception as e:
        return {"error": f"gh CLI check failed: {str(e)}"}


def check_git_ready_for_release() -> dict:
    """
    Проверяет готовность git к release операциям (merge, push).

    Выполняет проверки в следующем порядке:
    1. Git инициализирован (наличие .git папки)
    2. Remote настроен (git remote get-url origin)
    3. Нет uncommitted changes (git status --porcelain)
    4. Remote доступен (git ls-remote --exit-code origin)

    Returns:
        {
            "ready": bool,
            "errors": [],      # Блокирующие ошибки
            "warnings": [],    # Предупреждения (не блокируют)
            "details": {
                "branch": str,
                "remote": str,
                "remote_url": str
            }
        }
    """
    errors = []
    warnings = []
    details = {
        "branch": "",
        "remote": "origin",
        "remote_url": ""
    }

    project_dir = get_project_dir()
    if project_dir is None:
        return {
            "ready": False,
            "errors": ["Проект не выбран. Откройте проект через настройки"],
            "warnings": [],
            "details": details
        }

    # 1. Проверка: Git инициализирован
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        errors.append("Git не инициализирован. Выполните git init")
        return {
            "ready": False,
            "errors": errors,
            "warnings": warnings,
            "details": details
        }

    # Получаем текущую ветку
    branch_res = run_git_command(["branch", "--show-current"])
    if branch_res["success"]:
        details["branch"] = branch_res["stdout"]

    # 2. Проверка: Remote настроен
    remote_res = run_git_command(["remote", "get-url", "origin"], use_config=False)
    if not remote_res["success"]:
        errors.append("Remote не настроен. Укажите GitHub репозиторий в настройках")
        return {
            "ready": False,
            "errors": errors,
            "warnings": warnings,
            "details": details
        }

    # Скрываем токен в URL для безопасности при отображении
    raw_url = remote_res["stdout"]
    if "@github.com" in raw_url:
        # Маскируем токен: https://token@github.com/... -> https://***@github.com/...
        display_url = re.sub(r"https://[^@]+@", "https://***@", raw_url)
    else:
        display_url = raw_url
    details["remote_url"] = display_url

    # 3. Проверка: Нет uncommitted changes
    status_res = run_git_command(["status", "--porcelain"])
    if status_res["success"] and status_res["stdout"]:
        has_staged = False
        has_unstaged = False
        has_untracked = False

        for line in status_res["stdout"].split("\n"):
            if not line or len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]

            # Staged changes (в индексе)
            if index_status in ("A", "M", "D", "R", "C"):
                has_staged = True
            # Unstaged changes (изменены, но не добавлены)
            if worktree_status in ("M", "D"):
                has_unstaged = True
            # Untracked files (новые файлы)
            if index_status == "?" and worktree_status == "?":
                has_untracked = True

        # Staged и unstaged — это ошибка (блокирует)
        if has_staged or has_unstaged:
            errors.append("Есть незакоммиченные изменения. Сделайте коммит перед релизом")

        # Untracked — это предупреждение (не блокирует)
        if has_untracked and not has_staged and not has_unstaged:
            warnings.append("Есть untracked файлы (новые файлы не в git)")

    # Если есть ошибки на этом этапе — не проверяем доступность remote
    if errors:
        return {
            "ready": False,
            "errors": errors,
            "warnings": warnings,
            "details": details
        }

    # 4. Проверка: Remote доступен (выполняем только если нет других ошибок)
    # Перед проверкой обновляем remote URL с актуальным токеном
    _setup_git_remote()

    # git ls-remote --exit-code проверяет доступность и что remote не пустой
    # Используем увеличенный таймаут для сетевой операции
    try:
        ls_remote_result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=15,  # 15 секунд для сетевой операции
        )
        if ls_remote_result.returncode != 0:
            error_msg = ls_remote_result.stderr
            if "Authentication failed" in error_msg or "could not read" in error_msg:
                errors.append("Нет доступа к remote. Проверьте токен GitHub и URL репозитория")
            elif "Could not resolve host" in error_msg:
                errors.append("Не удаётся подключиться к GitHub. Проверьте интернет-соединение")
            elif "Repository not found" in error_msg:
                errors.append("Репозиторий не найден. Проверьте URL в настройках")
            else:
                errors.append("Нет доступа к remote. Проверьте токен GitHub и URL репозитория")
    except subprocess.TimeoutExpired:
        errors.append("Таймаут подключения к GitHub. Проверьте интернет-соединение")
    except Exception as e:
        errors.append(f"Ошибка проверки remote: {str(e)}")

    return {
        "ready": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "details": details
    }


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.get("/release-ready")
async def api_git_release_ready():
    """
    Проверить готовность git к release операциям.

    Выполняет проверки:
    1. Git инициализирован
    2. Remote настроен
    3. Нет uncommitted changes
    4. Remote доступен

    Возвращает:
    {
        "ready": true/false,
        "errors": ["описание ошибки"],
        "warnings": ["предупреждение"],
        "details": {
            "branch": "sprint/S001",
            "remote": "origin",
            "remote_url": "https://github.com/..."
        }
    }
    """
    return check_git_ready_for_release()


@router.get("/status")
async def api_git_status():
    """
    Статус репозитория.
    Возвращает: initialized, branch, staged, unstaged, untracked.
    При отсутствии .git возвращает initialized=false (не выбрасывает ошибку).
    """
    project_dir = get_project_dir()
    if project_dir is None:
        return {
            "initialized": False,
            "error": "no_project",
            "message": "Проект не выбран"
        }

    # Проверяем инициализацию git
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {
            "initialized": False,
            "error": "not_initialized",
            "message": "Git не инициализирован"
        }

    result = {
        "initialized": True,
        "branch": "",
        "staged": [],
        "unstaged": [],
        "untracked": [],
    }

    # Текущая ветка
    branch_res = run_git_command(["branch", "--show-current"])
    print(f"[DEBUG] git branch --show-current: {branch_res}")
    if branch_res["success"]:
        result["branch"] = branch_res["stdout"]

    # Статус файлов (porcelain для парсинга)
    status_res = run_git_command(["status", "--porcelain"])
    if status_res["success"] and status_res["stdout"]:
        for line in status_res["stdout"].split("\n"):
            if not line or len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]
            filename = line[3:]

            # Staged: файлы добавленные в индекс (A, M, D, R, C в первой позиции)
            if index_status in ("A", "M", "D", "R", "C"):
                result["staged"].append(filename)
            # Unstaged: изменённые но не добавленные (M, D во второй позиции)
            if worktree_status in ("M", "D"):
                result["unstaged"].append(filename)
            # Untracked: новые неотслеживаемые файлы (??)
            if index_status == "?" and worktree_status == "?":
                result["untracked"].append(filename)

    return result


@router.get("/branches")
async def api_git_branches():
    """
    Список веток.
    Возвращает: current, branches (локальные + remotes/).
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    result = {
        "current": "",
        "branches": [],
    }

    # Текущая ветка
    branch_res = run_git_command(["branch", "--show-current"])
    if branch_res["success"]:
        result["current"] = branch_res["stdout"]

    # Все ветки (локальные + remote)
    all_res = run_git_command(["branch", "-a", "--format=%(refname:short)"])
    if all_res["success"] and all_res["stdout"]:
        result["branches"] = [b.strip() for b in all_res["stdout"].split("\n") if b.strip()]

    return result


@router.post("/init")
async def api_git_init(data: dict = {}):
    """
    Инициализация git-репозитория.
    Body (опционально): {"create_initial_commit": true}
    """
    project_dir = get_project_dir()
    if project_dir is None:
        raise HTTPException(status_code=400, detail="Проект не выбран. Откройте проект через /api/projects/open")

    git_dir = project_dir / ".git"
    if git_dir.exists():
        return {"success": True, "message": "Git repository already initialized", "initialized": True}

    # git init
    result = run_git_command(["init"])
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "Ошибка git init")

    response = {"success": True, "message": "Git repository initialized", "initialized": True}

    # Устанавливаем default branch из настроек
    default_branch = _get_git_settings().get("defaultBranch", "main")
    run_git_command(["config", "init.defaultBranch", default_branch], use_config=False)

    # Создаём .gitignore (всегда, если не существует)
    gitignore_path = project_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_content = """# Dependencies
node_modules/
__pycache__/
*.pyc
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Build
dist/
build/
*.egg-info/

# Environment
.env
.env.local
*.log

# OS
.DS_Store
Thumbs.db

# Tayfa internal
.tayfa/*/notes.md
"""
        try:
            gitignore_path.write_text(gitignore_content, encoding="utf-8")
            response["gitignore_created"] = True
        except Exception as e:
            response["gitignore_error"] = str(e)
            response["gitignore_created"] = False
    else:
        response["gitignore_created"] = False  # Уже существует

    # Создаём initial commit (по умолчанию true)
    create_initial_commit = data.get("create_initial_commit", True) if data else True
    if create_initial_commit:
        # Добавляем .gitignore в staging
        add_result = run_git_command(["add", ".gitignore"], use_config=True)
        if add_result["success"]:
            # Создаём initial commit
            commit_result = run_git_command(["commit", "-m", "Initial commit"], use_config=True)
            if commit_result["success"]:
                response["initial_commit"] = True
                # Получаем hash последнего коммита
                hash_result = run_git_command(["rev-parse", "HEAD"], use_config=False)
                if hash_result["success"]:
                    response["commit_hash"] = hash_result["stdout"]
            else:
                # Не ошибка, но предупреждение
                response["initial_commit"] = False
                response["commit_warning"] = commit_result["stderr"] or "Не удалось создать initial commit"
        else:
            response["initial_commit"] = False
            response["commit_warning"] = f"Не удалось добавить .gitignore: {add_result['stderr']}"
    else:
        response["initial_commit"] = False

    # Настраиваем remote из настроек (если указан)
    remote_result = _setup_git_remote()
    if remote_result["success"]:
        response["remote_configured"] = True
    elif _get_git_settings().get("remoteUrl"):
        response["remote_error"] = remote_result["message"]

    return response


@router.post("/setup-remote")
async def api_git_setup_remote():
    """
    Настраивает git remote origin из настроек приложения.
    Использует remoteUrl и githubToken из settings.json.
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    result = _setup_git_remote()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return {"status": "configured", "message": result["message"]}


@router.get("/remote")
async def api_git_remote():
    """
    Получить информацию о remote repositories.
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    result = run_git_command(["remote", "-v"], use_config=False)
    if not result["success"]:
        return {"remotes": []}

    remotes = []
    for line in result["stdout"].split("\n"):
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                # Скрываем токен в URL для безопасности
                url = parts[1]
                if "@github.com" in url:
                    url = url.split("@github.com")[0].rsplit("/", 1)[0] + "@github.com/***"
                remotes.append({"name": name, "url": url})

    return {"remotes": remotes}


@router.get("/diff")
async def api_git_diff(staged: bool = False, file: str | None = None):
    """
    Просмотр изменений (diff).
    Параметры: ?staged=true — показать staged изменения, ?file=path — diff конкретного файла
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    args = ["diff"]
    if staged:
        args.append("--staged")
    if file:
        args.append("--")
        args.append(file)

    result = run_git_command(args)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "Ошибка git diff")

    return {"diff": result["stdout"], "staged": staged, "file": file}


@router.post("/branch")
async def api_git_branch(data: dict):
    """
    Создать ветку.
    Body: {"name": "feature/T025-git-api", "from_branch": "develop", "checkout": true}
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Нужно поле name")

    from_branch = data.get("from_branch")
    checkout = data.get("checkout", True)

    if checkout:
        # git checkout -b <name> [from_branch]
        args = ["checkout", "-b", name]
        if from_branch:
            args.append(from_branch)
    else:
        # git branch <name> [from_branch]
        args = ["branch", name]
        if from_branch:
            args.append(from_branch)

    result = run_git_command(args)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "Ошибка создания ветки")

    return {
        "status": "created",
        "branch": name,
        "from_branch": from_branch,
        "checkout": checkout,
    }


@router.post("/commit")
async def api_git_commit(data: dict):
    """
    Создать коммит.
    Body: {"message": "Commit message", "files": ["file1.py", "file2.js"]}
    Если files пустой — выполняется git add -A (добавляет все изменения).
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="Нужно поле message")

    files = data.get("files", [])

    # Добавляем файлы в индекс
    if files:
        add_result = run_git_command(["add"] + files)
    else:
        # Если files не указаны — git add -A
        add_result = run_git_command(["add", "-A"])

    if not add_result["success"]:
        raise HTTPException(status_code=500, detail=add_result["stderr"] or "Ошибка git add")

    # Создаём коммит
    commit_result = run_git_command(["commit", "-m", message])
    if not commit_result["success"]:
        # Проверяем, есть ли что коммитить
        if "nothing to commit" in commit_result["stdout"] or "nothing to commit" in commit_result["stderr"]:
            raise HTTPException(status_code=400, detail="Нечего коммитить — нет изменений в индексе")
        raise HTTPException(status_code=500, detail=commit_result["stderr"] or "Ошибка git commit")

    # Получаем хеш нового коммита
    hash_result = run_git_command(["rev-parse", "--short", "HEAD"])
    commit_hash = hash_result["stdout"] if hash_result["success"] else ""

    # Подсчитываем количество закоммиченных файлов
    files_count = len(files) if files else "all"
    commit_message = f"Committed {files_count} files" if isinstance(files_count, int) else "Committed all staged files"

    return {
        "success": True,
        "hash": commit_hash,
        "message": commit_message,
    }


@router.post("/push")
async def api_git_push(data: dict):
    """
    Push в remote.
    Body: {"remote": "origin", "branch": null, "set_upstream": true, "skip_checks": false}

    Перед push выполняется проверка git-статуса (можно отключить через skip_checks).
    """
    skip_checks = data.get("skip_checks", False)

    if not skip_checks:
        # Проверяем готовность git к push
        git_check = check_git_ready_for_release()
        if not git_check["ready"]:
            # Формируем понятное сообщение об ошибке
            error_details = "; ".join(git_check["errors"])
            raise HTTPException(status_code=400, detail=error_details)

    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    remote = data.get("remote", "origin")
    branch = data.get("branch")
    set_upstream = data.get("set_upstream", True)

    # Перед push обновляем remote URL с актуальным токеном
    if remote == "origin":
        _setup_git_remote()

    args = ["push"]
    if set_upstream:
        args.append("-u")
    args.append(remote)
    if branch:
        args.append(branch)

    result = run_git_command(args)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "Ошибка git push")

    # Включаем предупреждения в ответ (если были)
    response = {
        "status": "pushed",
        "remote": remote,
        "branch": branch,
        "set_upstream": set_upstream,
        "output": result["stdout"] or result["stderr"],
    }

    if not skip_checks:
        git_check = check_git_ready_for_release()
        if git_check.get("warnings"):
            response["warnings"] = git_check["warnings"]

    return response


@router.post("/pr")
async def api_git_pr(data: dict):
    """
    Создать Pull Request через gh CLI.
    Body: {"title": "T025: Git API", "body": "...", "base": "develop", "draft": false}
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    gh_err = _check_gh_cli()
    if gh_err:
        raise HTTPException(status_code=400, detail=gh_err["error"])

    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Нужно поле title")

    body = data.get("body", "")
    base = data.get("base", "main")
    draft = data.get("draft", False)

    project_dir = get_project_dir()
    if project_dir is None:
        raise HTTPException(status_code=400, detail="Проект не выбран")

    args = ["pr", "create", "--title", title, "--body", body, "--base", base]
    if draft:
        args.append("--draft")

    try:
        result = subprocess.run(
            ["gh"] + args,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr or "Ошибка gh pr create")

        # gh pr create выводит URL созданного PR
        pr_url = result.stdout.strip()
        return {
            "status": "created",
            "title": title,
            "base": base,
            "draft": draft,
            "url": pr_url,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Таймаут gh pr create")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log")
async def api_git_log(limit: int = 20):
    """
    История коммитов.
    Параметры: ?limit=20
    Возвращает: {"commits": [{"hash": "abc1234", "author": "Name", "date": "2026-02-11", "message": "..."}]}
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    # Формат: short_hash|author|date_short|message
    # Используем --date=short для формата YYYY-MM-DD
    result = run_git_command([
        "log", f"-n{limit}",
        "--oneline",
        "--format=%h|%an|%ad|%s",
        "--date=short"
    ])

    if not result["success"]:
        # Если нет коммитов — возвращаем пустой список
        if "does not have any commits" in result["stderr"]:
            return {"commits": []}
        raise HTTPException(status_code=500, detail=result["stderr"] or "Ошибка git log")

    commits = []
    for line in result["stdout"].split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0],
                "author": parts[1],
                "date": parts[2],
                "message": parts[3],
            })

    return {"commits": commits}


@router.post("/release")
async def api_git_release(data: dict):
    """
    Создать релиз: merge develop → main, создать тег, push.

    Body: {
        "sprint_id": "S006",        // опционально — для записи версии в спринт
        "version": "v0.2.0",        // опционально — иначе автоинкремент
        "source_branch": "develop", // опционально, default: develop
        "target_branch": "main",    // опционально, default: main
        "skip_checks": false        // опционально — пропустить проверки
    }

    Перед release выполняется проверка git-статуса:
    - Git инициализирован
    - Remote настроен
    - Нет uncommitted changes
    - Remote доступен

    Response (успех): {
        "success": true,
        "version": "v0.2.0",
        "commit": "abc1234",
        "message": "Release v0.2.0: Sprint Title",
        "tag_created": true,
        "pushed": true
    }
    """
    skip_checks = data.get("skip_checks", False)

    # Проверяем готовность git к release (если не пропущено)
    if not skip_checks:
        git_check = check_git_ready_for_release()
        if not git_check["ready"]:
            # Формируем понятное сообщение об ошибке
            error_details = "; ".join(git_check["errors"])
            raise HTTPException(status_code=400, detail=error_details)

    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    sprint_id = data.get("sprint_id")
    version = data.get("version")
    source_branch = data.get("source_branch", "develop")
    target_branch = data.get("target_branch", "main")

    # Получаем информацию о спринте (если указан)
    sprint_title = ""
    if sprint_id:
        sprint = get_sprint(sprint_id)
        if sprint:
            sprint_title = sprint.get("title", "")

    # Определяем версию
    if not version:
        # Попробуем получить последний тег из git
        tag_result = run_git_command(["describe", "--tags", "--abbrev=0"])
        if tag_result["success"] and tag_result["stdout"]:
            # Есть теги — инкрементируем
            version = get_next_version()
        else:
            # Нет тегов — начинаем с v0.1.0
            version = "v0.1.0"

    # Формируем сообщение коммита
    if sprint_title:
        merge_message = f"Release {version}: {sprint_title}"
    else:
        merge_message = f"Release {version}"

    project_dir = get_project_dir()
    if project_dir is None:
        raise HTTPException(status_code=400, detail="Проект не выбран")

    try:
        # 0. Настроить remote с токеном для аутентификации
        _setup_git_remote()

        # 1. Убедиться что source_branch актуален
        run_git_command(["checkout", source_branch])
        run_git_command(["pull", "origin", source_branch])

        # 2. Переключиться на target_branch и обновить
        checkout_result = run_git_command(["checkout", target_branch])
        if not checkout_result["success"]:
            # target_branch не существует — создаём
            create_result = run_git_command(["checkout", "-b", target_branch])
            if not create_result["success"]:
                raise HTTPException(
                    status_code=500,
                    detail=f"Не удалось создать ветку {target_branch}: {create_result['stderr']}"
                )
        else:
            run_git_command(["pull", "origin", target_branch])

        # 3. Merge source → target
        merge_result = run_git_command([
            "merge", source_branch, "--no-ff", "-m", merge_message
        ])
        if not merge_result["success"]:
            # Конфликт — откатываем
            run_git_command(["merge", "--abort"])
            run_git_command(["checkout", source_branch])
            raise HTTPException(
                status_code=409,
                detail=f"Merge conflict: {merge_result['stderr']}"
            )

        # 4. Получаем хеш коммита
        hash_result = run_git_command(["rev-parse", "--short", "HEAD"])
        commit_hash = hash_result["stdout"] if hash_result["success"] else ""

        # 5. Создаём тег
        tag_message = f"Sprint: {sprint_title}" if sprint_title else f"Release {version}"
        tag_result = run_git_command(["tag", "-a", version, "-m", tag_message])
        tag_created = tag_result["success"]

        # 6. Push main и тегов
        push_result = run_git_command(["push", "origin", target_branch, "--tags"])
        pushed = push_result["success"]

        if not pushed:
            # Пробуем push без тегов
            push_branch = run_git_command(["push", "origin", target_branch])
            if push_branch["success"]:
                # Push тегов отдельно
                run_git_command(["push", "origin", "--tags"])
                pushed = True

        # 7. Сохраняем версию в настройках
        save_version(version)

        # 8. Обновляем спринт (если указан) — используем публичный API
        if sprint_id:
            update_sprint_release(sprint_id, version, pushed=pushed)

        # 9. Возвращаемся на source_branch
        run_git_command(["checkout", source_branch])

        return {
            "success": True,
            "version": version,
            "commit": commit_hash,
            "message": merge_message,
            "tag_created": tag_created,
            "pushed": pushed,
            "sprint_id": sprint_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Пытаемся вернуться на source_branch при ошибке
        run_git_command(["checkout", source_branch])
        raise HTTPException(status_code=500, detail=str(e))

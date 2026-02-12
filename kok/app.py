"""
Tayfa Orchestrator — веб-приложение для управления мультиагентной системой.

Запускает Claude API сервер (WSL + uvicorn), управляет агентами,
управляет агентами, предоставляет веб-интерфейс.
"""

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path, PureWindowsPath, PurePosixPath

import httpx
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# ── Конфигурация ──────────────────────────────────────────────────────────────

CLAUDE_API_URL = "http://localhost:8788"
# app.py находится в TayfaNew/kok/
# TAYFA_ROOT_WIN указывает на корень проекта (TayfaNew)
# .tayfa внутри проекта содержит common/, boss/ и т.д.
KOK_DIR = Path(__file__).resolve().parent  # TayfaNew/kok/
TAYFA_ROOT_WIN = KOK_DIR.parent  # TayfaNew/
TAYFA_DATA_DIR = TAYFA_ROOT_WIN / ".tayfa"  # TayfaNew/.tayfa/ — данные Tayfa


def _to_wsl_path(path) -> str:
    """Конвертирует путь в WSL-формат. Работает и из Windows, и из WSL."""
    p = str(path).replace("\\", "/")
    # Исправляем артефакт двойной конвертации: /mnt//nt/c/... -> /mnt/c/...
    if "/mnt//nt/" in p:
        p = p.replace("/mnt//nt/", "/mnt/")
    if p.startswith("/mnt/"):
        return p  # уже WSL-путь
    if len(p) >= 2 and p[1] == ":":
        # Windows-путь: C:/Foo/Bar -> /mnt/c/Foo/Bar
        return "/mnt/" + p[0].lower() + p[2:]
    # Обработка UNC/нестандартных путей: //nt/c/... -> /mnt/c/...
    import re
    m = re.match(r"^/{1,2}nt/([a-zA-Z])/(.*)", p)
    if m:
        return "/mnt/" + m.group(1).lower() + "/" + m.group(2)
    return p  # fallback


TAYFA_ROOT_WSL = _to_wsl_path(TAYFA_ROOT_WIN)

# Fallback-пути (для обратной совместимости, когда проект не выбран)
# TAYFA_DATA_DIR указывает на .tayfa в корне проекта Tayfa
_FALLBACK_PERSONEL_DIR = TAYFA_DATA_DIR
_FALLBACK_PERSONEL_WSL = _to_wsl_path(TAYFA_DATA_DIR)


def get_personel_dir() -> Path:
    """Путь к .tayfa текущего проекта (Windows). Fallback: старый Personel."""
    project = get_current_project()
    if project:
        return Path(project["path"]) / TAYFA_DIR_NAME
    return _FALLBACK_PERSONEL_DIR


def get_personel_wsl() -> str:
    """Путь к .tayfa текущего проекта (WSL). Fallback: старый Personel."""
    project = get_current_project()
    if project:
        return _to_wsl_path(Path(project["path"])) + "/" + TAYFA_DIR_NAME
    return _FALLBACK_PERSONEL_WSL


def get_project_dir() -> Path | None:
    """Путь к корню текущего проекта (Windows). None если проект не выбран."""
    project = get_current_project()
    return Path(project["path"]) if project else None


def get_project_wsl() -> str | None:
    """Путь к корню текущего проекта (WSL). None если проект не выбран."""
    project = get_current_project()
    return _to_wsl_path(Path(project["path"])) if project else None


def get_agent_workdir() -> str:
    """workdir для агентов — корень проекта (WSL), не .tayfa."""
    project = get_current_project()
    if project:
        return _to_wsl_path(Path(project["path"]))
    return _FALLBACK_PERSONEL_WSL  # fallback


# Legacy aliases (для совместимости с существующим кодом, вычисляются динамически)
# НЕ использовать в новом коде — вызывайте функции напрямую
PERSONEL_DIR = _FALLBACK_PERSONEL_DIR  # legacy, используйте get_personel_dir()
PERSONEL_WSL = _FALLBACK_PERSONEL_WSL  # legacy, используйте get_personel_wsl()
TASKS_FILE = PERSONEL_DIR / "boss" / "tasks.md"  # единая доска задач (legacy)
SKILLS_DIR = PERSONEL_DIR / "common" / "skills"  # skills внутри Personel/common/skills/

# COMMON_DIR для импорта модулей — используем template_tayfa/common из папки kok
# (это исходники Tayfa, не данные проекта)
TEMPLATE_COMMON_DIR = KOK_DIR / "template_tayfa" / "common"
COMMON_DIR = PERSONEL_DIR / "common"  # legacy — путь к common текущего проекта

# Подключаем модули управления сотрудниками и задачами из template (исходники Tayfa)
sys.path.insert(0, str(TEMPLATE_COMMON_DIR))
sys.path.insert(0, str(Path(__file__).parent))  # для settings_manager и project_manager
from employee_manager import get_employees as _get_employees, get_employee, register_employee, remove_employee, set_employees_file
from task_manager import (
    create_task, create_backlog, update_task_status,
    set_task_result, get_tasks, get_task, get_next_agent,
    create_sprint, get_sprints, get_sprint, update_sprint_status,
    update_sprint_release,  # для обновления спринта после релиза
    STATUSES as TASK_STATUSES, SPRINT_STATUSES,
    set_tasks_file,  # для установки пути к tasks.json текущего проекта
)
from chat_history_manager import (
    save_message as save_chat_message,
    get_history as get_chat_history,
    clear_history as clear_chat_history,
    set_tayfa_dir as set_chat_history_tayfa_dir,
)
from settings_manager import (
    load_settings, update_settings, get_orchestrator_port,
    get_current_version, get_next_version, save_version,
)
from project_manager import (
    list_projects, get_project, add_project, remove_project,
    get_current_project, set_current_project, init_project,
    open_project, get_tayfa_dir, has_tayfa, TAYFA_DIR_NAME
)
from git_manager import (
    router as git_router,
    run_git_command,
    create_sprint_branch,
    check_git_state,
    commit_task,
    release_sprint,
)

ORCHESTRATOR_PORT = 8008
CURSOR_CLI_PROMPT_FILE = TAYFA_ROOT_WIN / ".cursor_cli_prompt.txt"  # временный файл для промпта в WSL
CURSOR_CHATS_FILE = TAYFA_ROOT_WIN / ".cursor_chats.json"  # agent_name -> chat_id (для --resume)
CURSOR_CLI_TIMEOUT = 600.0  # таймаут вызова Cursor CLI (секунды)
CURSOR_CREATE_CHAT_TIMEOUT = 30.0  # таймаут create-chat (секунды)

# ── Глобальное состояние ──────────────────────────────────────────────────────

wsl_process: subprocess.Popen | None = None
api_running: bool = False

# Задачи, которые сейчас выполняются агентами: { task_id: { agent, role, runtime, started_at } }
import time as _time
running_tasks: dict[str, dict] = {}


# ── Lifespan ──────────────────────────────────────────────────────────────────

async def _auto_open_browser():
    """Открыть браузер после запуска сервера (с небольшой задержкой)."""
    await asyncio.sleep(1.5)
    url = f"http://localhost:{ORCHESTRATOR_PORT}"
    print(f"  Открываю браузер: {url}")
    webbrowser.open(url)


def _init_files_for_current_project():
    """Инициализировать пути к tasks.json, employees.json и chat_history для текущего проекта (при запуске)."""
    project = get_current_project()
    if project:
        tayfa_path = get_tayfa_dir(project["path"])
        if tayfa_path:
            common_path = Path(tayfa_path) / "common"
            tasks_json_path = common_path / "tasks.json"
            employees_json_path = common_path / "employees.json"
            set_tasks_file(tasks_json_path)
            set_employees_file(employees_json_path)
            set_chat_history_tayfa_dir(tayfa_path)
            print(f"  tasks.json установлен: {tasks_json_path}")
            print(f"  employees.json установлен: {employees_json_path}")
            print(f"  chat_history_dir установлен: {tayfa_path}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Запуск и остановка фоновых задач."""
    # Устанавливаем пути к tasks.json и employees.json для текущего проекта
    _init_files_for_current_project()

    # Автозапуск Claude API сервера (WSL)
    print("  Запускаю Claude API сервер (WSL)...")
    result = start_claude_api()
    if result.get("status") == "started":
        print(f"  Claude API: запущен (pid={result.get('pid')})")
    elif result.get("status") == "already_running":
        print(f"  Claude API: уже работает (pid={result.get('pid')})")
    else:
        print(f"  Claude API: {result.get('status', 'ошибка')} — {result.get('detail', '')}")

    # Запускаем фоновую проверку статуса
    task = asyncio.create_task(health_check_loop())

    # Открыть браузер автоматически
    asyncio.create_task(_auto_open_browser())

    yield
    # Завершение
    task.cancel()
    stop_claude_api()


app = FastAPI(title="Tayfa Orchestrator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(git_router)


# ── Утилиты ───────────────────────────────────────────────────────────────────

def win_to_wsl_path(win_path: str) -> str:
    """Конвертирует Windows путь в WSL путь. Работает и из Windows, и из WSL."""
    p = str(win_path).replace("\\", "/")
    # Исправляем артефакт двойной конвертации: /mnt//nt/c/... -> /mnt/c/...
    if "/mnt//nt/" in p:
        p = p.replace("/mnt//nt/", "/mnt/")
    if p.startswith("/mnt/"):
        return p  # уже WSL-путь
    if len(p) >= 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:]
    # Обработка UNC/нестандартных путей: //nt/c/... -> /mnt/c/...
    import re
    m = re.match(r"^/{1,2}nt/([a-zA-Z])/(.*)", p)
    if m:
        return "/mnt/" + m.group(1).lower() + "/" + m.group(2)
    return p


async def health_check_loop():
    """Периодическая проверка доступности Claude API."""
    global api_running
    while True:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{CLAUDE_API_URL}/agents")
                api_running = resp.status_code == 200
        except Exception:
            api_running = False
        await asyncio.sleep(5)


async def call_claude_api(method: str, path: str, json_data: dict | None = None, timeout: float = 600.0) -> dict:
    """Отправка запроса к Claude API серверу. При 4xx/5xx от API пробрасывает HTTPException."""
    url = f"{CLAUDE_API_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url)
            elif method == "POST":
                resp = await client.post(url, json=json_data)
            elif method == "DELETE":
                resp = await client.delete(url)
            else:
                raise ValueError(f"Unknown method: {method}")
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    detail = body.get("detail", body.get("message", resp.text or "Not Found"))
                except Exception:
                    detail = resp.text or "Not Found"
                if resp.status_code == 404:
                    detail = (
                        "Агент не найден в Claude API. Запустите сервер (кнопка «Запустить сервер»), "
                        "затем нажмите «Обеспечить агентов», чтобы создать агентов (boss, hr и др.)."
                    )
                raise HTTPException(status_code=resp.status_code, detail=detail)
            return resp.json()
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Claude API сервер недоступен. Запустите его.")
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail="Claude API: таймаут ожидания ответа агента.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка Claude API: {str(e)}")


# ── WSL / uvicorn управление ─────────────────────────────────────────────────

def start_claude_api() -> dict:
    """Запускает Claude API сервер в WSL."""
    global wsl_process

    if wsl_process and wsl_process.poll() is None:
        return {"status": "already_running", "pid": wsl_process.pid}

    wsl_script = (
        'source ~/claude_venv/bin/activate && '
        f'cd "{TAYFA_ROOT_WSL}" && '
        'python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788'
    )

    try:
        wsl_process = subprocess.Popen(
            ["wsl", "bash"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        # Передаём скрипт через stdin и закрываем его, чтобы bash начал выполнение
        wsl_process.stdin.write(wsl_script.encode("utf-8"))
        wsl_process.stdin.close()
        return {"status": "started", "pid": wsl_process.pid}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def stop_claude_api() -> dict:
    """Останавливает Claude API сервер."""
    global wsl_process, api_running

    if wsl_process and wsl_process.poll() is None:
        try:
            if sys.platform == "win32":
                wsl_process.terminate()
            else:
                os.kill(wsl_process.pid, signal.SIGTERM)
            wsl_process.wait(timeout=10)
        except Exception:
            wsl_process.kill()
        wsl_process = None
        api_running = False
        return {"status": "stopped"}
    return {"status": "not_running"}


# ── Cursor CLI через WSL ─────────────────────────────────────────────────────

def _cursor_cli_base_script() -> str:
    """Базовый префикс для команд Cursor CLI в WSL: PATH и cd в проект.
    Не используем $PATH — в WSL он может содержать Windows-пути с пробелами и скобками (Program Files (x86)),
    из-за чего bash даёт syntax error near unexpected token `('.
    """
    return (
        'export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" && '
        f'cd "{TAYFA_ROOT_WSL}"'
    )


def _load_cursor_chats() -> dict[str, str]:
    """Читает маппинг agent_name -> chat_id из .cursor_chats.json."""
    if not CURSOR_CHATS_FILE.exists():
        return {}
    try:
        data = json.loads(CURSOR_CHATS_FILE.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cursor_chats(chats: dict[str, str]) -> None:
    """Сохраняет маппинг agent_name -> chat_id в .cursor_chats.json."""
    CURSOR_CHATS_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_cursor_cli_create_chat() -> dict:
    """
    Создаёт чат в Cursor CLI: agent --print --output-format json create-chat.
    Возвращает { "success": bool, "chat_id": str | None, "raw": str, "stderr": str }.
    Парсит JSON из stdout (ожидаются поля chat_id, session_id или id).
    """
    wsl_script = (
        f"{_cursor_cli_base_script()} && "
        "agent --print --output-format json create-chat"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "wsl", "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(TAYFA_ROOT_WIN),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=wsl_script.encode("utf-8")),
            timeout=CURSOR_CREATE_CHAT_TIMEOUT,
        )
        out_text = (stdout or b"").decode("utf-8", errors="replace").strip()
        err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        return {
            "success": False,
            "chat_id": None,
            "raw": "",
            "stderr": f"Таймаут {CURSOR_CREATE_CHAT_TIMEOUT} с.",
        }
    except Exception as e:
        return {"success": False, "chat_id": None, "raw": "", "stderr": str(e)}

    chat_id = None
    if out_text and proc.returncode == 0:
        try:
            obj = json.loads(out_text)
            chat_id = (
                obj.get("chat_id")
                or obj.get("session_id")
                or obj.get("id")
                or (obj.get("result") if isinstance(obj.get("result"), str) else None)
            )
            if isinstance(chat_id, dict):
                chat_id = chat_id.get("id") or chat_id.get("chat_id")
        except Exception:
            pass
        # create-chat может вернуть только UUID строкой (не JSON)
        if not chat_id and out_text.strip():
            line = out_text.strip().splitlines()[0].strip()
            if len(line) == 36 and line.count("-") == 4:
                chat_id = line

    return {
        "success": proc.returncode == 0 and bool(chat_id),
        "chat_id": str(chat_id) if chat_id else None,
        "raw": out_text,
        "stderr": err_text,
    }


def _build_cursor_cli_prompt(agent_name: str, user_prompt: str) -> str:
    """Собирает промпт для Cursor CLI: роль (имя агента) + контекст + задание."""
    return (
        f"Роль: {agent_name}. Рабочая папка: Personel (project/ — код, common/Rules/ — правила). "
        f"Учти контекст из {agent_name}/prompt.md и common/Rules/. Задание: {user_prompt}"
    )


async def ensure_cursor_chat(agent_name: str) -> tuple[str | None, str]:
    """
    Возвращает (chat_id, error): chat_id для агента из .cursor_chats.json или создаёт новый (create-chat).
    При ошибке: (None, сообщение_об_ошибке).
    """
    chats = _load_cursor_chats()
    if agent_name in chats and chats[agent_name]:
        return chats[agent_name], ""
    create_result = await run_cursor_cli_create_chat()
    if not create_result.get("success") or not create_result.get("chat_id"):
        err = create_result.get("stderr") or create_result.get("raw") or "create-chat не вернул chat_id"
        return None, err
    chat_id = create_result["chat_id"]
    chats[agent_name] = chat_id
    _save_cursor_chats(chats)
    return chat_id, ""


async def run_cursor_cli(agent_name: str, user_prompt: str, use_chat: bool = True) -> dict:
    """
    Запускает Cursor CLI в WSL в headless-режиме.
    Если use_chat=True, предварительно обеспечивает чат для агента (create-chat при необходимости)
    и отправляет сообщение с --resume <chat_id>. Иначе — разовый вызов без --resume.
    Возвращает { "success": bool, "result": str, "stderr": str }.
    """
    full_prompt = _build_cursor_cli_prompt(agent_name, user_prompt)
    try:
        CURSOR_CLI_PROMPT_FILE.write_text(full_prompt, encoding="utf-8")
    except Exception as e:
        return {"success": False, "result": "", "stderr": f"Не удалось записать промпт: {e}"}

    chat_id = None
    chat_error = ""
    if use_chat:
        chat_id, chat_error = await ensure_cursor_chat(agent_name)
        if not chat_id and chat_error:
            # Не удалось получить чат — возвращаем ошибку сразу (не запускаем agent без --resume)
            return {
                "success": False,
                "result": "",
                "stderr": f"Не удалось получить чат Cursor для «{agent_name}»: {chat_error}",
            }

    # WSL: PATH, cd, затем agent с промптом из файла (экранируем кавычки в содержимом для bash)
    base = _cursor_cli_base_script()
    safe_id = (chat_id or "").replace("'", "'\"'\"'")
    resume_part = f" --resume '{safe_id}'" if chat_id else ""
    # Читаем промпт в переменную с экранированием " для bash, чтобы кавычки в тексте не ломали команду
    wsl_script = (
        f"{base} && "
        "content=$(cat .cursor_cli_prompt.txt | sed 's/\"/\\\\\"/g') && "
        f"agent -p --force{resume_part} --output-format json \"$content\""
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            "wsl", "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(TAYFA_ROOT_WIN),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=wsl_script.encode("utf-8")),
            timeout=CURSOR_CLI_TIMEOUT,
        )
        out_text = (stdout or b"").decode("utf-8", errors="replace").strip()
        err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        return {
            "success": False,
            "result": "",
            "stderr": f"Таймаут {CURSOR_CLI_TIMEOUT} с. Cursor CLI не успел завершиться.",
        }
    except Exception as e:
        return {"success": False, "result": "", "stderr": str(e)}
    finally:
        try:
            if CURSOR_CLI_PROMPT_FILE.exists():
                CURSOR_CLI_PROMPT_FILE.unlink()
        except Exception:
            pass

    # Если вывод в JSON (--output-format json), извлечь result
    result_text = out_text
    if out_text and proc.returncode == 0:
        try:
            obj = json.loads(out_text)
            if isinstance(obj, dict) and "result" in obj:
                result_text = obj.get("result") or result_text
        except Exception:
            pass

    return {
        "success": proc.returncode == 0,
        "result": result_text,
        "stderr": err_text,
    }


def _extract_md_section(text: str, section_title: str) -> str:
    """Извлекает из markdown блок от строки ## section_title до следующего ## или конца."""
    lines = text.splitlines()
    in_section = False
    result = []
    for line in lines:
        if line.strip().startswith("## ") and section_title.lower() in line.lower():
            in_section = True
            result.append(line)
            continue
        if in_section:
            if line.strip().startswith("## "):
                break
            result.append(line)
    return "\n".join(result).strip() if result else ""


def resolve_skill_path(skill_id: str) -> Path | None:
    """
    По идентификатору skill (например 'project-decomposer' или 'public/pptx')
    возвращает путь к SKILL.md в Tayfa/skills/<skill_id>/SKILL.md.
    """
    if not skill_id or not SKILLS_DIR.exists():
        return None
    # Нормализуем: слеши в разделители пути
    parts = skill_id.replace("\\", "/").strip("/").split("/")
    skill_dir = SKILLS_DIR.joinpath(*parts)
    skill_file = skill_dir / "SKILL.md"
    return skill_file if skill_file.exists() else None


def load_skill_content(skill_id: str) -> str | None:
    """Читает содержимое SKILL.md для указанного skill. Возвращает None, если не найден."""
    path = resolve_skill_path(skill_id)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def compose_system_prompt(agent_name: str, use_skills: list[str] | None = None) -> str | None:
    """
    Собирает системный промпт из prompt.md + блок «Навыки» из profile.md (и skills.md).
    Если передан use_skills, добавляет содержимое SKILL.md из Tayfa/skills/<id>/ в конец промпта.
    Возвращает None, если папки/файлов нет — тогда используется только system_prompt_file из запроса.
    """
    personel_dir = get_personel_dir()
    agent_dir = personel_dir / agent_name
    prompt_file = agent_dir / "prompt.md"
    profile_file = agent_dir / "profile.md"
    skills_file = agent_dir / "skills.md"

    if not prompt_file.exists():
        return None

    prompt_text = prompt_file.read_text(encoding="utf-8")

    # Добавляем секцию о структуре рабочей папки (если есть текущий проект)
    project = get_current_project()
    if project:
        structure_info = f"""## Структура рабочей папки

Ты работаешь в проекте **{project['name']}**.

- **Корень проекта**: `./` (текущая рабочая папка, workdir)
- **.tayfa/**: папка команды Tayfa
  - `.tayfa/common/`: общие файлы (tasks.json, employees.json, Rules/)
  - `.tayfa/{agent_name}/`: твоя личная папка (income/, done/, notes.md)
  - `.tayfa/boss/`, `.tayfa/hr/`: папки других агентов

Код проекта находится в корне (src/, package.json и т.д.), а файлы команды — в .tayfa/.

"""
        prompt_text = structure_info + prompt_text

    skills_parts = []
    if profile_file.exists():
        profile_text = profile_file.read_text(encoding="utf-8")
        skills_block = _extract_md_section(profile_text, "Навыки")
        if skills_block:
            skills_parts.append(skills_block)
    if skills_file.exists():
        skills_parts.append(skills_file.read_text(encoding="utf-8").strip())

    if skills_parts:
        skills_content = "\n\n".join(skills_parts)
        skills_section = "## Твои навыки\n\n" + skills_content
        pattern = r"(##\s+Твои навыки\s*\n)(.*?)(?=\n##\s|\Z)"
        if re.search(pattern, prompt_text, re.DOTALL):
            prompt_text = re.sub(pattern, r"\1\n" + skills_content + "\n\n", prompt_text, flags=re.DOTALL)
        else:
            prompt_text = prompt_text.rstrip() + "\n\n" + skills_section + "\n"

    # Явно подключённые skills из Tayfa/skills/
    if use_skills:
        injected = []
        for skill_id in use_skills:
            content = load_skill_content(skill_id.strip())
            if content:
                injected.append(f"<!-- Skill: {skill_id} -->\n{content}")
        if injected:
            prompt_text = prompt_text.rstrip() + "\n\n## Активные skills (Cursor Agent Skills)\n\n" + "\n\n---\n\n".join(injected) + "\n"

    return prompt_text.strip()


# ── API Эндпоинты ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Отдаём главную страницу."""
    index_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_status():
    """Статус системы."""
    global api_running
    wsl_running = wsl_process is not None and wsl_process.poll() is None
    project = get_current_project()
    return {
        "wsl_running": wsl_running,
        "api_running": api_running,
        "wsl_pid": wsl_process.pid if wsl_running else None,
        "tayfa_root": str(TAYFA_ROOT_WIN),
        "api_url": CLAUDE_API_URL,
        "current_project": project,
        "has_project": project is not None,
    }


# ── Настройки ─────────────────────────────────────────────────────────────────


@app.get("/api/settings")
async def get_settings():
    """Получить все настройки."""
    try:
        return load_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения настроек: {str(e)}")


@app.post("/api/settings")
async def post_settings(data: dict):
    """Обновить настройки (partial update)."""
    if not data:
        raise HTTPException(status_code=400, detail="Пустой запрос")

    try:
        new_settings, error = update_settings(data)
        if error:
            raise HTTPException(status_code=400, detail=error)
        return {"status": "updated", "settings": new_settings}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения настроек: {str(e)}")


# ── Проекты ───────────────────────────────────────────────────────────────────


@app.get("/api/projects")
async def api_list_projects():
    """Список всех проектов и текущий проект."""
    return {
        "projects": list_projects(),
        "current": get_current_project()
    }


@app.get("/api/current-project")
async def api_current_project():
    """Получить текущий проект."""
    project = get_current_project()
    return {"project": project}


@app.post("/api/projects/open")
async def api_open_project(data: dict):
    """
    Открыть проект: init_project + set_current_project.
    Пересоздаёт агентов с новым workdir.
    Body: {"path": "C:\\Projects\\App"}
    """
    path = data.get("path")
    print(f"[api_open_project] Запрос: path={path}")

    if not path:
        raise HTTPException(status_code=400, detail="Нужен path")

    # Открываем проект (init + set_current)
    result = open_project(path)
    print(f"[api_open_project] open_project result: {result}")

    # Если ошибка (папка не существует и т.п.) — возвращаем её
    if result.get("status") == "error":
        print(f"[api_open_project] Ошибка: {result.get('error')}")
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Ошибка открытия проекта")
        )

    # Устанавливаем пути к tasks.json, employees.json и chat_history для текущего проекта
    tayfa_path = result.get("tayfa_path")
    if tayfa_path:
        common_path = Path(tayfa_path) / "common"
        tasks_json_path = common_path / "tasks.json"
        employees_json_path = common_path / "employees.json"
        set_tasks_file(tasks_json_path)
        set_employees_file(employees_json_path)
        set_chat_history_tayfa_dir(tayfa_path)
        print(f"[api_open_project] tasks.json установлен: {tasks_json_path}")
        print(f"[api_open_project] employees.json установлен: {employees_json_path}")
        print(f"[api_open_project] chat_history_dir установлен: {tayfa_path}")

    # Пересоздаём агентов с новым workdir (ошибки не блокируют открытие проекта)
    try:
        await kill_all_agents(stop_server=False)
        await ensure_agents()
    except Exception as e:
        print(f"[api_open_project] Ошибка при пересоздании агентов (не критично): {e}")

    response = {
        "status": "opened",
        "project": result.get("project"),
        "init": result.get("init"),
        "tayfa_path": result.get("tayfa_path")
    }
    print(f"[api_open_project] Ответ: {response}")
    return response


@app.post("/api/projects/init")
async def api_init_project(data: dict):
    """
    Инициализировать проект (создать .tayfa если нет).
    Body: {"path": "C:\\Projects\\App"}
    """
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Нужен path")

    result = init_project(path)
    return result


@app.post("/api/projects/add")
async def api_add_project(data: dict):
    """
    Добавить проект в список (без открытия).
    Body: {"path": "...", "name": "..."}
    """
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Нужен path")

    name = data.get("name")
    result = add_project(path, name)
    return result


@app.post("/api/projects/remove")
async def api_remove_project(data: dict):
    """
    Удалить проект из списка (не удаляет файлы).
    Body: {"path": "..."}
    """
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Нужен path")

    result = remove_project(path)
    return result


@app.post("/api/start-server")
async def start_server():
    """Запустить Claude API сервер в WSL."""
    result = start_claude_api()
    # Ждём пока сервер стартанёт
    if result["status"] == "started":
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient(timeout=2) as client:
                    resp = await client.get(f"{CLAUDE_API_URL}/agents")
                    if resp.status_code == 200:
                        global api_running
                        api_running = True
                        result["api_ready"] = True
                        return result
            except Exception:
                continue
        result["api_ready"] = False
    return result


@app.post("/api/stop-server")
async def stop_server():
    """Остановить Claude API сервер."""
    return stop_claude_api()


def _get_agent_runtimes(agent_name: str) -> list[str]:
    """Возвращает runtimes для агента. По умолчанию ['claude', 'cursor']."""
    return ["claude", "cursor"]


def _agents_from_registry() -> dict:
    """Список агентов из employees.json (у которых есть prompt.md)."""
    result = {}
    employees = _get_employees()
    personel_dir = get_personel_dir()
    agent_workdir = get_agent_workdir()

    for emp_name, emp_data in employees.items():
        prompt_file = personel_dir / emp_name / "prompt.md"
        if prompt_file.exists():
            result[emp_name] = {
                "system_prompt_file": f"{emp_name}/prompt.md",
                "workdir": agent_workdir,
                "runtimes": _get_agent_runtimes(emp_name),
                "role": emp_data.get("role", ""),
            }

    return result


@app.get("/api/agents")
async def list_agents():
    """
    Список агентов: из employees.json (у которых есть prompt.md).
    Если Claude API доступен — дополняем session_id и др. для агентов из API.
    """
    result = _agents_from_registry()
    employees = _get_employees()
    try:
        raw = await call_claude_api("GET", "/agents")
        if isinstance(raw, dict):
            for name, config in raw.items():
                if name not in employees:
                    continue
                cfg = dict(config) if isinstance(config, dict) else {}
                cfg["runtimes"] = _get_agent_runtimes(name)
                cfg["role"] = employees[name].get("role", "")
                result[name] = cfg
    except HTTPException:
        for name in result:
            result[name]["runtimes"] = _get_agent_runtimes(name)
    except Exception:
        for name in result:
            result[name]["runtimes"] = _get_agent_runtimes(name)
    return result


@app.post("/api/create-agent")
async def create_agent(data: dict):
    """Создать агента (передать JSON без prompt). Поддерживается use_skills — массив имён skills из Tayfa/skills/."""
    payload = dict(data)
    use_skills = payload.pop("use_skills", None)
    name = payload.get("name")
    if name and payload.get("system_prompt_file"):
        composed = compose_system_prompt(name, use_skills=use_skills)
        if composed is not None:
            payload.pop("system_prompt_file", None)
            payload["system_prompt"] = composed
    return await call_claude_api("POST", "/run", json_data=payload)


@app.post("/api/send-prompt")
async def send_prompt(data: dict):
    """Отправить промт агенту (Claude API). Сохраняет историю в chat_history.json."""
    agent_name = data.get("name") or data.get("agent")
    prompt_text = data.get("prompt", "")
    task_id = data.get("task_id")

    start_time = _time.time()
    api_result = await call_claude_api("POST", "/run", json_data=data, timeout=600.0)
    duration_sec = _time.time() - start_time

    # Сохраняем в историю чата
    if agent_name and prompt_text:
        save_chat_message(
            agent_name=agent_name,
            prompt=prompt_text,
            result=api_result.get("result", ""),
            runtime="claude",
            cost_usd=api_result.get("cost_usd"),
            duration_sec=duration_sec,
            task_id=task_id,
            success=True,
            extra={"num_turns": api_result.get("num_turns")},
        )

    return api_result


@app.post("/api/send-prompt-cursor")
async def send_prompt_cursor(data: dict):
    """
    Отправить промпт в Cursor CLI через WSL. Сохраняет историю в chat_history.json.
    Чат агента: из .cursor_chats.json (см. GET /api/cursor-chats) или создаётся create-chat при первой отправке.
    Команда в WSL: agent -p --force [--resume <chat_id>] --output-format json "<промпт из файла>".
    """
    name = data.get("name") or data.get("agent")
    prompt_text = data.get("prompt") or ""
    task_id = data.get("task_id")

    if not name or not prompt_text:
        raise HTTPException(status_code=400, detail="Нужны name и prompt")

    use_chat = data.get("use_chat", True)

    start_time = _time.time()
    result = await run_cursor_cli(name, prompt_text, use_chat=use_chat)
    duration_sec = _time.time() - start_time

    # Сохраняем в историю чата
    save_chat_message(
        agent_name=name,
        prompt=prompt_text,
        result=result.get("result", ""),
        runtime="cursor",
        cost_usd=None,  # Cursor CLI не возвращает стоимость
        duration_sec=duration_sec,
        task_id=task_id,
        success=result.get("success", False),
        extra={"stderr": result.get("stderr")} if result.get("stderr") else None,
    )

    return result


@app.post("/api/cursor-create-chat")
async def cursor_create_chat(data: dict):
    """
    Создать чат в Cursor CLI для одного агента: agent --print --output-format json create-chat.
    Chat_id сохраняется в .cursor_chats.json и используется при отправке (--resume).
    """
    name = data.get("name") or data.get("agent")
    if not name:
        raise HTTPException(status_code=400, detail="Нужно name агента")
    create_result = await run_cursor_cli_create_chat()
    if not create_result.get("success"):
        return {
            "success": False,
            "agent": name,
            "chat_id": None,
            "error": create_result.get("stderr") or create_result.get("raw"),
        }
    chat_id = create_result["chat_id"]
    chats = _load_cursor_chats()
    chats[name] = chat_id
    _save_cursor_chats(chats)
    return {"success": True, "agent": name, "chat_id": chat_id}


@app.post("/api/cursor-create-chats")
async def cursor_create_chats():
    """
    Создать чаты в Cursor CLI для всех сотрудников из employees.json, у которых runtimes включает cursor.
    Для каждого вызывается create-chat, chat_id сохраняется в .cursor_chats.json.
    """
    chats = _load_cursor_chats()
    employees = _get_employees()
    agents_with_cursor = [
        name for name in employees
        if "cursor" in _get_agent_runtimes(name)
    ]
    results = []
    for agent_name in agents_with_cursor:
        if agent_name in chats and chats[agent_name]:
            results.append({"agent": agent_name, "chat_id": chats[agent_name], "created": False})
            continue
        create_result = await run_cursor_cli_create_chat()
        if create_result.get("success") and create_result.get("chat_id"):
            chat_id = create_result["chat_id"]
            chats[agent_name] = chat_id
            results.append({"agent": agent_name, "chat_id": chat_id, "created": True})
        else:
            results.append({
                "agent": agent_name,
                "chat_id": None,
                "created": False,
                "error": create_result.get("stderr") or create_result.get("raw"),
            })
    _save_cursor_chats(chats)
    return {"results": results, "chats": chats}


@app.get("/api/cursor-chats")
async def list_cursor_chats():
    """Список привязок агент -> chat_id (из .cursor_chats.json)."""
    return {"chats": _load_cursor_chats()}


@app.post("/api/reset-agent")
async def reset_agent(data: dict):
    """Сбросить память агента."""
    payload = {"name": data["name"], "reset": True}
    return await call_claude_api("POST", "/run", json_data=payload)


@app.delete("/api/agents/{name}")
async def delete_agent(name: str):
    """Удалить агента."""
    return await call_claude_api("DELETE", f"/agents/{name}")


@app.post("/api/kill-all-agents")
async def kill_all_agents(stop_server: bool = True):
    """Удалить всех агентов в Claude API и опционально остановить сервер."""
    deleted = []
    errors = []
    try:
        agents = await call_claude_api("GET", "/agents")
    except HTTPException:
        agents = {}
    if isinstance(agents, dict):
        names = list(agents.keys())
    elif isinstance(agents, list):
        names = agents
    else:
        names = []
    for name in names:
        try:
            await call_claude_api("DELETE", f"/agents/{name}")
            deleted.append(name)
        except Exception as e:
            errors.append({"name": name, "error": str(e)})
    stop_result = None
    if stop_server:
        stop_result = stop_claude_api()
    return {
        "deleted": deleted,
        "errors": errors,
        "stop_server": stop_result,
    }


@app.post("/api/refresh-agent-prompt/{name}")
async def refresh_agent_prompt(name: str, data: dict = Body(default_factory=dict)):
    """Пересобрать системный промпт агента из prompt.md + profile.md (навыки) и опционально use_skills, затем обновить агента."""
    use_skills = data.get("use_skills")
    composed = compose_system_prompt(name, use_skills=use_skills)
    if composed is None:
        raise HTTPException(
            status_code=404,
            detail=f"Нет prompt.md в {name}/",
        )
    payload = {
        "name": name,
        "system_prompt": composed,
        "workdir": get_agent_workdir(),
    }
    return await call_claude_api("POST", "/run", json_data=payload)


@app.get("/api/tasks")
async def get_tasks_board():
    """Единая доска задач — содержимое Personel/boss/tasks.md. Пользователь видит все задачи."""
    if not TASKS_FILE.exists():
        return {"content": "# Задачи\n\nДоска задач пуста. Boss ведёт учёт в этом файле.", "path": str(TASKS_FILE)}
    try:
        content = TASKS_FILE.read_text(encoding="utf-8")
        return {"content": content, "path": str(TASKS_FILE)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ensure-agents")
async def ensure_agents():
    """Проверить и создать агентов для всех сотрудников из employees.json, у которых есть prompt.md."""
    results = []
    personel_dir = get_personel_dir()
    agent_workdir = get_agent_workdir()

    # Получаем текущий список агентов из Claude API
    try:
        agents = await call_claude_api("GET", "/agents")
    except Exception:
        agents = {}

    # Проверяем employees.json — создаём агентов для сотрудников без запущенного агента
    # Для уже существующих — проверяем и исправляем workdir (защита от /mnt//nt/ и т.п.)
    employees = _get_employees()
    for emp_name in employees:
        if isinstance(agents, dict) and emp_name in agents:
            existing = agents[emp_name]
            if isinstance(existing, dict) and existing.get("workdir") != agent_workdir:
                # Workdir отличается — обновляем (исправляем битый путь)
                try:
                    await call_claude_api("POST", "/run", json_data={
                        "name": emp_name,
                        "workdir": agent_workdir,
                    })
                    results.append({"agent": emp_name, "status": "workdir_fixed",
                                    "old_workdir": existing.get("workdir"), "new_workdir": agent_workdir})
                except Exception:
                    results.append({"agent": emp_name, "status": "already_exists", "workdir_mismatch": True})
            else:
                results.append({"agent": emp_name, "status": "already_exists"})
            continue

        # Проверяем наличие prompt.md
        prompt_file = personel_dir / emp_name / "prompt.md"
        if not prompt_file.exists():
            results.append({
                "agent": emp_name,
                "status": "skipped",
                "detail": f"Нет файла {emp_name}/prompt.md",
            })
            continue

        # Собираем системный промпт и создаём агента
        try:
            composed = compose_system_prompt(emp_name)
            payload = {
                "name": emp_name,
                "workdir": agent_workdir,
                "allowed_tools": "Read Edit Bash",
            }
            if composed is not None:
                payload["system_prompt"] = composed
            else:
                payload["system_prompt_file"] = f"{emp_name}/prompt.md"

            create_result = await call_claude_api("POST", "/run", json_data=payload)
            results.append({
                "agent": emp_name,
                "status": "created",
                "detail": create_result,
            })
        except Exception as e:
            results.append({
                "agent": emp_name,
                "status": "error",
                "detail": str(e),
            })

    return {"results": results, "current_agents": list(agents.keys()) if isinstance(agents, dict) else agents}


# ── Сотрудники (employees.json) ──────────────────────────────────────────────


@app.get("/api/employees")
async def api_get_employees():
    """Список всех зарегистрированных сотрудников из employees.json."""
    return {"employees": _get_employees()}


@app.get("/api/employees/{name}")
async def api_get_employee(name: str):
    """Получить данные одного сотрудника."""
    emp = get_employee(name)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Сотрудник '{name}' не найден")
    return {"name": name, **emp}


@app.post("/api/employees")
async def api_register_employee(data: dict):
    """Зарегистрировать нового сотрудника (обычно через create_employee.py)."""
    name = data.get("name")
    role = data.get("role", "")
    if not name:
        raise HTTPException(status_code=400, detail="Нужно поле name")
    result = register_employee(name, role)
    return result


@app.delete("/api/employees/{name}")
async def api_remove_employee(name: str):
    """Удалить сотрудника из реестра."""
    result = remove_employee(name)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Сотрудник '{name}' не найден")
    return result


# ── История чата (chat_history) ───────────────────────────────────────────────


@app.get("/api/chat-history/{agent_name}")
async def api_get_chat_history(agent_name: str, limit: int = 50, offset: int = 0):
    """
    Получить историю переписки с агентом.
    Параметры: ?limit=50&offset=0 (пагинация)
    Response: {"messages": [...], "total": 123, "limit": 50, "offset": 0}
    """
    # Проверяем, что агент существует
    emp = get_employee(agent_name)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Агент '{agent_name}' не найден")

    history = get_chat_history(agent_name, limit=limit, offset=offset)
    return history


@app.post("/api/chat-history/{agent_name}/clear")
async def api_clear_chat_history(agent_name: str):
    """
    Очистить историю переписки с агентом.
    Response: {"status": "cleared", "deleted_count": 50}
    """
    # Проверяем, что агент существует
    emp = get_employee(agent_name)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Агент '{agent_name}' не найден")

    result = clear_chat_history(agent_name)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Ошибка очистки истории"))
    return result


# ── Спринты ──────────────────────────────────────────────────────────────────


@app.get("/api/sprints")
async def api_get_sprints():
    """Список всех спринтов."""
    sprints = get_sprints()
    return {"sprints": sprints, "statuses": SPRINT_STATUSES}


@app.get("/api/sprints/{sprint_id}")
async def api_get_sprint(sprint_id: str):
    """Получить спринт по ID."""
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail=f"Спринт {sprint_id} не найден")
    return sprint


@app.post("/api/sprints")
async def api_create_sprint(data: dict):
    """
    Создать спринт. Body: {"title": "...", "description": "...", "created_by": "boss"}.

    Автоматически создаёт git-ветку sprint/SXXX от main.

    Требования:
    - Git должен быть инициализирован (иначе HTTP 400)
    - Должна существовать ветка main или master
    - Если remote недоступен — ветка создаётся локально с предупреждением

    Response:
    - Успех: {"id": "S002", "git_branch": "sprint/S002", "git_status": "ok"}
    - Предупреждение: {..., "git_warning": "Remote недоступен..."}
    - Ошибка: HTTP 400 с detail
    """
    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Нужно поле title")

    # Сначала проверяем состояние git (до создания спринта)
    git_state = check_git_state()
    if git_state["error"]:
        raise HTTPException(status_code=400, detail=git_state["error"])

    # Создаём спринт
    sprint = create_sprint(
        title=title,
        description=data.get("description", ""),
        created_by=data.get("created_by", "boss"),
    )

    sprint_id = sprint.get("id")
    if not sprint_id:
        return sprint  # Спринт создан, но без ID (не должно случиться)

    # Создаём git-ветку для спринта
    branch_result = create_sprint_branch(sprint_id)

    if branch_result["success"]:
        sprint["git_branch"] = branch_result["branch"]
        sprint["git_status"] = branch_result["git_status"]
        if branch_result["git_warning"]:
            sprint["git_warning"] = branch_result["git_warning"]
    else:
        # Ошибка создания ветки — возвращаем ошибку (спринт уже создан, но без ветки)
        # TODO: возможно, стоит удалять спринт при ошибке git
        raise HTTPException(
            status_code=400,
            detail=f"Спринт {sprint_id} создан, но не удалось создать git-ветку: {branch_result['error']}"
        )

    return sprint


@app.put("/api/sprints/{sprint_id}/status")
async def api_update_sprint_status(sprint_id: str, data: dict):
    """Изменить статус спринта. Body: {"status": "завершён"}."""
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Нужно поле status")
    result = update_sprint_status(sprint_id, new_status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/sprints/{sprint_id}/release-ready")
async def api_sprint_release_ready(sprint_id: str):
    """
    Проверить, готов ли спринт к релизу.
    Возвращает: ready (bool), pending_tasks (list), next_version (str).
    """
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail=f"Спринт {sprint_id} не найден")

    # Получаем все задачи спринта (кроме финализирующей)
    tasks = get_tasks(sprint_id=sprint_id)
    pending_tasks = [
        {"id": t["id"], "title": t["title"], "status": t["status"]}
        for t in tasks
        if not t.get("is_finalize") and t["status"] != "выполнена"
    ]

    ready = len(pending_tasks) == 0
    next_version = get_next_version() if ready else None

    return {
        "sprint_id": sprint_id,
        "sprint_title": sprint.get("title", ""),
        "ready": ready,
        "pending_tasks": pending_tasks,
        "next_version": next_version,
        "current_status": sprint.get("status"),
    }


# ── Автокоммит ────────────────────────────────────────────────────────────────


def _get_current_branch() -> str | None:
    """Возвращает имя текущей git-ветки или None при ошибке."""
    result = run_git_command(["branch", "--show-current"])
    if result["success"] and result["stdout"]:
        return result["stdout"].strip()
    return None


def _get_commit_hash() -> str | None:
    """Возвращает короткий hash последнего коммита или None."""
    result = run_git_command(["rev-parse", "--short", "HEAD"])
    if result["success"] and result["stdout"]:
        return result["stdout"].strip()
    return None


def _get_files_changed_count() -> int:
    """Возвращает количество изменённых файлов в последнем коммите."""
    result = run_git_command(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
    if result["success"] and result["stdout"]:
        return len([f for f in result["stdout"].strip().split("\n") if f])
    return 0


def _perform_auto_commit(task_id: str, task: dict) -> dict:
    """
    Выполняет автоматический git-коммит при переводе задачи на проверку.

    Возвращает dict с результатом:
    - success: bool
    - hash: str (при успехе)
    - message: str (сообщение коммита)
    - files_changed: int (количество изменённых файлов)
    - error: str (при ошибке)
    """
    # 1. Проверяем, инициализирован ли git
    from project_manager import get_project_dir
    project_dir = get_project_dir()
    if project_dir is None:
        return {
            "success": False,
            "error": "Проект не выбран"
        }

    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {
            "success": False,
            "error": "Git не инициализирован в проекте"
        }

    # 2. Проверяем текущую ветку (если задача привязана к спринту)
    sprint_id = task.get("sprint_id")
    if sprint_id:
        current_branch = _get_current_branch()
        expected_branch = f"sprint/{sprint_id}"
        if current_branch and current_branch != expected_branch:
            # Предупреждение, но не блокируем коммит
            # (ветка может быть другой по легитимным причинам)
            pass  # Можно добавить warning в лог

    # 3. Формируем сообщение коммита
    task_title = task.get("title", "Task completed")
    developer = task.get("developer", "")

    commit_message = f"{task_id}: {task_title}"
    if developer:
        commit_message += f"\n\nСтатус: на_проверке\nРазработчик: {developer}"
    else:
        commit_message += f"\n\nСтатус: на_проверке"

    # 4. git add -A
    add_result = run_git_command(["add", "-A"])
    if not add_result["success"]:
        return {
            "success": False,
            "error": f"git add failed: {add_result.get('stderr', 'Unknown error')}"
        }

    # 5. Проверяем, есть ли что коммитить (git status --porcelain)
    status_result = run_git_command(["status", "--porcelain"])
    if status_result["success"] and not status_result["stdout"].strip():
        # Нет изменений — это не ошибка
        return {
            "success": True,
            "hash": "",
            "message": f"{task_id}: {task_title}",
            "files_changed": 0
        }

    # 6. git commit
    commit_result = run_git_command(["commit", "-m", commit_message])

    # 7. Обрабатываем результат
    stdout_stderr = (commit_result.get("stdout", "") + commit_result.get("stderr", "")).lower()

    if commit_result["success"]:
        # Успешный коммит
        commit_hash = _get_commit_hash() or ""
        files_changed = _get_files_changed_count()

        return {
            "success": True,
            "hash": commit_hash,
            "message": f"{task_id}: {task_title}",
            "files_changed": files_changed
        }
    elif "nothing to commit" in stdout_stderr:
        # Нет изменений — не ошибка
        return {
            "success": True,
            "hash": "",
            "message": f"{task_id}: {task_title}",
            "files_changed": 0
        }
    else:
        # Реальная ошибка коммита
        return {
            "success": False,
            "error": commit_result.get("stderr") or commit_result.get("stdout") or "Commit failed"
        }


# ── Задачи (tasks.json) ─────────────────────────────────────────────────────


@app.get("/api/tasks-list")
async def api_get_tasks(status: str | None = None, sprint_id: str | None = None):
    """Список задач. Опционально фильтр ?status=новая&sprint_id=S001."""
    tasks = get_tasks(status=status, sprint_id=sprint_id)
    return {"tasks": tasks, "statuses": TASK_STATUSES}


@app.get("/api/tasks-list/{task_id}")
async def api_get_task(task_id: str):
    """Получить одну задачу по ID."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Задача {task_id} не найдена")
    return task


@app.post("/api/tasks-list")
async def api_create_tasks(data: dict):
    """
    Создать задачу или бэклог задач.
    Если в data есть "tasks" (список) — создаёт бэклог.
    Иначе — одну задачу из полей title, description, customer, developer, tester, sprint_id, depends_on.
    """
    if "tasks" in data and isinstance(data["tasks"], list):
        results = create_backlog(data["tasks"])
        return {"created": results, "count": len(results)}

    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Нужно поле title")

    task = create_task(
        title=title,
        description=data.get("description", ""),
        customer=data.get("customer", "boss"),
        developer=data.get("developer", ""),
        tester=data.get("tester", ""),
        sprint_id=data.get("sprint_id", ""),
        depends_on=data.get("depends_on"),
    )
    return task


@app.put("/api/tasks-list/{task_id}/status")
async def api_update_task_status(task_id: str, data: dict):
    """
    Изменить статус задачи. Body: {"status": "в_работе"}.

    Автоматические git-действия:
    - "на_проверке": git add -A && git commit "TXXX: Заголовок"
    - "выполнена": если все задачи спринта выполнены → merge в main + tag + push

    При переходе в "на_проверке" возвращает git_commit:
    {
        "success": true,
        "hash": "abc1234",
        "message": "T008: Заголовок задачи",
        "files_changed": 5
    }
    При ошибке: {"success": false, "error": "описание ошибки"}
    """
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Нужно поле status")
    result = update_task_status(task_id, new_status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    task = get_task(task_id)
    if not task:
        return result

    # Автокоммит при переходе в "на_проверке"
    if new_status == "на_проверке":
        git_commit_result = _perform_auto_commit(task_id, task)
        result["git_commit"] = git_commit_result

    # Автофинализация при переходе в "выполнена"
    if new_status == "выполнена":
        sprint_id = task.get("sprint_id")
        if sprint_id:
            # Проверяем, все ли задачи спринта выполнены
            sprint_tasks = get_tasks(sprint_id=sprint_id)
            all_done = all(t["status"] in ("выполнена", "отменена") for t in sprint_tasks)

            if all_done:
                # Финализация: используем release_sprint() из git_manager
                release_result = release_sprint(sprint_id)

                if release_result["success"]:
                    result["sprint_finalized"] = {
                        "sprint_id": sprint_id,
                        "version": release_result["version"],
                        "merged": True,
                        "pushed": release_result["pushed"],
                        "tag": release_result["version"],
                        "commit": release_result["commit"],
                    }
                else:
                    result["sprint_finalize_error"] = release_result.get("error", "Release failed")

    return result


@app.put("/api/tasks-list/{task_id}/result")
async def api_set_task_result(task_id: str, data: dict):
    """Записать результат работы в задачу. Body: {"result": "текст"}."""
    result_text = data.get("result", "")
    result = set_task_result(task_id, result_text)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/running-tasks")
async def api_running_tasks():
    """Список задач, которые сейчас выполняются агентами (в процессе trigger)."""
    now = _time.time()
    result = {}
    for tid, info in running_tasks.items():
        result[tid] = {
            **info,
            "elapsed_seconds": round(now - info.get("started_at", now)),
        }
    return {"running": result}


@app.post("/api/tasks-list/{task_id}/trigger")
async def api_trigger_task(task_id: str, data: dict = Body(default_factory=dict)):
    """
    Запустить следующего агента для задачи.
    Определяет, кто должен работать по текущему статусу, и отправляет ему промпт.
    Поддерживает runtime: data.get("runtime", "claude") — "claude" или "cursor".
    """
    # Проверяем, не запущена ли задача уже
    if task_id in running_tasks:
        raise HTTPException(
            status_code=409,
            detail=f"Задача {task_id} уже выполняется агентом {running_tasks[task_id].get('agent', '?')}",
        )

    next_info = get_next_agent(task_id)
    if not next_info:
        raise HTTPException(
            status_code=400,
            detail="Задача не найдена или уже завершена / отменена",
        )

    agent_name = next_info["agent"]
    role_label = {"customer": "заказчик", "developer": "разработчик", "tester": "тестировщик"}.get(
        next_info["role"], next_info["role"]
    )
    task = next_info["task"]

    if not agent_name:
        raise HTTPException(
            status_code=400,
            detail=f"Не назначен {role_label} для задачи {task_id}",
        )

    # Проверяем, зарегистрирован ли агент
    emp = get_employee(agent_name)
    if not emp:
        raise HTTPException(
            status_code=400,
            detail=f"Агент '{agent_name}' не зарегистрирован в employees.json",
        )

    # Формируем промпт для агента
    prompt_parts = [
        f"Задача {task['id']}: {task['title']}",
        f"Описание: {task['description']}" if task.get("description") else "",
        f"Твоя роль: {role_label}",
        f"Текущий статус: {task['status']}",
    ]
    if task.get("result"):
        prompt_parts.append(f"Предыдущий результат: {task['result']}")

    prompt_parts.append("")
    if next_info["role"] == "customer":
        prompt_parts.append(
            "Ты — заказчик. Детализируй требования задачи. "
            "Когда закончишь, вызови:\n"
            f"  python common/task_manager.py result {task['id']} \"<подробное описание>\"\n"
            f"  python common/task_manager.py status {task['id']} в_работе"
        )
    elif next_info["role"] == "developer":
        prompt_parts.append(
            "Ты — разработчик. Выполни задачу согласно описанию. "
            "Когда закончишь, вызови:\n"
            f"  python common/task_manager.py result {task['id']} \"<описание что сделано>\"\n"
            f"  python common/task_manager.py status {task['id']} на_проверке"
        )
    elif next_info["role"] == "tester":
        prompt_parts.append(
            "Ты — тестировщик. Проверь результат работы. "
            "Если всё хорошо, вызови:\n"
            f"  python common/task_manager.py result {task['id']} \"<результат проверки>\"\n"
            f"  python common/task_manager.py status {task['id']} выполнена\n"
            "Если есть проблемы:\n"
            f"  python common/task_manager.py result {task['id']} \"<описание проблем>\"\n"
            f"  python common/task_manager.py status {task['id']} в_работе"
        )

    full_prompt = "\n".join(p for p in prompt_parts if p is not None)

    runtime = data.get("runtime", "claude")

    # Регистрируем задачу как «выполняется»
    running_tasks[task_id] = {
        "agent": agent_name,
        "role": role_label,
        "runtime": runtime,
        "started_at": _time.time(),
    }

    start_time = _time.time()
    try:
        if runtime == "cursor":
            result = await run_cursor_cli(agent_name, full_prompt)
            duration_sec = _time.time() - start_time

            # Сохраняем в историю чата
            save_chat_message(
                agent_name=agent_name,
                prompt=full_prompt,
                result=result.get("result", ""),
                runtime="cursor",
                cost_usd=None,
                duration_sec=duration_sec,
                task_id=task_id,
                success=result.get("success", False),
                extra={"role": role_label, "stderr": result.get("stderr")} if result.get("stderr") else {"role": role_label},
            )

            return {
                "task_id": task_id,
                "agent": agent_name,
                "role": role_label,
                "runtime": "cursor",
                "success": result.get("success", False),
                "result": result.get("result", ""),
                "stderr": result.get("stderr", ""),
            }
        else:
            # Claude API
            api_result = await call_claude_api("POST", "/run", json_data={
                "name": agent_name,
                "prompt": full_prompt,
            }, timeout=600.0)
            duration_sec = _time.time() - start_time

            # Сохраняем в историю чата
            save_chat_message(
                agent_name=agent_name,
                prompt=full_prompt,
                result=api_result.get("result", ""),
                runtime="claude",
                cost_usd=api_result.get("cost_usd"),
                duration_sec=duration_sec,
                task_id=task_id,
                success=True,
                extra={"role": role_label, "num_turns": api_result.get("num_turns")},
            )

            return {
                "task_id": task_id,
                "agent": agent_name,
                "role": role_label,
                "runtime": "claude",
                "success": True,
                "result": api_result.get("result", ""),
                "cost_usd": api_result.get("cost_usd"),
                "num_turns": api_result.get("num_turns"),
            }
    finally:
        # Убираем задачу из «выполняется» при любом исходе
        running_tasks.pop(task_id, None)


# ── Запуск ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"\n  Tayfa Orchestrator")
    print(f"  http://localhost:{ORCHESTRATOR_PORT}\n")
    uvicorn.run(app, host="0.0.0.0", port=ORCHESTRATOR_PORT)

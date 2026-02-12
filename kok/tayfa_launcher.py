"""
Tayfa Launcher — запускает app.py скрыто (без видимой консоли).

Этот файл компилируется в Tayfa.exe через PyInstaller:
    pyinstaller --onefile --noconsole --icon=static/tayfa-icon.ico --name=Tayfa ^
        --add-data "static/tayfa-icon.png;static" ^
        --hidden-import PIL._tkinter_finder ^
        tayfa_launcher.py
"""

import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime


def log(msg: str, log_file: Path):
    """Записывает сообщение в лог-файл."""
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass  # Игнорируем ошибки логирования


def main():
    # Определяем базовую директорию
    if getattr(sys, 'frozen', False):
        # Запущен как exe (PyInstaller)
        base_dir = Path(sys.executable).parent
    else:
        # Запущен как .py
        base_dir = Path(__file__).parent

    log_file = base_dir / 'tayfa_launcher.log'
    log(f"Tayfa Launcher started", log_file)
    log(f"base_dir = {base_dir}", log_file)

    # Проверяем наличие app.py
    app_py = base_dir / 'app.py'
    if not app_py.exists():
        log(f"ERROR: app.py not found at {app_py}", log_file)
        return 1

    log(f"Found app.py at: {app_py}", log_file)

    # Ищем Python в venv или системный
    venv_python = base_dir / 'venv' / 'Scripts' / 'python.exe'
    if venv_python.exists():
        python_exe = str(venv_python)
        log(f"Using venv Python: {python_exe}", log_file)
    else:
        # Ищем системный Python
        python_exe = 'python'
        log(f"venv not found, using system Python", log_file)

    # Показываем splash-анимацию перед запуском сервера
    try:
        from splash_animation import show_splash
        splash_result = show_splash()
        log(f"Splash animation: {'shown' if splash_result else 'skipped'}", log_file)
    except Exception as e:
        log(f"Splash animation error (ignored): {e}", log_file)

    # Запускаем app.py скрыто
    try:
        log(f"Starting app.py with {python_exe}...", log_file)

        # Копируем текущее окружение и добавляем venv
        env = os.environ.copy()
        venv_scripts = base_dir / 'venv' / 'Scripts'
        if venv_scripts.exists():
            env['PATH'] = str(venv_scripts) + os.pathsep + env.get('PATH', '')
            env['VIRTUAL_ENV'] = str(base_dir / 'venv')

        # CREATE_NO_WINDOW для полного скрытия
        CREATE_NO_WINDOW = 0x08000000

        # Логируем stderr в файл для отладки
        stderr_log = base_dir / 'tayfa_app.log'
        with open(stderr_log, 'w', encoding='utf-8') as err_file:
            subprocess.Popen(
                [python_exe, str(app_py)],
                creationflags=CREATE_NO_WINDOW,
                cwd=str(base_dir),
                env=env,
                stdout=err_file,
                stderr=err_file,
            )
        log(f"app.py started, logs in tayfa_app.log", log_file)
    except Exception as e:
        log(f"ERROR: {e}", log_file)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())

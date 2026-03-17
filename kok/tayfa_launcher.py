"""
Tayfa Launcher — launches app.py hidden (without a visible console).

This file is compiled into Tayfa.exe via PyInstaller:
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
    """Writes a message to the log file."""
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass  # Ignore logging errors


def main():
    # Determine the base directory
    if getattr(sys, 'frozen', False):
        # Running as exe (PyInstaller)
        base_dir = Path(sys.executable).parent
    else:
        # Running as .py
        base_dir = Path(__file__).parent

    log_file = base_dir / 'tayfa_launcher.log'
    log(f"Tayfa Launcher started", log_file)
    log(f"base_dir = {base_dir}", log_file)

    # Check that app.py exists
    app_py = base_dir / 'app.py'
    if not app_py.exists():
        log(f"ERROR: app.py not found at {app_py}", log_file)
        return 1

    log(f"Found app.py at: {app_py}", log_file)

    # Look for Python in venv or system
    venv_python = base_dir / 'venv' / 'Scripts' / 'python.exe'
    if venv_python.exists():
        python_exe = str(venv_python)
        log(f"Using venv Python: {python_exe}", log_file)
    else:
        # Look for system Python
        python_exe = 'python'
        log(f"venv not found, using system Python", log_file)

    # Start splash animation IN PARALLEL with the server
    splash_thread = None
    try:
        from splash_animation import start_splash_async
        splash_thread = start_splash_async()
        log(f"Splash animation started in background", log_file)
    except Exception as e:
        log(f"Splash animation error (ignored): {e}", log_file)

    # Launch app.py hidden (in parallel with the animation)
    try:
        log(f"Starting app.py with {python_exe}...", log_file)

        # Copy current environment and add venv
        env = os.environ.copy()
        venv_scripts = base_dir / 'venv' / 'Scripts'
        if venv_scripts.exists():
            env['PATH'] = str(venv_scripts) + os.pathsep + env.get('PATH', '')
            env['VIRTUAL_ENV'] = str(base_dir / 'venv')

        # CREATE_NO_WINDOW to fully hide the window
        CREATE_NO_WINDOW = 0x08000000

        # Open log file in APPEND mode (do not overwrite!)
        # The file stays open while the process is running
        stderr_log = base_dir / 'tayfa_app.log'
        err_file = open(stderr_log, 'a', encoding='utf-8')  # 'a' instead of 'w'!
        err_file.write(f"\n{'='*60}\n")
        err_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === Tayfa starting ===\n")
        err_file.flush()

        subprocess.Popen(
            [python_exe, str(app_py)],
            creationflags=CREATE_NO_WINDOW,
            cwd=str(base_dir),
            env=env,
            stdout=err_file,
            stderr=err_file,
        )
        # Do NOT close err_file — it will be closed when the launcher exits
        log(f"app.py started, logs in tayfa_app.log", log_file)
    except Exception as e:
        log(f"ERROR: {e}", log_file)
        import traceback
        log(f"TRACEBACK: {traceback.format_exc()}", log_file)
        return 1

    # Wait for the animation to finish (the server is already running in parallel)
    if splash_thread is not None:
        try:
            splash_thread.join(timeout=5.0)  # 5 sec max just in case
            log(f"Splash animation finished", log_file)
        except Exception:
            pass

    return 0


if __name__ == '__main__':
    sys.exit(main())

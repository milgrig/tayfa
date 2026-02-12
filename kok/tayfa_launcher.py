"""
Tayfa Launcher — запускает tayfa.bat скрыто (без видимой консоли).

Этот файл компилируется в Tayfa.exe через PyInstaller:
    pyinstaller --onefile --noconsole --icon=static/tayfa-icon.ico --name=Tayfa tayfa_launcher.py
"""

import subprocess
import sys
from pathlib import Path


def main():
    # Определяем путь к tayfa.bat
    # При запуске из exe: рядом с exe
    # При запуске из .py: рядом с .py
    if getattr(sys, 'frozen', False):
        # Запущен как exe (PyInstaller)
        base_dir = Path(sys.executable).parent
    else:
        # Запущен как .py
        base_dir = Path(__file__).parent

    bat_path = base_dir / 'tayfa.bat'

    if not bat_path.exists():
        # Попробуем найти в родительской папке
        bat_path = base_dir.parent / 'kok' / 'tayfa.bat'

    if not bat_path.exists():
        print(f"Ошибка: tayfa.bat не найден в {bat_path}")
        return 1

    # Запускаем tayfa.bat скрыто (CREATE_NO_WINDOW)
    # 0x08000000 = CREATE_NO_WINDOW — окно не создаётся
    try:
        subprocess.Popen(
            ['cmd', '/c', str(bat_path)],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            cwd=str(bat_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"Ошибка запуска: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())

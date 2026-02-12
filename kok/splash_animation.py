"""
Splash Animation Module для Tayfa
=================================
Показывает анимированный splash-экран при запуске приложения.

API:
    show_splash() -> bool  # Возвращает True если показан, False если пропущен

Особенности:
    - Использует tkinter (встроен в Python)
    - Совместим с PyInstaller
    - Graceful degradation при ошибках
"""

import os
import sys
import logging

# Настройка логирования
logger = logging.getLogger(__name__)


def _get_resource_path(relative_path: str) -> str:
    """
    Получить абсолютный путь к ресурсу.
    Работает как в обычном режиме, так и в frozen (PyInstaller).
    """
    # PyInstaller создаёт временную папку и сохраняет путь в _MEIPASS
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _can_show_splash() -> bool:
    """Проверить, можно ли показать splash-экран."""
    # Проверка на Linux без дисплея
    if sys.platform.startswith('linux'):
        display = os.environ.get('DISPLAY')
        if not display:
            logger.debug("DISPLAY не установлен, пропускаем splash")
            return False

    # Проверка доступности tkinter
    try:
        import tkinter as tk
        # Пробуем создать временный root для проверки
        test_root = tk.Tk()
        test_root.withdraw()
        test_root.destroy()
        return True
    except Exception as e:
        logger.debug(f"tkinter недоступен: {e}")
        return False


def show_splash() -> bool:
    """
    Показать splash-анимацию.

    Returns:
        bool: True если splash был показан, False если пропущен
    """
    # Проверяем возможность показа
    if not _can_show_splash():
        return False

    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError as e:
        logger.warning(f"Не удалось импортировать необходимые модули: {e}")
        return False

    # Параметры анимации
    WINDOW_SIZE = 256
    BG_COLOR = "#1a1d27"
    TOTAL_DURATION_MS = 1000
    FADE_IN_END = 300      # 0-300ms: fade-in
    FADE_OUT_START = 700   # 700-1000ms: fade-out
    FRAME_INTERVAL = 16    # ~60 FPS

    # Путь к изображению
    icon_path = _get_resource_path(os.path.join("static", "tayfa-icon.png"))

    if not os.path.exists(icon_path):
        logger.warning(f"Изображение не найдено: {icon_path}")
        return False

    try:
        # Создаём окно
        root = tk.Tk()
        root.withdraw()  # Скрываем пока не настроим

        # Настройки окна
        root.overrideredirect(True)  # Без рамки
        root.attributes('-topmost', True)  # Поверх всех окон
        root.configure(bg=BG_COLOR)

        # Прозрачность (Windows и некоторые Linux DE)
        try:
            root.attributes('-alpha', 0.0)
        except tk.TclError:
            pass  # Некоторые системы не поддерживают alpha

        # Центрирование на экране
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - WINDOW_SIZE) // 2
        y = (screen_height - WINDOW_SIZE) // 2
        root.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}+{x}+{y}")

        # Загружаем и масштабируем изображение
        img = Image.open(icon_path)

        # Масштабируем с сохранением пропорций, оставляя отступы
        img_size = int(WINDOW_SIZE * 0.75)  # 192px для 256px окна
        img.thumbnail((img_size, img_size), Image.Resampling.LANCZOS)

        # Центрируем на канве
        photo = ImageTk.PhotoImage(img)

        # Canvas для отображения
        canvas = tk.Canvas(
            root,
            width=WINDOW_SIZE,
            height=WINDOW_SIZE,
            bg=BG_COLOR,
            highlightthickness=0
        )
        canvas.pack()

        # Размещаем изображение по центру
        canvas.create_image(
            WINDOW_SIZE // 2,
            WINDOW_SIZE // 2,
            image=photo,
            anchor=tk.CENTER
        )

        # Показываем окно
        root.deiconify()
        root.update()

        # Переменные для анимации
        start_time = [None]  # Используем список для мутабельности в замыкании

        def animate():
            """Функция анимации, вызывается каждый кадр."""
            import time

            if start_time[0] is None:
                start_time[0] = time.time() * 1000  # В миллисекундах

            elapsed = time.time() * 1000 - start_time[0]

            if elapsed >= TOTAL_DURATION_MS:
                # Анимация завершена
                root.destroy()
                return

            # Вычисляем alpha в зависимости от фазы
            try:
                if elapsed < FADE_IN_END:
                    # Фаза 1: Fade-in (0 -> 1)
                    alpha = elapsed / FADE_IN_END
                elif elapsed < FADE_OUT_START:
                    # Фаза 2: Полная видимость
                    alpha = 1.0
                else:
                    # Фаза 3: Fade-out (1 -> 0)
                    alpha = 1.0 - (elapsed - FADE_OUT_START) / (TOTAL_DURATION_MS - FADE_OUT_START)

                # Ограничиваем значения
                alpha = max(0.0, min(1.0, alpha))
                root.attributes('-alpha', alpha)
            except tk.TclError:
                pass  # Игнорируем если окно уже закрыто

            # Планируем следующий кадр
            root.after(FRAME_INTERVAL, animate)

        # Запускаем анимацию
        root.after(0, animate)

        # Главный цикл
        root.mainloop()

        return True

    except Exception as e:
        logger.warning(f"Ошибка при показе splash: {e}")
        # Пытаемся закрыть окно если оно было создано
        try:
            root.destroy()
        except:
            pass
        return False


def main():
    """Точка входа для тестирования."""
    # Настраиваем логирование для тестов
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Запуск splash-анимации...")
    result = show_splash()
    print(f"Результат: {'показан' if result else 'пропущен'}")


if __name__ == '__main__':
    main()

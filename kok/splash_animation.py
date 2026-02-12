"""
Splash Animation Module для Tayfa
=================================
Показывает анимированный splash-экран при запуске приложения.

Анимация:
    - Буква T растёт от 0 до размера экрана за 3 секунды
    - Начинается от позиции курсора мыши (или центра экрана)
    - Прозрачный фон, буква полупрозрачная
    - В конце плавный fade-out

API:
    show_splash() -> bool  # Блокирующий вызов, возвращает True если показан
    start_splash_async() -> None  # Запускает анимацию в отдельном потоке

Особенности:
    - Использует tkinter (встроен в Python)
    - Совместим с PyInstaller
    - Graceful degradation при ошибках
"""

import os
import sys
import logging
import threading

# Настройка логирования
logger = logging.getLogger(__name__)


def _get_resource_path(relative_path: str) -> str:
    """
    Получить абсолютный путь к ресурсу.
    Работает как в обычном режиме, так и в frozen (PyInstaller).
    """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _can_show_splash() -> bool:
    """Проверить, можно ли показать splash-экран."""
    if sys.platform.startswith('linux'):
        display = os.environ.get('DISPLAY')
        if not display:
            logger.debug("DISPLAY не установлен, пропускаем splash")
            return False

    try:
        import tkinter as tk
        test_root = tk.Tk()
        test_root.withdraw()
        test_root.destroy()
        return True
    except Exception as e:
        logger.debug(f"tkinter недоступен: {e}")
        return False


def _get_mouse_position():
    """Получить текущую позицию курсора мыши."""
    try:
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return None, None


def show_splash() -> bool:
    """
    Показать splash-анимацию (блокирующий вызов).

    Буква T растёт от позиции курсора до размера экрана за 3 секунды.
    Фон прозрачный, буква полупрозрачная, в конце fade-out.

    Returns:
        bool: True если splash был показан, False если пропущен
    """
    if not _can_show_splash():
        return False

    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError as e:
        logger.warning(f"Не удалось импортировать необходимые модули: {e}")
        return False

    # Параметры анимации
    TOTAL_DURATION_MS = 3000    # 3 секунды
    FADE_OUT_START = 2500       # Последние 500ms — fade-out
    FRAME_INTERVAL = 16         # ~60 FPS
    BASE_OPACITY = 0.6          # Базовая прозрачность буквы T

    # Путь к изображению (только буква T без фона)
    icon_path = _get_resource_path(os.path.join("static", "tayfa-icon.png"))

    if not os.path.exists(icon_path):
        logger.warning(f"Изображение не найдено: {icon_path}")
        return False

    try:
        # Создаём окно
        root = tk.Tk()
        root.withdraw()

        # Получаем размеры экрана
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # Начальная позиция — курсор мыши или центр экрана
        mouse_x, mouse_y = _get_mouse_position()
        if mouse_x is None or mouse_y is None:
            start_x = screen_width // 2
            start_y = screen_height // 2
        else:
            start_x = mouse_x
            start_y = mouse_y

        # Настройки окна — полноэкранное, прозрачное
        root.overrideredirect(True)
        root.attributes('-topmost', True)
        root.geometry(f"{screen_width}x{screen_height}+0+0")

        # Прозрачный фон (Windows)
        # Используем специальный цвет для прозрачности
        TRANSPARENT_COLOR = "#010101"  # Почти чёрный, будет прозрачным
        root.configure(bg=TRANSPARENT_COLOR)

        try:
            root.attributes('-transparentcolor', TRANSPARENT_COLOR)
            root.attributes('-alpha', BASE_OPACITY)
        except tk.TclError:
            pass

        # Canvas на весь экран
        canvas = tk.Canvas(
            root,
            width=screen_width,
            height=screen_height,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0
        )
        canvas.pack()

        # Загружаем изображение
        original_img = Image.open(icon_path).convert("RGBA")

        # Храним текущее изображение и его ID на canvas
        current_photo = [None]
        image_id = [None]
        start_time = [None]

        def animate():
            """Функция анимации, вызывается каждый кадр."""
            import time

            if start_time[0] is None:
                start_time[0] = time.time() * 1000

            elapsed = time.time() * 1000 - start_time[0]

            if elapsed >= TOTAL_DURATION_MS:
                root.destroy()
                return

            try:
                # Прогресс анимации (0.0 -> 1.0)
                progress = elapsed / TOTAL_DURATION_MS

                # Размер изображения: от 1px до max(screen_width, screen_height)
                max_size = max(screen_width, screen_height)
                current_size = max(1, int(max_size * progress))

                # Позиция: интерполяция от start_x,start_y к центру экрана
                current_x = int(start_x + (screen_width // 2 - start_x) * progress)
                current_y = int(start_y + (screen_height // 2 - start_y) * progress)

                # Масштабируем изображение
                resized = original_img.resize(
                    (current_size, current_size),
                    Image.Resampling.LANCZOS
                )
                current_photo[0] = ImageTk.PhotoImage(resized)

                # Обновляем или создаём изображение на canvas
                if image_id[0] is None:
                    image_id[0] = canvas.create_image(
                        current_x, current_y,
                        image=current_photo[0],
                        anchor=tk.CENTER
                    )
                else:
                    canvas.coords(image_id[0], current_x, current_y)
                    canvas.itemconfig(image_id[0], image=current_photo[0])

                # Fade-out в конце
                if elapsed >= FADE_OUT_START:
                    fade_progress = (elapsed - FADE_OUT_START) / (TOTAL_DURATION_MS - FADE_OUT_START)
                    alpha = BASE_OPACITY * (1.0 - fade_progress)
                    alpha = max(0.0, min(BASE_OPACITY, alpha))
                    root.attributes('-alpha', alpha)

            except tk.TclError:
                return  # Окно закрыто

            root.after(FRAME_INTERVAL, animate)

        # Показываем окно и запускаем анимацию
        root.deiconify()
        root.update()
        root.after(0, animate)
        root.mainloop()

        return True

    except Exception as e:
        logger.warning(f"Ошибка при показе splash: {e}")
        try:
            root.destroy()
        except:
            pass
        return False


def start_splash_async() -> threading.Thread:
    """
    Запустить splash-анимацию в отдельном потоке.
    Позволяет серверу запускаться параллельно с анимацией.

    Returns:
        threading.Thread: Поток с анимацией (можно join() если нужно дождаться)
    """
    thread = threading.Thread(target=show_splash, daemon=True)
    thread.start()
    return thread


def main():
    """Точка входа для тестирования."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Запуск splash-анимации...")
    result = show_splash()
    print(f"Результат: {'показан' if result else 'пропущен'}")


if __name__ == '__main__':
    main()

"""
Splash Animation Module for Tayfa
==================================
Displays an animated splash screen on application startup.

Animation:
    - The letter T grows from 0 to screen size over 3 seconds
    - Starts from the mouse cursor position (or screen center)
    - Transparent background, semi-transparent letter
    - Smooth fade-out at the end

API:
    show_splash() -> bool  # Blocking call, returns True if shown
    start_splash_async() -> None  # Starts animation in a separate thread

Features:
    - Uses tkinter (built into Python)
    - Compatible with PyInstaller
    - Graceful degradation on errors
"""

import os
import sys
import logging
import threading

# Logging setup
logger = logging.getLogger(__name__)


def _get_resource_path(relative_path: str) -> str:
    """
    Get the absolute path to a resource.
    Works both in normal mode and in frozen mode (PyInstaller).
    """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _can_show_splash() -> bool:
    """Check whether the splash screen can be shown."""
    if sys.platform.startswith('linux'):
        display = os.environ.get('DISPLAY')
        if not display:
            logger.debug("DISPLAY is not set, skipping splash")
            return False

    try:
        import tkinter as tk
        test_root = tk.Tk()
        test_root.withdraw()
        test_root.destroy()
        return True
    except Exception as e:
        logger.debug(f"tkinter is not available: {e}")
        return False


def _get_mouse_position():
    """Get the current mouse cursor position."""
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
    Show the splash animation (blocking call).

    The letter T grows from the cursor position to screen size over 3 seconds.
    Transparent background, semi-transparent letter, fade-out at the end.

    Returns:
        bool: True if splash was shown, False if skipped
    """
    if not _can_show_splash():
        return False

    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError as e:
        logger.warning(f"Failed to import required modules: {e}")
        return False

    # Animation parameters
    TOTAL_DURATION_MS = 3000    # 3 seconds
    FADE_OUT_START = 2500       # Last 500ms — fade-out
    FRAME_INTERVAL = 16         # ~60 FPS
    BASE_OPACITY = 0.6          # Base opacity of the letter T

    # Path to image (letter T only, no background)
    icon_path = _get_resource_path(os.path.join("static", "tayfa-icon.png"))

    if not os.path.exists(icon_path):
        logger.warning(f"Image not found: {icon_path}")
        return False

    try:
        # Create window
        root = tk.Tk()
        root.withdraw()

        # Get screen dimensions
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # Starting position — mouse cursor or screen center
        mouse_x, mouse_y = _get_mouse_position()
        if mouse_x is None or mouse_y is None:
            start_x = screen_width // 2
            start_y = screen_height // 2
        else:
            start_x = mouse_x
            start_y = mouse_y

        # Window settings — fullscreen, transparent
        root.overrideredirect(True)
        root.attributes('-topmost', True)
        root.geometry(f"{screen_width}x{screen_height}+0+0")

        # Transparent background (Windows)
        # Use a special color for transparency
        TRANSPARENT_COLOR = "#010101"  # Near-black, will be transparent
        root.configure(bg=TRANSPARENT_COLOR)

        try:
            root.attributes('-transparentcolor', TRANSPARENT_COLOR)
            root.attributes('-alpha', BASE_OPACITY)
        except tk.TclError:
            pass

        # Full-screen canvas
        canvas = tk.Canvas(
            root,
            width=screen_width,
            height=screen_height,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0
        )
        canvas.pack()

        # Load the image
        original_img = Image.open(icon_path).convert("RGBA")

        # Store current image and its canvas ID
        current_photo = [None]
        image_id = [None]
        start_time = [None]

        def animate():
            """Animation function, called every frame."""
            import time

            if start_time[0] is None:
                start_time[0] = time.time() * 1000

            elapsed = time.time() * 1000 - start_time[0]

            if elapsed >= TOTAL_DURATION_MS:
                root.destroy()
                return

            try:
                # Animation progress (0.0 -> 1.0)
                progress = elapsed / TOTAL_DURATION_MS

                # Image size: from 1px to max(screen_width, screen_height)
                max_size = max(screen_width, screen_height)
                current_size = max(1, int(max_size * progress))

                # Position: interpolate from start_x,start_y to screen center
                current_x = int(start_x + (screen_width // 2 - start_x) * progress)
                current_y = int(start_y + (screen_height // 2 - start_y) * progress)

                # Scale the image
                resized = original_img.resize(
                    (current_size, current_size),
                    Image.Resampling.LANCZOS
                )
                current_photo[0] = ImageTk.PhotoImage(resized)

                # Update or create the image on the canvas
                if image_id[0] is None:
                    image_id[0] = canvas.create_image(
                        current_x, current_y,
                        image=current_photo[0],
                        anchor=tk.CENTER
                    )
                else:
                    canvas.coords(image_id[0], current_x, current_y)
                    canvas.itemconfig(image_id[0], image=current_photo[0])

                # Fade-out at the end
                if elapsed >= FADE_OUT_START:
                    fade_progress = (elapsed - FADE_OUT_START) / (TOTAL_DURATION_MS - FADE_OUT_START)
                    alpha = BASE_OPACITY * (1.0 - fade_progress)
                    alpha = max(0.0, min(BASE_OPACITY, alpha))
                    root.attributes('-alpha', alpha)

            except tk.TclError:
                return  # Window closed

            root.after(FRAME_INTERVAL, animate)

        # Show the window and start the animation
        root.deiconify()
        root.update()
        root.after(0, animate)
        root.mainloop()

        return True

    except Exception as e:
        logger.warning(f"Error showing splash: {e}")
        try:
            root.destroy()
        except:
            pass
        return False


def start_splash_async() -> threading.Thread:
    """
    Start the splash animation in a separate thread.
    Allows the server to start in parallel with the animation.

    Returns:
        threading.Thread: The animation thread (can join() if you need to wait)
    """
    thread = threading.Thread(target=show_splash, daemon=True)
    thread.start()
    return thread


def main():
    """Entry point for testing."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Starting splash animation...")
    result = show_splash()
    print(f"Result: {'shown' if result else 'skipped'}")


if __name__ == '__main__':
    main()

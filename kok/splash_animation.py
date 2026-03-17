"""
Splash Animation Module for Tayfa
==================================
Displays an animated 3D splash screen on application startup.

Animation:
    - Beautiful rotating 3D letter T
    - Smooth rotation around Y-axis
    - Transparent background (no background elements)
    - Elegant fade-in and fade-out
    - Glowing effect with gradient colors

API:
    show_splash() -> bool  # Blocking call, returns True if shown
    start_splash_async() -> None  # Starts animation in a separate thread

Features:
    - Uses Pygame for 3D rendering
    - Compatible with PyInstaller
    - Graceful degradation on errors
    - Pure 3D geometry (no images needed)
"""

import os
import sys
import logging
import threading
import math

# Logging setup
logger = logging.getLogger(__name__)


def _can_show_splash() -> bool:
    """Check whether the splash screen can be shown."""
    if sys.platform.startswith('linux'):
        display = os.environ.get('DISPLAY')
        if not display:
            logger.debug("DISPLAY is not set, skipping splash")
            return False

    try:
        import pygame
        pygame.init()
        pygame.quit()
        return True
    except Exception as e:
        logger.debug(f"Pygame is not available: {e}")
        return False


def _create_3d_letter_t(size: float = 100) -> list:
    """
    Create 3D vertices for the letter T.
    Returns list of (x, y, z) vertices.
    """
    vertices = []
    thickness = size * 0.2
    top_height = size * 0.8
    bottom_bar_width = size * 1.2

    # Top horizontal bar (T cross)
    # Front face
    vertices.append((-bottom_bar_width/2, top_height, -thickness/2))
    vertices.append((bottom_bar_width/2, top_height, -thickness/2))
    vertices.append((bottom_bar_width/2, top_height - thickness, -thickness/2))
    vertices.append((-bottom_bar_width/2, top_height - thickness, -thickness/2))

    # Back face
    vertices.append((-bottom_bar_width/2, top_height, thickness/2))
    vertices.append((bottom_bar_width/2, top_height, thickness/2))
    vertices.append((bottom_bar_width/2, top_height - thickness, thickness/2))
    vertices.append((-bottom_bar_width/2, top_height - thickness, thickness/2))

    # Vertical bar (T stem)
    # Front face
    center_offset = (bottom_bar_width/2 - thickness) / 2
    vertices.append((-thickness/2, top_height - thickness, -thickness/2))
    vertices.append((thickness/2, top_height - thickness, -thickness/2))
    vertices.append((thickness/2, -top_height, -thickness/2))
    vertices.append((-thickness/2, -top_height, -thickness/2))

    # Back face
    vertices.append((-thickness/2, top_height - thickness, thickness/2))
    vertices.append((thickness/2, top_height - thickness, thickness/2))
    vertices.append((thickness/2, -top_height, thickness/2))
    vertices.append((-thickness/2, -top_height, thickness/2))

    return vertices


def _rotate_vertex(vertex: tuple, angle_y: float) -> tuple:
    """Rotate a vertex around Y-axis by angle_y (in radians)."""
    x, y, z = vertex
    cos_a = math.cos(angle_y)
    sin_a = math.sin(angle_y)

    new_x = x * cos_a - z * sin_a
    new_z = x * sin_a + z * cos_a

    return (new_x, y, new_z)


def _project_3d_to_2d(vertex: tuple, screen_width: int, screen_height: int, distance: float = 500) -> tuple:
    """Project 3D vertex to 2D screen coordinates."""
    x, y, z = vertex

    # Perspective projection
    scale = distance / (distance + z)
    screen_x = int(screen_width / 2 + x * scale)
    screen_y = int(screen_height / 2 - y * scale)

    return (screen_x, screen_y, z)


def show_splash() -> bool:
    """
    Show the splash animation with rotating 3D letter T.

    Returns:
        bool: True if splash was shown, False if skipped
    """
    if not _can_show_splash():
        return False

    try:
        import pygame
        import numpy as np
    except ImportError as e:
        logger.warning(f"Failed to import required modules: {e}")
        return False

    # Animation parameters
    TOTAL_DURATION_MS = 3000    # 3 seconds
    FADE_OUT_START = 2500       # Last 500ms — fade-out
    FPS = 60
    FRAME_INTERVAL = 1000 // FPS

    try:
        pygame.init()

        # Get screen dimensions
        screen_info = pygame.display.Info()
        screen_width = screen_info.current_w
        screen_height = screen_info.current_h

        # Create fullscreen window with transparent background
        flags = pygame.FULLSCREEN | pygame.NOFRAME
        screen = pygame.display.set_mode((screen_width, screen_height), flags)
        pygame.display.set_caption("Tayfa Loading...")

        # Fill with black (will use colorkey for transparency on some systems)
        screen.fill((0, 0, 0))
        screen.set_colorkey((0, 0, 0))

        clock = pygame.time.Clock()

        # Create 3D letter T
        letter_t = _create_3d_letter_t(size=150)

        # Create a surface for rendering (we'll render to a smaller surface then scale)
        render_surface = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)

        start_time = None

        # Main animation loop
        running = True
        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

            # Get elapsed time
            if start_time is None:
                start_time = pygame.time.get_ticks()

            elapsed = pygame.time.get_ticks() - start_time

            if elapsed >= TOTAL_DURATION_MS:
                running = False
                break

            # Calculate progress (0.0 -> 1.0)
            progress = elapsed / TOTAL_DURATION_MS

            # Calculate rotation angle (continuous rotation)
            rotation_angle = progress * math.pi * 4  # 2 full rotations

            # Calculate opacity (fade in, then fade out)
            if progress < 0.2:
                # Fade in first 20%
                alpha = int(255 * (progress / 0.2))
            elif progress > 0.8:
                # Fade out last 20%
                fade_progress = (progress - 0.8) / 0.2
                alpha = int(255 * (1.0 - fade_progress))
            else:
                alpha = 255

            # Clear the render surface
            render_surface.fill((0, 0, 0, 0))

            # Project and draw 3D letter
            projected_vertices = []
            for vertex in letter_t:
                rotated = _rotate_vertex(vertex, rotation_angle)
                projected = _project_3d_to_2d(rotated, screen_width, screen_height)
                projected_vertices.append(projected)

            # Draw faces of the letter T
            # We'll draw simple quads for each face
            faces = [
                # Top bar front
                [0, 1, 2, 3],
                # Top bar back
                [4, 5, 6, 7],
                # Top bar sides
                [0, 1, 5, 4],
                [1, 2, 6, 5],
                [2, 3, 7, 6],
                [3, 0, 4, 7],
                # Stem front
                [8, 9, 10, 11],
                # Stem back
                [12, 13, 14, 15],
                # Stem sides
                [8, 9, 13, 12],
                [9, 10, 14, 13],
                [10, 11, 15, 14],
                [11, 8, 12, 15],
            ]

            # Draw with gradient coloring based on z-depth
            for face in faces:
                points = []
                z_values = []

                for idx in face:
                    if idx < len(projected_vertices):
                        sx, sy, sz = projected_vertices[idx]
                        points.append((sx, sy))
                        z_values.append(sz)

                if len(points) == 4:
                    # Calculate average z for depth sorting
                    avg_z = sum(z_values) / len(z_values)

                    # Color based on depth and progress
                    # Gradient from cyan to magenta
                    color_progress = (avg_z + 150) / 300  # Normalize z
                    color_progress = max(0, min(1, color_progress))

                    # Gradient: cyan -> blue -> magenta
                    if color_progress < 0.5:
                        r = int(0 + (100 - 0) * (color_progress * 2))
                        g = int(255 - (255 - 100) * (color_progress * 2))
                        b = int(255)
                    else:
                        r = int(100 + (255 - 100) * ((color_progress - 0.5) * 2))
                        g = int(100 - 100 * ((color_progress - 0.5) * 2))
                        b = int(255 - (255 - 150) * ((color_progress - 0.5) * 2))

                    color = (r, g, b, alpha)

                    # Draw polygon
                    try:
                        pygame.draw.polygon(render_surface, color, points)
                        # Add edge for better definition
                        pygame.draw.polygon(render_surface, (255, 255, 255, int(alpha * 0.3)), points, 2)
                    except (ValueError, IndexError):
                        pass  # Skip if polygon is invalid

            # Blit the render surface to the screen
            screen.blit(render_surface, (0, 0))

            pygame.display.flip()
            clock.tick(FPS)

        pygame.quit()
        return True

    except Exception as e:
        logger.warning(f"Error showing splash: {e}")
        try:
            pygame.quit()
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

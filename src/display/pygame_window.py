# src/display/pygame_window.py
"""
pygame_window.py — Wayland-compatible fullscreen display backend.

Wraps pygame initialisation, the game loop tick, and clean shutdown.
The Renderer draws onto the Surface this module provides.

Usage:
    window = PygameWindow(width=1920, height=1080)
    with window:
        while window.is_running():
            window.handle_events()
            renderer.draw(flights)
            window.flip()
"""

from __future__ import annotations

import os
import sys

# Must be set BEFORE pygame import — tells SDL2 to use native Wayland,
# not XWayland fallback which breaks on pure Wayland compositors.
os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame


class PygameWindow:
    """
    Manages a borderless fullscreen pygame window for use as a wallpaper.

    Attributes:
        surface: The pygame Surface to draw onto. Pass this to Renderer.
        width, height: Screen dimensions.
    """

    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30) -> None:
        self.width   = width
        self.height  = height
        self.fps     = fps
        self.surface: pygame.Surface | None = None
        self._clock: pygame.time.Clock | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Context manager — use `with PygameWindow() as w:`
    # ------------------------------------------------------------------

    def __enter__(self) -> "PygameWindow":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Initialise pygame and open the fullscreen window."""
        pygame.init()

        # NOFRAME = no title bar/borders; looks like a wallpaper
        # FULLSCREEN = covers entire display
        flags = pygame.NOFRAME | pygame.FULLSCREEN

        try:
            self.surface = pygame.display.set_mode(
                (self.width, self.height), flags
            )
        except pygame.error as e:
            # Common failure: Wayland compositor not running or SDL2
            # wayland backend not installed.
            print(
                f"[pygame_window] Failed to open display: {e}\n"
                "Hint: ensure SDL2 Wayland backend is installed:\n"
                "  sudo apt install libsdl2-2.0-0\n"
                "And that WAYLAND_DISPLAY is set in your environment."
            )
            sys.exit(1)

        pygame.display.set_caption("Flight Radar Wallpaper")
        pygame.mouse.set_visible(False)          # hide cursor over wallpaper
        self._clock   = pygame.time.Clock()
        self._running = True

    def close(self) -> None:
        """Shut down pygame cleanly."""
        self._running = False
        pygame.mouse.set_visible(True)
        pygame.quit()

    # ------------------------------------------------------------------
    # Per-frame API
    # ------------------------------------------------------------------

    def handle_events(self) -> None:
        """
        Process the pygame event queue.
        Sets is_running() to False if the user quits or presses Escape.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._running = False
            elif event.type == pygame.VIDEORESIZE:
                # Wayland may send resize events; notify renderer
                self.width  = event.w
                self.height = event.h

    def flip(self) -> None:
        """Present the current frame and tick the FPS limiter."""
        pygame.display.flip()
        if self._clock:
            self._clock.tick(self.fps)

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def verify_wayland_driver() -> bool:
        """
        Returns True if pygame is using the native Wayland SDL2 driver.
        Call after open() to confirm you're not on XWayland fallback.
        """
        return pygame.display.get_driver() == "wayland"
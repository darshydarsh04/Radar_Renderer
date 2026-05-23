# Display
SCREEN_W, SCREEN_H = 1920, 1080
FULLSCREEN = True
DISPLAY_MODE = "wayland"   # tells main.py which backend to use

# Force SDL2 to use Wayland (not XWayland fallback)
import os
os.environ["SDL_VIDEODRIVER"] = "wayland"
os.environ["SDL_AUDIODRIVER"] = "dummy"   # no audio needed
# src/config.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

SCREEN_W, SCREEN_H = 1920, 1080
BBOX = (22.0, 45.0, 30.0, 60.0)   # lat_min, lon_min, lat_max, lon_max (UAE)
POLL_INTERVAL = 10
FPS = 30

COLORS = {
    "background": (10, 10, 30),
    "plane":      (0, 200, 255),
    "trail":      (0, 100, 130),
    "text":       (200, 200, 200),
}
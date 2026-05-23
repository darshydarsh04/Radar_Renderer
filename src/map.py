# src/map.py
from src.config import SCREEN_W, SCREEN_H, BBOX

def project(lon: float, lat: float) -> tuple[int, int]:
    """Equirectangular projection: geo coords → screen pixels."""
    lat_min, lon_min, lat_max, lon_max = BBOX
    x = int((lon - lon_min) / (lon_max - lon_min) * SCREEN_W)
    y = int((lat_max - lat) / (lat_max - lat_min) * SCREEN_H)  # y flipped
    return x, y

def in_bbox(lon: float, lat: float) -> bool:
    lat_min, lon_min, lat_max, lon_max = BBOX
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max
import os
os.environ["SDL_VIDEODRIVER"] = "wayland"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import threading
import time

from src.config   import SCREEN_W, SCREEN_H, FPS
from src.fetcher  import fetch_flights
from src.renderer import Renderer
from src.airports import AirportDB
from src.routes   import RouteCache

flights     = []
lock        = threading.Lock()
airport_db  = AirportDB()
route_cache = RouteCache()

# Shared bbox so poll_loop always fetches the current region
current_bbox = [(22.0, 45.0, 30.0, 60.0)]  # list so it's mutable from thread
bbox_lock    = threading.Lock()


def poll_loop():
    while True:
        with bbox_lock:
            bbox = current_bbox[0]
        new_flights = fetch_flights(bbox)
        with lock:
            flights.clear()
            flights.extend(new_flights)
        for f in new_flights:
            if f.callsign:
                route_cache.request(f.callsign)
        time.sleep(10)


def main():
    threading.Thread(target=airport_db.load, daemon=True).start()

    pygame.init()
    screen   = pygame.display.set_mode(
        (SCREEN_W, SCREEN_H), pygame.NOFRAME | pygame.FULLSCREEN
    )
    renderer = Renderer(screen, location="dubai")
    clock    = pygame.time.Clock()

    threading.Thread(target=poll_loop, daemon=True).start()

    loc_keys = {
        pygame.K_1: "dubai",
        pygame.K_2: "london",
        pygame.K_3: "newyork",
        pygame.K_4: "tokyo",
        pygame.K_5: "paris",
        pygame.K_6: "sydney",
        pygame.K_7: "singapore",
    }

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return

                # Location switch — update renderer AND poll bbox
                if event.key in loc_keys:
                    renderer.set_location(loc_keys[event.key])
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox
                    with lock:
                        flights.clear()   # clear stale flights immediately

                # Toggle airport mode
                if event.key == pygame.K_0:
                    renderer.toggle_airport_mode()
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox
                    with lock:
                        flights.clear()

                # Zoom
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    renderer.zoom(0.75)
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox

                if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    renderer.zoom(1.33)
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox

                if event.key in (pygame.K_r, pygame.K_BACKSPACE):
                    renderer.reset_zoom()
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox

                # Pan
                lat_span = renderer.bbox[2] - renderer.bbox[0]
                lon_span = renderer.bbox[3] - renderer.bbox[1]
                step_lat = lat_span * 0.20
                step_lon = lon_span * 0.20

                if event.key == pygame.K_UP:
                    renderer.pan( step_lat, 0)
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox
                if event.key == pygame.K_DOWN:
                    renderer.pan(-step_lat, 0)
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox
                if event.key == pygame.K_LEFT:
                    renderer.pan(0, -step_lon)
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox
                if event.key == pygame.K_RIGHT:
                    renderer.pan(0,  step_lon)
                    with bbox_lock:
                        current_bbox[0] = renderer.bbox

            if event.type == pygame.MOUSEWHEEL:
                if event.y > 0:
                    renderer.zoom(0.85)
                elif event.y < 0:
                    renderer.zoom(1.18)
                with bbox_lock:
                    current_bbox[0] = renderer.bbox

        route_cache.process_queue()

        with lock:
            current_flights = list(flights)

        airports_in_view = []
        if airport_db.loaded:
            lat_min, lon_min, lat_max, lon_max = renderer.bbox
            airports_in_view = airport_db.in_bbox(lat_min, lon_min, lat_max, lon_max)

        renderer.draw(current_flights, airports_in_view, route_cache, airport_db)
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
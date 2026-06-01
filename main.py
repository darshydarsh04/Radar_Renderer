import os
os.environ["SDL_VIDEODRIVER"] = "wayland"

import pygame
from src.config import SCREEN_W, SCREEN_H, FPS
from src.fetcher import fetch_flights
from src.renderer import Renderer
import threading, time


flights = []
lock = threading.Lock()

def poll_loop():
    while True:
        new_flights = fetch_flights()
        with lock:
            flights.clear()
            flights.extend(new_flights)
        time.sleep(10)

def main():
    pygame.init()

    # Borderless fullscreen — looks like a wallpaper
    flags = pygame.NOFRAME | pygame.FULLSCREEN
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    pygame.display.set_caption("Flight Wallpaper")

    # Start background polling thread
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()

    renderer = Renderer(screen)
    clock = pygame.time.Clock()

    renderer.set_location("Edinburgh Airport")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return

        with lock:
            current_flights = list(flights)

        renderer.draw(current_flights)
        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()
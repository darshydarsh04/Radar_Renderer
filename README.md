# Flight Radar Wallpaper



A live flight radar for Ubuntu (GNOME on Wayland), built in Python with Pygame. It pulls real-time aircraft positions from the [OpenSky Network](https://opensky-network.org/) API and draws them on an animated circular radar, with a flight list panel on the left.

## Commands
Commands 
- **location london**	Jump to a city preset (locations lists them; Tab completes)
- **goto 51.47 -0.45 1**	Centre on any coordinates, with the radius in degrees of latitude
- **mode airport / mode city**	Airport close-up or city view
- **zoom in / zoom out**	Change the visible area by 1.33x
- **zoom in 2**	Show half the area
- **zoom reset**	Back to the preset view
- **pan north, pan w 0.5**	Move the view by a fraction of what is visible
- **map on/off**	City skyline background (no argument toggles it)
- **airports on/off**	Airport markers
- **routes off**	Skip route lookups, so reloads are much faster (routes 5 sets a lookup limit)
- **size 2560x1440**	Image resolution; set it to your real screen
- **status**	Show the current settings
- **reload (or r)**	Fetch data, render a new image, set it as the wallpaper and delete the old one


## Features

- **Live data**: aircraft positions, heading, altitude and speed from OpenSky, polled every 10 seconds
- **Circular radar**: rotating sweep, range rings, pulse animation and a compass rose
- **Plane icons and trails**: heading-aware icons coloured by speed, with fading position trails
- **Airports**: large and medium airports plotted from a local `airports.csv`
- **Routes**: origin and destination per flight (fetched lazily and cached), drawn as lines on the radar
- **Flight panel**: callsign, route, flight level and speed for every aircraft in view
- **Zoom and pan**: change the visible area live

## new Features, may have bugs
- **Two view modes**: city/regional view and airport close-up view
- **City silhouettes**: rough skyline behind the radar for each preset city

## Requirements

- Ubuntu with GNOME on Wayland (`echo $XDG_SESSION_TYPE` should print `wayland`)
- Python 3.10+
- SDL2 with the Wayland backend

```bash
sudo apt install libsdl2-2.0-0 python3-pip
pip install -r requirements.txt
```

`requirements.txt`:

```
pygame>=2.5
requests>=2.31
pytest>=8.0
```

## Setup

1. Clone the repository and `cd` into it.
2. Place an OurAirports-format `airports.csv` in the `src/` folder. If it is missing, the app tries to download one.
3. Run:

```bash
python3 main.py
```

## Controls

| Key / Action | Effect |
|---|---|
| `1` to `7` | Jump to a city preset (Dubai, London, New York, Tokyo, Paris, Sydney, Singapore) |
| `0` | Toggle between city view and airport close-up view |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| Scroll wheel | Zoom in / out |
| Arrow keys | Pan the view |
| `R` / Backspace | Reset zoom and pan |
| `Esc` | Exit |

## Project structure

```
radar_background/
├── main.py              # live fullscreen window (keyboard controls)
├── radar_ctl.py         # terminal controller: location, zoom, layers, reload
├── snapshot.py          # renders one frame, sets the GNOME wallpaper, deletes the old image
├── install.sh           # systemd user timer for scheduled refreshes
├── pytest.ini
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py        # screen size, FPS, default bbox
│   ├── flight.py        # Flight data model, OpenSky parsing
│   ├── fetcher.py       # OpenSky API client (takes a bbox)
│   ├── map.py           # geo to screen projection helpers
│   ├── airports.py      # airport CSV loader and bbox lookup
│   ├── routes.py        # rate-limited route lookup with cache
│   ├── renderer.py      # all drawing: radar, panel, trails, icons
│   ├── settings.py      # saved view settings plus zoom/pan/goto maths
│   └── airports.csv     # airport data (OurAirports format)
└── tests/
    ├── __init__.py
    ├── test_flight.py
    ├── test_fetcher.py
    ├── test_map.py
    ├── test_renderer.py
    ├── test_settings.py
    ├── test_snapshot.py
    └── fixtures/
        └── opensky_response.json
```

## How it works

1. A background thread calls `fetch_flights(bbox)` every 10 seconds for the area currently on screen.
2. New callsigns are queued in `RouteCache`, which fetches one route per ~1.2 s to respect API limits.
3. The main loop draws each frame: background, city silhouette, trails, radar, compass, routes, airports, planes, then the left panel.
4. Changing location, zoom or pan updates the shared bounding box, so the next poll fetches the correct region.
5. Make sure to disable any old wallpaper engines or sources which may be running

## Changing the location

Add an entry to `CITY_LOCATIONS` (and optionally `AIRPORT_LOCATIONS`) in `src/renderer.py`:

```python
"rome": ("ROME / ITALY", (40.5, 11.0, 43.0, 14.5)),   # (lat_min, lon_min, lat_max, lon_max)
```

Then bind a key to it in `main.py`.

## Testing

Tests never call the real API or open a display.

```bash
pytest
```

Run from the project root so `pytest.ini` is picked up.

## Known limitations

- OpenSky's anonymous tier is rate limited, so updates arrive roughly every 10 seconds and some flights have no route data.
- Country and coastline borders inside the radar are not working yet.
- It runs as a fullscreen Pygame window rather than a true desktop background. A GNOME Shell extension is a possible next step.

## Data sources

- Flight positions and routes: [OpenSky Network](https://opensky-network.org/)
- Airports: [OurAirports](https://ourairports.com/data/)

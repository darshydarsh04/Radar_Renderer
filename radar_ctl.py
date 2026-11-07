#!/usr/bin/env python3
"""
radar_ctl.py: terminal controller for the flight radar wallpaper.

Change the location, zoom, map background and airports from a prompt, then type
`reload` to fetch fresh data, render a new image, set it as your wallpaper and
delete the old one. Your choices are saved, so the scheduled refresh
(install.sh) keeps using them.

    python3 radar_ctl.py                                        # interactive
    python3 radar_ctl.py -c "location london; zoom in; reload"  # one-off
"""
from __future__ import annotations

import argparse
import cmd
from typing import Optional

from snapshot import OUT_DIR, render_wallpaper
from src import settings as st
from src.renderer import CITY_LOCATIONS

APPLY_HINT = "(type 'reload' to apply)"


class RadarShell(cmd.Cmd):
    intro = "Flight radar controller. 'help' lists commands; 'reload' renders a new wallpaper.\n"
    prompt = "radar> "

    def __init__(self) -> None:
        super().__init__()
        self.s = st.load_settings()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _changed(self, message: Optional[str] = None) -> None:
        st.save_settings(self.s)
        print(message or self._summary())

    def _summary(self) -> str:
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(self.s)
        view = "custom" if self.s["custom"] else ("airport" if self.s["airport_mode"] else "city")
        return (f"  {st.display_name(self.s)} [{view}]  lat {lat_min:.2f}..{lat_max:.2f}  "
                f"lon {lon_min:.2f}..{lon_max:.2f}  zoom {st.zoom_level(self.s):.1f}x  {APPLY_HINT}")

    @staticmethod
    def _toggle(arg: str, current: bool) -> Optional[bool]:
        word = arg.strip().lower()
        if not word:
            return not current
        if word in ("on", "1", "yes", "true"):
            return True
        if word in ("off", "0", "no", "false"):
            return False
        return None

    @staticmethod
    def _complete(text: str, options) -> list[str]:
        return [o for o in options if o.startswith(text)]

    # ------------------------------------------------------------------
    # location
    # ------------------------------------------------------------------

    def do_locations(self, arg: str) -> None:
        """locations   List the built-in city presets."""
        for key in sorted(CITY_LOCATIONS):
            print(f"  {key:<10} {CITY_LOCATIONS[key][0]}")

    def do_location(self, arg: str) -> None:
        """location NAME   Jump to a city preset (see 'locations'). Resets zoom and pan."""
        name = arg.strip().lower()
        if name not in CITY_LOCATIONS:
            print("Unknown location. Available: " + ", ".join(sorted(CITY_LOCATIONS)))
            return
        st.set_location(self.s, name)
        self._changed()

    def complete_location(self, text, line, begidx, endidx):
        return self._complete(text, sorted(CITY_LOCATIONS))

    def do_goto(self, arg: str) -> None:
        """goto LAT LON [RADIUS]   Centre on any coordinates.
        RADIUS is the degrees of latitude shown either side (default 3).
        Example: goto 51.47 -0.45 1"""
        try:
            nums = [float(x) for x in arg.split()]
        except ValueError:
            nums = []
        if len(nums) not in (2, 3):
            print("Usage: goto LAT LON [RADIUS]   e.g. goto 51.47 -0.45 1")
            return
        try:
            st.goto(self.s, *nums)
        except ValueError as exc:
            print(exc)
            return
        self._changed()

    def do_mode(self, arg: str) -> None:
        """mode city|airport   Switch between the city view and the airport close-up."""
        word = arg.strip().lower()
        if word not in ("city", "airport"):
            print("Usage: mode city|airport")
            return
        st.set_mode(self.s, word == "airport")
        self._changed()

    def complete_mode(self, text, line, begidx, endidx):
        return self._complete(text, ["city", "airport"])

    # ------------------------------------------------------------------
    # zoom and pan
    # ------------------------------------------------------------------

    def do_zoom(self, arg: str) -> None:
        """zoom in [N] | zoom out [N] | zoom FACTOR | zoom reset
        'zoom in' / 'zoom out' change the area by 1.33x; N sets your own multiplier
        (zoom in 2 = half the area). FACTOR is a raw scale: 0.5 = in, 2 = out."""
        parts = arg.split()
        usage = "Usage: zoom in [N] | zoom out [N] | zoom FACTOR | zoom reset"
        if not parts:
            print(usage)
            return
        try:
            if parts[0] == "reset":
                st.reset_view(self.s)
            elif parts[0] in ("in", "out"):
                n = float(parts[1]) if len(parts) > 1 else st.DEFAULT_ZOOM_STEP
                if n <= 1:
                    print("N must be greater than 1")
                    return
                st.zoom(self.s, 1 / n if parts[0] == "in" else n)
            else:
                st.zoom(self.s, float(parts[0]))
        except ValueError as exc:
            print(exc if "factor" in str(exc) else usage)
            return
        self._changed()

    def complete_zoom(self, text, line, begidx, endidx):
        return self._complete(text, ["in", "out", "reset"])

    def do_pan(self, arg: str) -> None:
        """pan north|south|east|west [FRACTION]   Move the view (default 0.2 of what is visible).
        Short forms work: pan n, pan w 0.5"""
        parts = arg.split()
        if not parts or parts[0][0].lower() not in "nsew":
            print("Usage: pan north|south|east|west [FRACTION]")
            return
        try:
            frac = float(parts[1]) if len(parts) > 1 else st.DEFAULT_PAN_STEP
        except ValueError:
            print("FRACTION must be a number, e.g. 0.5")
            return
        if frac <= 0:
            print("FRACTION must be greater than 0")
            return
        direction = parts[0][0].lower()
        st.pan(self.s,
               north={"n": frac, "s": -frac}.get(direction, 0.0),
               east={"e": frac, "w": -frac}.get(direction, 0.0))
        self._changed()

    def complete_pan(self, text, line, begidx, endidx):
        return self._complete(text, ["north", "south", "east", "west"])

    # ------------------------------------------------------------------
    # layers
    # ------------------------------------------------------------------

    def do_map(self, arg: str) -> None:
        """map [on|off]   City skyline background. With no argument it toggles."""
        value = self._toggle(arg, self.s["show_map"])
        if value is None:
            print("Usage: map [on|off]")
            return
        self.s["show_map"] = value
        self._changed(f"  map background: {'on' if value else 'off'}  {APPLY_HINT}")

    def do_airports(self, arg: str) -> None:
        """airports [on|off]   Airport markers. With no argument it toggles."""
        value = self._toggle(arg, self.s["show_airports"])
        if value is None:
            print("Usage: airports [on|off]")
            return
        self.s["show_airports"] = value
        self._changed(f"  airports: {'on' if value else 'off'}  {APPLY_HINT}")

    def do_routes(self, arg: str) -> None:
        """routes [on|off|N]   Route lines and lookups. 'off' skips the lookups, which makes
        reload much faster; N is the most flights to look up per render (default 12)."""
        word = arg.strip().lower()
        usage = "Usage: routes [on|off|N]"
        if not word:
            n = 0 if self.s["routes"] else st.DEFAULT_ROUTES
        elif word == "on":
            n = self.s["routes"] or st.DEFAULT_ROUTES
        elif word == "off":
            n = 0
        else:
            try:
                n = int(word)
            except ValueError:
                print(usage)
                return
            if n < 0:
                print(usage)
                return
        self.s["routes"] = n
        self._changed(f"  routes: {'off' if n == 0 else f'up to {n} lookups'}  {APPLY_HINT}")

    def do_size(self, arg: str) -> None:
        """size WIDTHxHEIGHT   Resolution of the image, e.g. size 2560x1440 (use your screen's)."""
        if st.parse_size(arg.strip()) is None:
            print("Usage: size WIDTHxHEIGHT, e.g. size 1920x1080 (at least 640x480)")
            return
        self.s["size"] = arg.strip().lower()
        self._changed(f"  size: {self.s['size']}  {APPLY_HINT}")

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def do_status(self, arg: str) -> None:
        """status   Show the current settings."""
        lat_min, lon_min, lat_max, lon_max = st.current_bbox(self.s)
        view = ("custom view" if self.s["custom"]
                else "airport close-up" if self.s["airport_mode"] else "city view")
        routes = "off" if self.s["routes"] == 0 else f"up to {self.s['routes']} lookups"
        print(f"  Location : {st.display_name(self.s)} ({view})")
        print(f"  View     : lat {lat_min:.2f}..{lat_max:.2f}, lon {lon_min:.2f}..{lon_max:.2f}"
              f" (zoom {st.zoom_level(self.s):.1f}x)")
        print(f"  Layers   : map {'on' if self.s['show_map'] else 'off'}, "
              f"airports {'on' if self.s['show_airports'] else 'off'}, routes {routes}")
        print(f"  Size     : {self.s['size']}")
        print(f"  Images   : {OUT_DIR}")

    def do_reload(self, arg: str) -> None:
        """reload [force]   Fetch fresh data, render a new image, set it as the wallpaper and
        delete the old image. 'force' renders even if no flights came back."""
        try:
            out = render_wallpaper(self.s, force=arg.strip().lower() == "force")
        except Exception as exc:   # keep the shell alive whatever goes wrong
            print(f"Reload failed: {exc}")
            return
        if out:
            print(f"Done: {out}")

    def do_r(self, arg: str) -> None:
        """r   Shortcut for reload."""
        self.do_reload(arg)

    def do_quit(self, arg: str) -> bool:
        """quit   Leave the controller (settings are already saved)."""
        return True

    do_exit = do_quit
    do_EOF = do_quit

    def emptyline(self) -> bool:
        return False   # do not repeat the last command on a blank line

    def default(self, line: str) -> None:
        print(f"Unknown command: {line.split()[0]!r}. Type 'help'.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Terminal controller for the flight radar wallpaper.")
    ap.add_argument("-c", "--commands",
                    help='run these commands (separated by ";") and exit, '
                         'e.g. -c "location london; zoom in; reload"')
    args = ap.parse_args()

    shell = RadarShell()
    if args.commands:
        for line in args.commands.split(";"):
            line = line.strip()
            if line:
                print(f"radar> {line}")
                if shell.onecmd(line):
                    break
        return 0
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

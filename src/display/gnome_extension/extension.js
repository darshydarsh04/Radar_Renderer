// extension.js — GNOME Shell Extension (Phase 2)
// Renders a canvas behind the desktop by creating a St.DrawingArea
// that covers the root actor, positioned below all windows.
//
// This communicates with your Python flight fetcher via a Unix socket
// or a named pipe written to /tmp/flights.json every 10 seconds.

import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// How often to re-read the flight data file (ms)
const REFRESH_MS = 10_000;

// Python backend writes flight positions here
const FLIGHT_DATA_PATH = '/tmp/flights.json';

let _canvas = null;
let _timeoutId = null;
let _flights = [];

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

function loadFlights() {
    try {
        const [ok, contents] = GLib.file_get_contents(FLIGHT_DATA_PATH);
        if (ok) {
            const json = new TextDecoder().decode(contents);
            _flights = JSON.parse(json);
        }
    } catch (e) {
        // File not written yet — use empty array, don't crash
        _flights = [];
    }
}

// ---------------------------------------------------------------------------
// Drawing — called by Clutter whenever the canvas needs repainting
// ---------------------------------------------------------------------------

function onDraw(canvas, cr, width, height) {
    // Background
    cr.setSourceRGB(0.016, 0.031, 0.094);   // deep navy
    cr.paint();

    // Grid lines
    cr.setSourceRGBA(0.07, 0.16, 0.28, 1.0);
    cr.setLineWidth(0.5);
    for (let x = 0; x < width; x += width / 15) {
        cr.moveTo(x, 0); cr.lineTo(x, height);
    }
    for (let y = 0; y < height; y += height / 10) {
        cr.moveTo(0, y); cr.lineTo(width, y);
    }
    cr.stroke();

    // Planes  — _flights is [{lon, lat, heading, callsign}, ...]
    const LAT_MIN = 22, LAT_MAX = 30;
    const LON_MIN = 45, LON_MAX = 60;

    _flights.forEach(f => {
        if (f.lon == null || f.lat == null) return;
        const x = (f.lon - LON_MIN) / (LON_MAX - LON_MIN) * width;
        const y = (LAT_MAX - f.lat) / (LAT_MAX - LAT_MIN) * height;

        // Plane dot
        cr.setSourceRGBA(0.0, 0.86, 1.0, 0.9);
        cr.arc(x, y, 3, 0, 2 * Math.PI);
        cr.fill();

        // Heading line
        const rad = (f.heading - 90) * Math.PI / 180;
        cr.setSourceRGBA(0.0, 0.86, 1.0, 0.4);
        cr.setLineWidth(1);
        cr.moveTo(x, y);
        cr.lineTo(x + Math.cos(rad) * 12, y + Math.sin(rad) * 12);
        cr.stroke();
    });

    return Clutter.EVENT_STOP;
}

// ---------------------------------------------------------------------------
// Extension lifecycle
// ---------------------------------------------------------------------------

export default class FlightRadarExtension {
    enable() {
        // Create a full-screen canvas actor
        _canvas = new Clutter.Canvas();
        _canvas.connect('draw', onDraw);

        const actor = new St.Widget({
            width:  global.stage.width,
            height: global.stage.height,
            content: _canvas,
            reactive: false,       // don't intercept mouse events
            z_position: -1,        // behind everything
        });

        // Insert below desktop icons but above the bare background
        Main.layoutManager.uiGroup.insert_child_at_index(actor, 0);

        // Poll for new flight data
        _timeoutId = GLib.timeout_add(GLib.PRIORITY_LOW, REFRESH_MS, () => {
            loadFlights();
            _canvas.invalidate();   // triggers onDraw
            return GLib.SOURCE_CONTINUE;
        });

        loadFlights();
        _canvas.set_size(global.stage.width, global.stage.height);
        _canvas.invalidate();
    }

    disable() {
        if (_timeoutId) {
            GLib.source_remove(_timeoutId);
            _timeoutId = null;
        }
        if (_canvas) {
            _canvas.destroy();
            _canvas = null;
        }
        _flights = [];
    }
}
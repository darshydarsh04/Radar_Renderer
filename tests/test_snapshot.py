"""
tests/test_snapshot.py: render_wallpaper() saves an image, sets it, and deletes the old ones.

No network and no display: flights are faked and set_wallpaper is replaced.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

import snapshot
from src import settings as st


def fake_flights(n: int = 3) -> list:
    return [
        NS(icao24=f"a{i:05d}", callsign=f"UAE{100 + i}", longitude=52.0 + i,
           latitude=25.0 + i * 0.5, heading=45.0 * i, altitude=10000.0, velocity=200.0)
        for i in range(n)
    ]


@pytest.fixture
def env(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    monkeypatch.setattr(snapshot, "OUT_DIR", out_dir)
    monkeypatch.setattr(snapshot, "fetch_flights", lambda bbox: fake_flights())
    set_calls = []
    monkeypatch.setattr(snapshot, "set_wallpaper", lambda path: set_calls.append(path))

    settings = dict(st.DEFAULTS)
    settings.update(size="800x600", routes=0, show_airports=False)   # no network needed
    return settings, out_dir, set_calls


def quiet(_msg: str) -> None:
    pass


def images(out_dir):
    return sorted(p.name for p in out_dir.glob("radar-*.png"))


class TestRenderWallpaper:
    def test_creates_a_png(self, env):
        settings, out_dir, _ = env
        out = snapshot.render_wallpaper(settings, set_it=False, log=quiet)
        assert out.exists() and out.stat().st_size > 1000
        assert out.parent == out_dir

    def test_sets_the_new_image_as_wallpaper(self, env):
        settings, _, set_calls = env
        out = snapshot.render_wallpaper(settings, log=quiet)
        assert set_calls == [out]

    def test_deletes_old_images_after_setting(self, env):
        settings, out_dir, _ = env
        (out_dir / "radar-1.png").write_bytes(b"old")
        (out_dir / "radar-2.png").write_bytes(b"old")
        (out_dir / "keep-me.txt").write_text("unrelated")
        out = snapshot.render_wallpaper(settings, log=quiet)
        assert images(out_dir) == [out.name]
        assert (out_dir / "keep-me.txt").exists()

    def test_keeps_old_images_when_gnome_cannot_be_set(self, env, monkeypatch):
        settings, out_dir, _ = env
        (out_dir / "radar-1.png").write_bytes(b"old")

        def boom(_path):
            raise RuntimeError("gsettings not found")

        monkeypatch.setattr(snapshot, "set_wallpaper", boom)
        with pytest.raises(RuntimeError):
            snapshot.render_wallpaper(settings, log=quiet)
        assert "radar-1.png" in images(out_dir)      # the old wallpaper is still there
        assert len(images(out_dir)) == 2             # and the new image was saved

    def test_keeps_old_images_in_no_set_mode(self, env):
        settings, out_dir, set_calls = env
        (out_dir / "radar-1.png").write_bytes(b"old")
        snapshot.render_wallpaper(settings, set_it=False, log=quiet)
        assert "radar-1.png" in images(out_dir)
        assert set_calls == []

    def test_repeated_reloads_leave_exactly_one_image(self, env):
        settings, out_dir, _ = env
        for _ in range(3):
            snapshot.render_wallpaper(settings, log=quiet)
        assert len(images(out_dir)) == 1

    def test_no_flights_changes_nothing(self, env, monkeypatch):
        settings, out_dir, set_calls = env
        (out_dir / "radar-1.png").write_bytes(b"old")
        monkeypatch.setattr(snapshot, "fetch_flights", lambda bbox: [])
        assert snapshot.render_wallpaper(settings, log=quiet) is None
        assert images(out_dir) == ["radar-1.png"]
        assert set_calls == []

    def test_force_renders_without_flights(self, env, monkeypatch):
        settings, out_dir, _ = env
        monkeypatch.setattr(snapshot, "fetch_flights", lambda bbox: [])
        out = snapshot.render_wallpaper(settings, force=True, log=quiet)
        assert out is not None and out.exists()

    def test_fetches_the_saved_view(self, env, monkeypatch):
        settings, _, _ = env
        st.goto(settings, 51.47, -0.45, 1.0)
        seen = []
        monkeypatch.setattr(snapshot, "fetch_flights",
                            lambda bbox: seen.append(bbox) or fake_flights())
        snapshot.render_wallpaper(settings, set_it=False, log=quiet)
        assert seen[0] == pytest.approx(st.current_bbox(settings))


class TestBuildRenderer:
    def test_layer_flags_follow_settings(self):
        s = dict(st.DEFAULTS)
        s.update(size="800x600", show_map=False, show_airports=False, routes=0)
        r = snapshot.build_renderer(s)
        assert r.show_silhouette is False
        assert r.show_airports is False
        assert r.show_routes is False

    def test_layers_on_by_default(self):
        s = dict(st.DEFAULTS)
        s["size"] = "800x600"
        r = snapshot.build_renderer(s)
        assert r.show_silhouette and r.show_airports and r.show_routes

    def test_size_is_applied(self):
        s = dict(st.DEFAULTS)
        s["size"] = "1024x768"
        assert snapshot.build_renderer(s).surface.get_size() == (1024, 768)

    def test_zoomed_view_is_applied(self):
        s = dict(st.DEFAULTS)
        s["size"] = "800x600"
        st.zoom(s, 0.5)
        r = snapshot.build_renderer(s)
        assert r.bbox == pytest.approx(st.current_bbox(s))

    def test_airport_mode_is_applied(self):
        s = dict(st.DEFAULTS)
        s["size"] = "800x600"
        st.set_mode(s, True)
        r = snapshot.build_renderer(s)
        assert r._airport_mode is True
        assert r.bbox == pytest.approx(st.current_bbox(s))

    def test_custom_view_uses_label(self):
        s = dict(st.DEFAULTS)
        s["size"] = "800x600"
        st.goto(s, 51.47, -0.45, 1.0)
        r = snapshot.build_renderer(s)
        assert r.location_name == s["label"]
        assert r.bbox == pytest.approx(st.current_bbox(s))

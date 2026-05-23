# tests/test_map.py
from src.map import project, in_bbox
from src.config import SCREEN_W, SCREEN_H, BBOX

lat_min, lon_min, lat_max, lon_max = BBOX


class TestProject:
    def test_top_left_corner(self):
        x, y = project(lon_min, lat_max)
        assert x == 0 and y == 0

    def test_bottom_right_corner(self):
        x, y = project(lon_max, lat_min)
        assert x == SCREEN_W and y == SCREEN_H

    def test_center(self):
        mid_lon = (lon_min + lon_max) / 2
        mid_lat = (lat_min + lat_max) / 2
        x, y = project(mid_lon, mid_lat)
        assert x == SCREEN_W // 2
        assert y == SCREEN_H // 2

    def test_y_axis_is_flipped(self):
        """Higher latitude = smaller y (closer to top of screen)."""
        _, y_north = project(55.0, lat_max - 1)
        _, y_south = project(55.0, lat_min + 1)
        assert y_north < y_south


class TestInBbox:
    def test_center_is_inside(self):
        assert in_bbox(52.5, 26.0) is True

    def test_outside_lon(self):
        assert in_bbox(70.0, 25.0) is False

    def test_outside_lat(self):
        assert in_bbox(55.0, 5.0) is False

    def test_edge_is_inside(self):
        assert in_bbox(lon_min, lat_min) is True
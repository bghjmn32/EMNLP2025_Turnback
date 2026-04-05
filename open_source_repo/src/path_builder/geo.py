from __future__ import annotations

import math
from typing import Iterable

from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point
from shapely.ops import substring, transform

from .models import LatLon

ABSOLUTE_DIRECTIONS = {
    "north": 0.0,
    "northeast": 45.0,
    "east": 90.0,
    "southeast": 135.0,
    "south": 180.0,
    "southwest": 225.0,
    "west": 270.0,
    "northwest": 315.0,
}

RELATIVE_DIRECTIONS = {
    "left": -75.0,
    "right": 75.0,
    "slight left": -30.0,
    "slight right": 30.0,
    "sharp left": -100.0,
    "sharp right": 100.0,
    "keep left": -30.0,
    "keep right": 30.0,
    "straight": 0.0,
    "continue straight": 0.0,
}


def normalize_heading(heading: float) -> float:
    return heading % 360.0


def angular_difference(left: float, right: float) -> float:
    delta = abs(normalize_heading(left) - normalize_heading(right))
    return min(delta, 360.0 - delta)


def signed_heading_delta(current_heading: float, target_heading: float) -> float:
    return ((normalize_heading(target_heading) - normalize_heading(current_heading) + 540.0) % 360.0) - 180.0


def bearing_between_points(start: LatLon, end: LatLon) -> float:
    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)
    delta_lon = lon2 - lon1
    x = math.cos(lat2) * math.sin(delta_lon)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return normalize_heading(math.degrees(math.atan2(x, y)))


def heading_for_instruction(current_heading: float, direction: str | None) -> float:
    if not direction:
        return normalize_heading(current_heading)
    direction = " ".join(direction.lower().split())
    if direction in ABSOLUTE_DIRECTIONS:
        return ABSOLUTE_DIRECTIONS[direction]
    if direction in RELATIVE_DIRECTIONS:
        return normalize_heading(current_heading + RELATIVE_DIRECTIONS[direction])
    raise ValueError(f"Unsupported direction: {direction}")


def utm_crs_for(lat: float, lon: float) -> CRS:
    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return CRS.from_epsg(epsg)


def project_geometry_to_local_meters(geometry: LineString | Point, anchor: LatLon) -> tuple[LineString | Point, Transformer, Transformer]:
    lat, lon = anchor
    target = utm_crs_for(lat, lon)
    to_local = Transformer.from_crs("EPSG:4326", target, always_xy=True)
    to_wgs84 = Transformer.from_crs(target, "EPSG:4326", always_xy=True)
    projected = transform(to_local.transform, geometry)
    return projected, to_local, to_wgs84


def point_distance_meters(left: LatLon, right: LatLon) -> float:
    lat0 = math.radians((left[0] + right[0]) / 2.0)
    dx = math.radians(right[1] - left[1]) * 6_371_000.0 * math.cos(lat0)
    dy = math.radians(right[0] - left[0]) * 6_371_000.0
    return math.hypot(dx, dy)


def path_length_meters(points: Iterable[LatLon]) -> float:
    total = 0.0
    items = list(points)
    for start, end in zip(items, items[1:]):
        total += point_distance_meters(start, end)
    return total


def interpolate_along_line(line: LineString, distance_meters: float) -> tuple[LatLon, float]:
    anchor = (line.coords[0][1], line.coords[0][0])
    projected, _, to_wgs84 = project_geometry_to_local_meters(line, anchor)
    total = projected.length
    actual = min(max(distance_meters, 0.0), total)
    point = projected.interpolate(actual)
    lon, lat = to_wgs84.transform(point.x, point.y)
    return (lat, lon), actual


def project_point_onto_line(line: LineString, point: LatLon) -> tuple[LatLon, float]:
    anchor = point
    projected_line, to_local, to_wgs84 = project_geometry_to_local_meters(line, anchor)
    projected_point = transform(to_local.transform, Point(point[1], point[0]))
    along = projected_line.project(projected_point)
    snapped = projected_line.interpolate(along)
    lon, lat = to_wgs84.transform(snapped.x, snapped.y)
    return (lat, lon), along


def extract_line_segment(line: LineString, start: LatLon, distance_meters: float) -> tuple[list[LatLon], LatLon, float]:
    anchor = start
    projected_line, to_local, to_wgs84 = project_geometry_to_local_meters(line, anchor)
    projected_point = transform(to_local.transform, Point(start[1], start[0]))
    start_distance = projected_line.project(projected_point)
    end_distance = min(projected_line.length, start_distance + max(distance_meters, 0.0))
    clipped = substring(projected_line, start_distance, end_distance)
    if isinstance(clipped, Point):
        lon, lat = to_wgs84.transform(clipped.x, clipped.y)
        point = (lat, lon)
        return [point, point], point, 0.0
    latlon_points: list[LatLon] = []
    for x, y in clipped.coords:
        lon, lat = to_wgs84.transform(x, y)
        latlon_points.append((lat, lon))
    endpoint = latlon_points[-1] if latlon_points else start
    return latlon_points, endpoint, end_distance - start_distance

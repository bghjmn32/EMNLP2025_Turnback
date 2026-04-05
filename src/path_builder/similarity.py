from __future__ import annotations

import json
import math
from typing import Any

from shapely.geometry import LineString

from .models import LonLat, SimilarityResult, SimilarityThresholds, SimilarityWeights

XY = tuple[float, float]
EARTH_R = 6_371_000.0


def lonlat_to_xy(lon: float, lat: float, lon0: float, lat0: float) -> XY:
    x = math.radians(lon - lon0) * EARTH_R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_R
    return x, y


def polyline_length(poly_xy: list[XY]) -> float:
    if len(poly_xy) < 2:
        return 0.0
    return sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(poly_xy, poly_xy[1:]))


def resample_polyline(poly_xy: list[XY], n_points: int = 64) -> list[XY]:
    if not poly_xy:
        return []
    if len(poly_xy) == 1:
        return [poly_xy[0]] * n_points
    cumulative = [0.0]
    for (x1, y1), (x2, y2) in zip(poly_xy, poly_xy[1:]):
        cumulative.append(cumulative[-1] + math.hypot(x2 - x1, y2 - y1))
    total = cumulative[-1]
    if total == 0:
        return [poly_xy[0]] * n_points
    targets = [total * index / (n_points - 1) for index in range(n_points)]
    points: list[XY] = []
    segment_index = 1
    for target in targets:
        while segment_index < len(cumulative) and cumulative[segment_index] < target:
            segment_index += 1
        if segment_index >= len(cumulative):
            points.append(poly_xy[-1])
            continue
        start_distance = cumulative[segment_index - 1]
        end_distance = cumulative[segment_index]
        if end_distance == start_distance:
            points.append(poly_xy[segment_index])
            continue
        ratio = (target - start_distance) / (end_distance - start_distance)
        x1, y1 = poly_xy[segment_index - 1]
        x2, y2 = poly_xy[segment_index]
        points.append((x1 + ratio * (x2 - x1), y1 + ratio * (y2 - y1)))
    return points


def directed_hausdorff(left: list[XY], right: list[XY]) -> float:
    if not left or not right:
        return float("inf")
    best = 0.0
    for lx, ly in left:
        minimum = min(math.hypot(lx - rx, ly - ry) for rx, ry in right)
        best = max(best, minimum)
    return best


def hausdorff_distance(left: list[XY], right: list[XY], densify_n: int = 128) -> float:
    a = resample_polyline(left, densify_n)
    b = resample_polyline(right, densify_n)
    return max(directed_hausdorff(a, b), directed_hausdorff(b, a))


def angle_between_vectors_deg(left: XY, right: XY) -> float:
    lx, ly = left
    rx, ry = right
    left_norm = math.hypot(lx, ly)
    right_norm = math.hypot(rx, ry)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    cosine = max(-1.0, min(1.0, (lx * rx + ly * ry) / (left_norm * right_norm)))
    return math.degrees(math.acos(cosine))


def bearing_deg(start: XY, end: XY) -> float:
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    return angle + 360.0 if angle < 0 else angle


def quantize_bearing(bearing: float, bins: int = 16) -> int:
    step = 360.0 / bins
    return int(bearing // step) % bins


def polyline_to_tokens(poly_xy: list[XY], n_points: int = 64, bearing_bins: int = 16) -> list[int]:
    points = resample_polyline(poly_xy, n_points)
    return [quantize_bearing(bearing_deg(start, end), bearing_bins) for start, end in zip(points, points[1:])]


def levenshtein(left: list[int], right: list[int]) -> int:
    if not left:
        return len(right)
    if not right:
        return len(left)
    row = list(range(len(right) + 1))
    for left_index, left_value in enumerate(left, start=1):
        previous = row[0]
        row[0] = left_index
        for right_index, right_value in enumerate(right, start=1):
            current = row[right_index]
            cost = 0 if left_value == right_value else 1
            row[right_index] = min(
                row[right_index] + 1,
                row[right_index - 1] + 1,
                previous + cost,
            )
            previous = current
    return row[-1]


def edr_similarity_score(left: list[XY], right: list[XY], n_points: int = 64, bearing_bins: int = 16) -> float:
    left_tokens = polyline_to_tokens(left, n_points=n_points, bearing_bins=bearing_bins)
    right_tokens = polyline_to_tokens(right, n_points=n_points, bearing_bins=bearing_bins)
    distance = levenshtein(left_tokens, right_tokens)
    denominator = max(len(left_tokens), len(right_tokens), 1)
    return 100.0 * max(0.0, min(1.0, 1.0 - distance / denominator))


def length_ratio_score(left: list[XY], right: list[XY]) -> float:
    left_length = polyline_length(left)
    right_length = polyline_length(right)
    if left_length == 0 and right_length == 0:
        return 100.0
    if left_length == 0 or right_length == 0:
        return 0.0
    return 100.0 * (min(left_length, right_length) / max(left_length, right_length))


def endpoints_shift(left: list[XY], right: list[XY]) -> float:
    if not left or not right:
        return float("inf")
    return math.hypot(left[0][0] - right[0][0], left[0][1] - right[0][1]) + math.hypot(left[-1][0] - right[-1][0], left[-1][1] - right[-1][1])


def endpoints_shift_score(left: list[XY], right: list[XY], scale_m: float = 20.0) -> float:
    shift = endpoints_shift(left, right)
    if not math.isfinite(shift):
        return 0.0
    return 100.0 / (1.0 + shift / max(scale_m, 1e-6))


def angle_score(left: list[XY], right: list[XY]) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    vector_left = (left[-1][0] - left[0][0], left[-1][1] - left[0][1])
    vector_right = (right[-1][0] - right[0][0], right[-1][1] - right[0][1])
    angle = angle_between_vectors_deg(vector_left, vector_right)
    return 100.0 * (1.0 - angle / 180.0)


def iou_buffer_score(left: list[XY], right: list[XY], buffer_m: float = 20.0) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    buffer_left = LineString(left).buffer(buffer_m)
    buffer_right = LineString(right).buffer(buffer_m)
    union = buffer_left.union(buffer_right).area
    if union == 0:
        return 100.0
    return 100.0 * (buffer_left.intersection(buffer_right).area / union)


def hausdorff_score(left: list[XY], right: list[XY], scale_m: float = 50.0, densify_n: int = 128) -> float:
    distance = hausdorff_distance(left, right, densify_n=densify_n)
    if not math.isfinite(distance):
        return 0.0
    return 100.0 / (1.0 + distance / max(scale_m, 1e-6))


def weighted_sum(scores: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return 0.0
    return sum(scores.get(metric, 0.0) * weight / total_weight for metric, weight in weights.items())


def extract_linestring_coordinates(geojson: dict[str, Any]) -> list[list[LonLat]]:
    lines: list[list[LonLat]] = []
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "LineString":
            continue
        lines.append([(float(lon), float(lat)) for lon, lat in geometry.get("coordinates", [])])
    return lines


def to_projected_xy(left: list[LonLat], right: list[LonLat]) -> tuple[list[XY], list[XY]]:
    all_points = left + right
    lon0 = sum(point[0] for point in all_points) / len(all_points)
    lat0 = sum(point[1] for point in all_points) / len(all_points)
    return (
        [lonlat_to_xy(lon, lat, lon0, lat0) for lon, lat in left],
        [lonlat_to_xy(lon, lat, lon0, lat0) for lon, lat in right],
    )


def score_polylines(
    prediction: list[LonLat],
    reference: list[LonLat],
    weights: SimilarityWeights | None = None,
    thresholds: SimilarityThresholds | None = None,
) -> SimilarityResult:
    weights = weights or SimilarityWeights()
    thresholds = thresholds or SimilarityThresholds()
    prediction_xy, reference_xy = to_projected_xy(prediction, reference)
    score_map = {
        "length_ratio": length_ratio_score(prediction_xy, reference_xy),
        "hausdorff": hausdorff_score(prediction_xy, reference_xy, scale_m=thresholds.hausdorff_scale_m, densify_n=thresholds.hausdorff_densify_points),
        "iou": iou_buffer_score(prediction_xy, reference_xy, buffer_m=thresholds.buffer_meters),
        "angle": angle_score(prediction_xy, reference_xy),
        "endpoints_shift": endpoints_shift_score(prediction_xy, reference_xy, scale_m=thresholds.endpoints_scale_m),
        "edr": edr_similarity_score(prediction_xy, reference_xy, n_points=thresholds.edr_resample_points, bearing_bins=thresholds.edr_bearing_bins),
    }
    return SimilarityResult(
        similarity=weighted_sum(score_map, weights.as_dict()),
        scores=score_map,
        weights=weights.as_dict(),
        params=thresholds.as_dict(),
    )


def score_geojson_routes(
    prediction_geojson: dict[str, Any],
    reference_geojson: dict[str, Any],
    weights: SimilarityWeights | None = None,
    thresholds: SimilarityThresholds | None = None,
) -> SimilarityResult:
    prediction_lines = extract_linestring_coordinates(prediction_geojson)
    reference_lines = extract_linestring_coordinates(reference_geojson)
    if not prediction_lines or not reference_lines:
        raise ValueError("Both GeoJSON payloads must contain at least one LineString feature.")
    return score_polylines(prediction_lines[0], reference_lines[0], weights=weights, thresholds=thresholds)


def payload_from_geojson(
    prediction_geojson: dict[str, Any],
    reference_geojson: dict[str, Any],
    weights: SimilarityWeights | None = None,
    thresholds: SimilarityThresholds | None = None,
) -> dict[str, Any]:
    weights = weights or SimilarityWeights()
    thresholds = thresholds or SimilarityThresholds()
    return {
        "data": {
            "format": "geojson",
            "encoding": "plain_text",
            "content": json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": prediction_geojson.get("features", []) + reference_geojson.get("features", []),
                }
            ),
        },
        "weights": weights.as_dict(),
        "thresholds": thresholds.as_dict(),
    }


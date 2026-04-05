from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, mapping, shape
from shapely.ops import linemerge


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_geojson(path: str | Path) -> dict[str, Any]:
    return read_json(path)


def save_geojson(path: str | Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def merge_line_features(geojson_data: dict[str, Any]) -> dict[str, Any]:
    features = geojson_data.get("features", [])
    if not features:
        return {"type": "FeatureCollection", "features": []}
    lines = [shape(feature["geometry"]) for feature in features]
    merged = linemerge(lines)
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": mapping(merged)}],
    }


def feature_collection_from_linestring(line: LineString, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": properties or {}, "geometry": mapping(line)}],
    }


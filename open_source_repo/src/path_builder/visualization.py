from __future__ import annotations

from pathlib import Path

from shapely.geometry import LineString

from .similarity import extract_linestring_coordinates


def plot_route_pair(reference_geojson: dict, prediction_geojson: dict, output_path: str | Path | None = None, title: str = "Route Comparison") -> None:
    import matplotlib.pyplot as plt

    reference_lines = extract_linestring_coordinates(reference_geojson)
    prediction_lines = extract_linestring_coordinates(prediction_geojson)
    fig, ax = plt.subplots(figsize=(8, 8))
    if reference_lines:
        reference = LineString(reference_lines[0])
        xs, ys = reference.xy
        ax.plot(xs, ys, color="#1f77b4", linewidth=2.5, label="reference")
    if prediction_lines:
        prediction = LineString(prediction_lines[0])
        xs, ys = prediction.xy
        ax.plot(xs, ys, color="#d62728", linewidth=2.0, linestyle="--", label="prediction")
    ax.set_title(title)
    ax.legend()
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="box")
    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=200)
    plt.close(fig)


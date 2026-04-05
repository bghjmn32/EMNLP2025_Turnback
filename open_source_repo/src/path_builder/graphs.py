from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .execution import PathBuilder
from .models import DatasetExample, GraphSnapshotManifest, LatLon
from .io import read_json, write_json


class GraphSnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def snapshot_dir(self, example: DatasetExample) -> Path:
        parts = [self.root, example.corpus]
        if example.city:
            parts.append(example.city)
        if example.difficulty:
            parts.append(example.difficulty)
        parts.append(example.example_id)
        return Path(*parts)

    def graph_path(self, example: DatasetExample) -> Path:
        return self.snapshot_dir(example) / "graph.graphml"

    def manifest_path(self, example: DatasetExample) -> Path:
        return self.snapshot_dir(example) / "manifest.json"

    def has_snapshot(self, example: DatasetExample) -> bool:
        return self.graph_path(example).exists() and self.manifest_path(example).exists()

    def load_manifest(self, example: DatasetExample) -> GraphSnapshotManifest | None:
        path = self.manifest_path(example)
        if not path.exists():
            return None
        payload = read_json(path)
        return GraphSnapshotManifest(**payload)

    def store_graph(
        self,
        example: DatasetExample,
        graph,
        *,
        dist: int,
        network_type: str = "walk",
        graph_source: str = "live-captured",
    ) -> GraphSnapshotManifest:
        import osmnx as ox

        target_dir = self.snapshot_dir(example)
        target_dir.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(graph, filepath=self.graph_path(example))
        manifest = GraphSnapshotManifest(
            corpus=example.corpus,
            example_id=example.example_id,
            graph_source=graph_source,
            network_type=network_type,
            dist=dist,
            created_at=datetime.now(UTC).isoformat(),
            city=example.city,
            difficulty=example.difficulty,
        )
        write_json(self.manifest_path(example), asdict(manifest))
        return manifest

    def load_builder(self, example: DatasetExample) -> PathBuilder | None:
        import osmnx as ox

        graph_path = self.graph_path(example)
        if not graph_path.exists():
            return None
        try:
            graph = ox.load_graphml(graph_path)
        except ValueError:
            # Fallback for synthetic or manually-authored snapshots that use
            # non-integer node ids instead of OSM osmid integers.
            graph = ox.load_graphml(graph_path, node_dtypes={"osmid": str})
        return PathBuilder(graph)

    def load_or_create_builder(
        self,
        example: DatasetExample,
        *,
        center: LatLon,
        dist: int,
        network_type: str = "walk",
        refresh: bool = False,
    ) -> tuple[PathBuilder, str]:
        if not refresh:
            builder = self.load_builder(example)
            if builder is not None:
                return builder, "frozen"
        builder = PathBuilder.from_osm(center, dist=dist, network_type=network_type)
        self.store_graph(example, builder.graph, dist=dist, network_type=network_type)
        return builder, "live-captured"


class SharedGraphCache:
    def __init__(self, root: str | Path):
        self.root = Path(root) / "_shared_graphs"

    def _scope_path(self, cache_key: str) -> Path:
        parts = [part for part in cache_key.split("/") if part and part not in {".", ".."}]
        if not parts:
            raise ValueError("cache_key must contain at least one non-empty path segment.")
        return self.root.joinpath(*parts)

    def graph_path(self, cache_key: str) -> Path:
        return self._scope_path(cache_key) / "graph.graphml"

    def manifest_path(self, cache_key: str) -> Path:
        return self._scope_path(cache_key) / "manifest.json"

    def has_cache(self, cache_key: str) -> bool:
        return self.graph_path(cache_key).exists() and self.manifest_path(cache_key).exists()

    def load_manifest(self, cache_key: str) -> dict[str, Any] | None:
        path = self.manifest_path(cache_key)
        if not path.exists():
            return None
        return read_json(path)

    def store_graph(
        self,
        cache_key: str,
        graph,
        *,
        corpus: str,
        graph_source: str = "live-osm",
        network_type: str = "walk",
        example_count: int = 0,
        city: str | None = None,
        difficulties: list[str] | None = None,
        padding_degrees: float = 0.01,
    ) -> dict[str, Any]:
        import osmnx as ox

        target_dir = self._scope_path(cache_key)
        target_dir.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(graph, filepath=self.graph_path(cache_key))
        manifest = {
            "cache_key": cache_key,
            "corpus": corpus,
            "city": city,
            "difficulties": difficulties or [],
            "graph_source": graph_source,
            "network_type": network_type,
            "padding_degrees": padding_degrees,
            "example_count": int(example_count),
            "created_at": datetime.now(UTC).isoformat(),
        }
        write_json(self.manifest_path(cache_key), manifest)
        return manifest

    def load_builder(self, cache_key: str) -> PathBuilder | None:
        import osmnx as ox

        graph_path = self.graph_path(cache_key)
        if not graph_path.exists():
            return None
        manifest = self.load_manifest(cache_key) or {}
        try:
            graph = ox.load_graphml(graph_path)
        except ValueError:
            graph = ox.load_graphml(graph_path, node_dtypes={"osmid": str})
        graph.graph["shared_graph_cache_key"] = cache_key
        graph.graph["shared_graph_source"] = manifest.get("graph_source", "shared-cache")
        return PathBuilder(graph)

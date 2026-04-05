from pathlib import Path

import networkx as nx
from shapely.geometry import LineString

from path_builder.evaluation import build_or_load_shared_graph_for_examples
from path_builder.graphs import GraphSnapshotStore, SharedGraphCache
from path_builder.models import DatasetExample


def build_snapshot_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.001, y=0.0)
    graph.add_edge(
        "a",
        "b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        length=111.0,
        name="Snapshot Road",
    )
    graph.add_edge(
        "b",
        "a",
        key=0,
        geometry=LineString([(0.001, 0.0), (0.0, 0.0)]),
        length=111.0,
        name="Snapshot Road",
    )
    return graph


def synthetic_example(example_id: str = "0") -> DatasetExample:
    route_dir = Path("36kroutes") / "Toronto_Canada" / "easy" / example_id
    return DatasetExample(
        corpus="36kroutes",
        example_id=example_id,
        root=route_dir,
        route_geojson_path=route_dir / "route.geojson",
        instructions_path=route_dir / "instructions.txt",
        natural_instructions_path=route_dir / "natural_instructions.txt",
        parsed_instructions_path=route_dir / "instructions_parse.txt",
        reverse_route_path=None,
        start=(0.0, 0.0),
        end=(0.0, 0.001),
        city="Toronto_Canada",
        difficulty="easy",
    )


def test_graph_snapshot_store_layout(tmp_path: Path) -> None:
    store = GraphSnapshotStore(tmp_path)
    example = synthetic_example("0")
    assert store.snapshot_dir(example) == tmp_path / "36kroutes" / "Toronto_Canada" / "easy" / "0"
    assert store.graph_path(example) == tmp_path / "36kroutes" / "Toronto_Canada" / "easy" / "0" / "graph.graphml"
    assert store.manifest_path(example) == tmp_path / "36kroutes" / "Toronto_Canada" / "easy" / "0" / "manifest.json"


def test_shared_graph_cache_roundtrip(tmp_path: Path) -> None:
    cache = SharedGraphCache(tmp_path)
    manifest = cache.store_graph(
        "36kroutes/Toronto_Canada/easy/walk",
        build_snapshot_graph(),
        corpus="36kroutes",
        city="Toronto_Canada",
        difficulties=["easy"],
        network_type="walk",
        example_count=4,
        padding_degrees=0.02,
    )

    assert manifest["city"] == "Toronto_Canada"
    assert cache.has_cache("36kroutes/Toronto_Canada/easy/walk") is True
    builder = cache.load_builder("36kroutes/Toronto_Canada/easy/walk")
    assert builder is not None
    assert builder.graph.graph["shared_graph_cache_key"] == "36kroutes/Toronto_Canada/easy/walk"


def test_shared_graph_builder_prefers_frozen_route_snapshots(tmp_path: Path, monkeypatch) -> None:
    snapshot_root = tmp_path / "snapshots"
    example_a = synthetic_example("1")
    example_b = DatasetExample(
        corpus="36kroutes",
        example_id="2",
        root=tmp_path / "36kroutes" / "Toronto_Canada" / "medium" / "2",
        route_geojson_path=tmp_path / "36kroutes" / "Toronto_Canada" / "medium" / "2" / "route.geojson",
        instructions_path=None,
        natural_instructions_path=None,
        parsed_instructions_path=None,
        reverse_route_path=None,
        start=(0.0, 0.001),
        end=(0.0, 0.002),
        city="Toronto_Canada",
        difficulty="medium",
    )

    store = GraphSnapshotStore(snapshot_root)
    graph_a = build_snapshot_graph()
    graph_b = nx.relabel_nodes(build_snapshot_graph(), {"a": "c", "b": "d"})
    store.store_graph(example_a, graph_a, dist=1200, network_type="walk")
    store.store_graph(example_b, graph_b, dist=1200, network_type="walk")

    monkeypatch.setattr(
        "path_builder.evaluation.build_shared_graph_for_examples",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("live OSM build should not run when snapshots are available")
        ),
    )

    builder = build_or_load_shared_graph_for_examples(
        [example_a, example_b],
        cache_dir=snapshot_root,
        cache_key="36kroutes/Toronto_Canada/__all__/walk",
    )
    assert builder is not None
    assert len(builder.graph.nodes) == 4
    assert SharedGraphCache(snapshot_root).has_cache("36kroutes/Toronto_Canada/__all__/walk") is True


import json

import networkx as nx
import numpy as np

from path_builder import generation
from path_builder.models import RouteAuditRecord


def _fake_prepare_city_graph(*_args, **_kwargs):
    graph = nx.MultiDiGraph()
    graph.add_node(0, x=0.0, y=0.0)
    graph.add_node(1, x=0.001, y=0.0)
    graph.add_node(2, x=0.002, y=0.0)
    graph.add_node(3, x=0.003, y=0.0)
    graph.add_edge(0, 1, length=600.0)
    graph.add_edge(1, 2, length=900.0)
    graph.add_edge(2, 3, length=700.0)
    graph.add_edge(1, 0, length=600.0)
    graph.add_edge(2, 1, length=900.0)
    graph.add_edge(3, 2, length=700.0)
    candidate_nodes = np.array([0], dtype=object)
    node_index = [0, 1, 2, 3]
    node_to_index = {node: node for node in node_index}
    node_xy = {0: {"x": 0.0, "y": 0.0}, 1: {"x": 0.001, "y": 0.0}, 2: {"x": 0.002, "y": 0.0}, 3: {"x": 0.003, "y": 0.0}}
    return graph, None, candidate_nodes, node_index, node_to_index, node_xy


def test_build_adjacency_returns_expected_shape():
    graph = nx.MultiDiGraph()
    graph.add_nodes_from([0, 1])
    graph.add_edge(0, 1, length=12.0)
    adjacency = generation.build_adjacency(graph, [0, 1])
    assert adjacency.shape == (2, 2)
    assert adjacency.nnz == 1


def test_generate_routes_all_levels_with_monkeypatched_graph(monkeypatch):
    monkeypatch.setattr(generation, "prepare_city_graph", _fake_prepare_city_graph)
    buckets = generation.generate_routes_all_levels("synthetic", 1, 1, 1, easy_range=(500, 700), medium_range=(1400, 1600), hard_range=(2100, 2300))
    assert len(buckets["easy"].routes) == 1
    assert len(buckets["medium"].routes) == 1
    assert len(buckets["hard"].routes) == 1


def test_generate_routes_all_levels_v2_with_monkeypatched_graph(monkeypatch):
    monkeypatch.setattr(generation, "prepare_city_graph", _fake_prepare_city_graph)
    monkeypatch.setattr(
        generation,
        "classify_path_difficulty_v2",
        lambda distance, complexity_score, **_: (
            "easy" if 500 <= distance <= 700 else "medium" if 1400 <= distance <= 1600 else "hard" if 2100 <= distance <= 2300 else None
        ),
    )
    buckets = generation.generate_routes_all_levels_v2("synthetic", 1, 1, 1, easy_range=(500, 700), medium_range=(1400, 1600), hard_range=(2100, 2300))
    assert len(buckets["easy"].routes) == 1
    assert len(buckets["medium"].routes) == 1
    assert len(buckets["hard"].routes) == 1


def test_estimate_path_complexity_increases_with_turns():
    graph, _, _, _, _, _ = _fake_prepare_city_graph()
    short_path = generation.estimate_path_complexity(graph, [0, 1])
    longer_path = generation.estimate_path_complexity(graph, [0, 1, 2, 3])
    assert longer_path["turn_count"] > short_path["turn_count"]
    assert longer_path["complexity_score"] > short_path["complexity_score"]


def _fake_geojson_payload(start_latlon: tuple[float, float], end_latlon: tuple[float, float]) -> dict[str, object]:
    start_lat, start_lon = start_latlon
    end_lat, end_lon = end_latlon
    return {
        "type": "FeatureCollection",
        "metadata": {"query": {"coordinates": [[start_lon, start_lat], [end_lon, end_lat]]}},
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
                },
                "properties": {
                    "segments": [
                        {
                            "steps": [
                                {
                                    "name": "Main Street",
                                    "instruction": "Head east on Main Street",
                                    "distance": 300.0,
                                    "duration": 200.0,
                                },
                                {
                                    "name": "Oak Street",
                                    "instruction": "Turn left onto Oak Street",
                                    "distance": 320.0,
                                    "duration": 220.0,
                                },
                                {
                                    "name": "-",
                                    "instruction": "Arrive at your destination, straight ahead",
                                    "distance": 0.0,
                                    "duration": 0.0,
                                },
                            ]
                        }
                    ]
                },
            }
        ],
    }


def _fake_record(*, corpus: str, example_id: str, city: str | None, difficulty: str) -> RouteAuditRecord:
    return RouteAuditRecord(
        corpus=corpus,
        example_id=example_id,
        source_difficulty=difficulty,
        difficulty_v2=difficulty,
        paper_valid=True,
        invalid_reasons=[],
        route_length_m=800.0 if difficulty == "easy" else 1500.0 if difficulty == "medium" else 2100.0,
        step_count=4,
        turn_count=2,
        named_step_ratio=0.75,
        anonymous_turn_ratio=0.25,
        longest_anonymous_chain=1,
        roundabout_count=0,
        keep_count=0,
        short_turn_count=0,
        turn_density_per_km=2.0,
        complexity_score=6.0,
        city=city,
        pb_recoverable=True,
        recoverability_reasons=[],
        pb_similarity=91.0,
        pb_executor="hybrid",
        pb_hard_constraints=[],
        pb_soft_constraints=[],
    )


def _fake_buckets(num_easy: int, num_medium: int, num_hard: int) -> dict[str, generation.RouteBucket]:
    def _make_bucket(name: str, need: int, distance: float, latitude: float) -> generation.RouteBucket:
        bucket = generation.RouteBucket(name=name, need=need, distance_range=(0.0, 99999.0))
        for index in range(max(0, need)):
            start_latlon = (latitude + index * 0.0001, 0.0)
            end_latlon = (latitude + index * 0.0001, 0.01)
            bucket.routes.append((index, index + 1, distance))
            bucket.routes_latlon.append((start_latlon, end_latlon, distance))
            bucket.pairs.add((index, index + 1))
        return bucket

    return {
        "easy": _make_bucket("easy", num_easy, 700.0, 0.0),
        "medium": _make_bucket("medium", num_medium, 1500.0, 1.0),
        "hard": _make_bucket("hard", num_hard, 2200.0, 2.0),
    }


class _FakeORSClient:
    def batch_directions(
        self,
        routes: list[tuple[tuple[float, float], tuple[float, float], float]],
    ) -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        for start_latlon, end_latlon, _ in routes:
            payloads.append(_fake_geojson_payload(start_latlon, end_latlon))
        return payloads


def test_generate_routes_pipeline_success_writes_route_and_manifest(monkeypatch, tmp_path):
    import path_builder.paper as paper

    monkeypatch.setattr(
        generation,
        "generate_routes_all_levels_v2",
        lambda city_name, num_easy, num_medium, num_hard, **_: _fake_buckets(
            num_easy,
            num_medium,
            num_hard,
        ),
    )
    monkeypatch.setattr(generation, "_build_ors_client", lambda *_args, **_kwargs: _FakeORSClient())
    monkeypatch.setattr(
        paper,
        "audit_example",
        lambda example: _fake_record(
            corpus=example.corpus,
            example_id=example.example_id,
            city=example.city,
            difficulty=example.difficulty or "easy",
        ),
    )

    output_root = tmp_path / "generated"
    payload = generation.generate_routes_pipeline(
        ["Toronto_Canada"],
        num_easy=1,
        num_medium=0,
        num_hard=0,
        output_root=output_root,
        ors_api_key="fake-key",
        oversample_factor=2,
        probe_sample_size=4,
    )

    assert payload["overall"]["all_cities_success"] is True
    assert payload["overall"]["accepted_total"] == 1
    route_dir = output_root / "Toronto_Canada" / "easy" / "0"
    assert (route_dir / "route.geojson").exists()
    assert (route_dir / "instructions.txt").exists()
    assert (route_dir / "natural_instructions.txt").exists()
    assert (route_dir / "instructions_parse.txt").exists()
    manifest_path = output_root / "generation_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["overall"]["all_cities_success"] is True
    assert manifest["cities"][0]["accepted_counts"]["easy"] == 1
    audit_manifest_path = output_root / "route_audit_manifest.json"
    assert audit_manifest_path.exists()
    audit_manifest = json.loads(audit_manifest_path.read_text(encoding="utf-8"))
    assert len(audit_manifest["records"]) == 1
    assert audit_manifest["records"][0]["pb_recoverable"] is True
    assert payload["audit_manifest_path"] == str(audit_manifest_path)


def test_generate_routes_pipeline_repulls_until_success(monkeypatch, tmp_path):
    call_counter = {"count": 0}

    def _fake_run_city_attempt(*args, stage_city_dir, **kwargs):
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return {"success": False, "failure_reason": "probe_rate_below_gate"}, {"easy": [], "medium": [], "hard": []}
        route_dir = stage_city_dir / "easy" / "candidate_0"
        route_dir.mkdir(parents=True, exist_ok=True)
        (route_dir / "route.geojson").write_text(
            json.dumps(_fake_geojson_payload((0.0, 0.0), (0.0, 0.01))),
            encoding="utf-8",
        )
        (route_dir / "instructions.txt").write_text("", encoding="utf-8")
        (route_dir / "natural_instructions.txt").write_text("", encoding="utf-8")
        (route_dir / "instructions_parse.txt").write_text("", encoding="utf-8")
        record = _fake_record(
            corpus="36kroutes",
            example_id="candidate_0",
            city="Munich_Germany",
            difficulty="easy",
        )
        return {"success": True}, {"easy": [(route_dir, record)], "medium": [], "hard": []}

    monkeypatch.setattr(generation, "_run_city_attempt", _fake_run_city_attempt)

    output_root = tmp_path / "generated"
    payload = generation.generate_routes_pipeline(
        ["Munich_Germany"],
        num_easy=1,
        num_medium=0,
        num_hard=0,
        output_root=output_root,
        ors_api_key="fake-key",
        max_graph_repulls=2,
    )

    assert call_counter["count"] == 2
    attempts = payload["cities"][0]["attempts"]
    assert len(attempts) == 2
    assert attempts[0]["success"] is False
    assert attempts[1]["success"] is True
    assert (output_root / "Munich_Germany" / "easy" / "0" / "route.geojson").exists()


def test_generate_routes_pipeline_rejects_pb_unrecoverable_routes(monkeypatch, tmp_path):
    import path_builder.paper as paper

    monkeypatch.setattr(
        generation,
        "generate_routes_all_levels_v2",
        lambda city_name, num_easy, num_medium, num_hard, **_: _fake_buckets(
            num_easy,
            num_medium,
            num_hard,
        ),
    )
    monkeypatch.setattr(generation, "_build_ors_client", lambda *_args, **_kwargs: _FakeORSClient())

    def _fake_unrecoverable(example):
        record = _fake_record(
            corpus=example.corpus,
            example_id=example.example_id,
            city=example.city,
            difficulty=example.difficulty or "easy",
        )
        record.pb_recoverable = False
        record.recoverability_reasons = ["named-street-oov"]
        record.pb_hard_constraints = ["named-street-oov"]
        return record

    monkeypatch.setattr(paper, "audit_example", _fake_unrecoverable)

    output_root = tmp_path / "generated"
    payload = generation.generate_routes_pipeline(
        ["Toronto_Canada"],
        num_easy=1,
        num_medium=0,
        num_hard=0,
        output_root=output_root,
        ors_api_key="fake-key",
        oversample_factor=2,
        probe_sample_size=4,
    )

    assert payload["overall"]["all_cities_success"] is False
    attempt = payload["cities"][0]["attempts"][0]
    assert attempt["probe_pb_recoverable"] == 0
    assert attempt["gate_metric"] == "pb_recoverable_rate"

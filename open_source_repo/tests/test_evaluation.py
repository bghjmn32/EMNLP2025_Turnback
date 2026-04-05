import json

import path_builder.evaluation as evaluation_module
from path_builder.datasets import load_route_example
from path_builder.models import CorpusEvaluationRow


def _write_route_example(path, *, coordinates, instructions):
    path.mkdir(parents=True, exist_ok=True)
    route = {
        "type": "FeatureCollection",
        "metadata": {
            "query": {
                "coordinates": [coordinates[0], coordinates[-1]],
            }
        },
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {},
            }
        ],
    }
    (path / "route.geojson").write_text(json.dumps(route), encoding="utf-8")
    (path / "instructions.txt").write_text("\n".join(instructions) + "\n", encoding="utf-8")


def test_evaluate_route_examples_parallel_uses_process_pool_and_preserves_order(tmp_path, monkeypatch):
    route_one = tmp_path / "Toronto_Canada" / "easy" / "1"
    route_two = tmp_path / "Toronto_Canada" / "easy" / "2"
    instructions = [
        "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
        "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
        "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
    ]
    _write_route_example(route_one, coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)], instructions=instructions)
    _write_route_example(route_two, coordinates=[(0.0, 0.0), (0.002, 0.0), (0.002, 0.002)], instructions=instructions)
    examples = [
        load_route_example(route_one, corpus="36kroutes", city="Toronto_Canada", difficulty="easy"),
        load_route_example(route_two, corpus="36kroutes", city="Toronto_Canada", difficulty="easy"),
    ]

    observed: dict[str, object] = {}

    class _FakeExecutor:
        def __init__(self, max_workers):
            observed["max_workers"] = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def map(self, func, payloads):
            return [func(payload) for payload in payloads]

    def _fake_worker(payload):
        example = payload["example"]
        return CorpusEvaluationRow(
            corpus=example.corpus,
            example_id=example.example_id,
            similarity=float(example.example_id),
            length_ratio=100.0,
            hausdorff=100.0,
            iou=100.0,
            angle=100.0,
            endpoints_shift=100.0,
            edr=100.0,
            waypoint_count=3,
            segment_count=2,
            graph_source="frozen",
            executor="greedy",
            city=example.city,
            difficulty=example.difficulty,
        )

    monkeypatch.setattr(evaluation_module, "ProcessPoolExecutor", _FakeExecutor)
    monkeypatch.setattr(evaluation_module, "_evaluate_example_worker", _fake_worker)

    rows = evaluation_module.evaluate_route_examples(examples, jobs=2, snapshot_dir=tmp_path / "snapshots")

    assert observed["max_workers"] == 2
    assert [row.example_id for row in rows] == ["1", "2"]

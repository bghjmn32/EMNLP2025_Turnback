import json
from types import SimpleNamespace

import networkx as nx
import path_builder.paper as paper_module
from path_builder.datasets import load_route_example
from path_builder.models import ExecutionState, ExecutionTrace
from path_builder.models import CorpusEvaluationRow, RouteAuditRecord
from path_builder.paper import (
    audit_example,
    build_guardrail_records,
    build_success_summary,
    filter_examples_by_manifest,
    load_route_audit_manifest,
    summarize_route_audit,
    write_route_audit_manifest,
)


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


def test_audit_example_assigns_paper_valid_and_difficulty_v2(tmp_path):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    example = load_route_example(route_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    record = audit_example(example)
    assert record.paper_valid is True
    assert record.difficulty_v2 == "easy"
    assert record.turn_count == 1
    assert record.named_step_ratio > 0.9


def test_manifest_roundtrip_and_filtering(tmp_path):
    valid_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    invalid_dir = tmp_path / "Toronto_Canada" / "hard" / "2"
    _write_route_example(
        valid_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    _write_route_example(
        invalid_dir,
        coordinates=[(0.0, 0.0), (0.004, 0.0), (0.008, 0.0)],
        instructions=[
            "Name: -, Instruction: Head east, Distance: 880.0 meters, Time: 600.0 seconds",
            "Name: -, Instruction: Turn right, Distance: 0.0 meters, Time: 0.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    valid_example = load_route_example(valid_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    invalid_example = load_route_example(invalid_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="hard")
    records = [audit_example(valid_example), audit_example(invalid_example)]
    manifest_path = tmp_path / "paper_valid.json"
    write_route_audit_manifest(records, manifest_path)
    loaded = load_route_audit_manifest(manifest_path)
    filtered = filter_examples_by_manifest([valid_example, invalid_example], loaded, paper_valid_only=True)
    assert [example.example_id for example in filtered] == ["1"]
    summary = summarize_route_audit(loaded)
    assert summary["paper_valid_count"] == 1
    assert summary["invalid_reasons"]


def test_summarize_route_audit_reports_pb_recoverable_rates():
    records = [
        RouteAuditRecord(
            corpus="36kroutes",
            example_id="1",
            source_difficulty="easy",
            difficulty_v2="easy",
            paper_valid=True,
            invalid_reasons=[],
            route_length_m=800.0,
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
            city="Toronto_Canada",
            pb_recoverable=True,
        ),
        RouteAuditRecord(
            corpus="36kroutes",
            example_id="2",
            source_difficulty="easy",
            difficulty_v2="easy",
            paper_valid=True,
            invalid_reasons=[],
            route_length_m=820.0,
            step_count=4,
            turn_count=2,
            named_step_ratio=0.75,
            anonymous_turn_ratio=0.25,
            longest_anonymous_chain=1,
            roundabout_count=0,
            keep_count=0,
            short_turn_count=0,
            turn_density_per_km=2.0,
            complexity_score=6.5,
            city="Toronto_Canada",
            pb_recoverable=False,
            recoverability_reasons=["named-street-oov"],
        ),
    ]
    summary = summarize_route_audit(records)
    assert summary["pb_recoverable_count"] == 1
    assert summary["pb_recoverable_rate"] == 0.5
    assert summary["by_city"]["Toronto_Canada"]["pb_recoverable_rate"] == 0.5
    assert summary["by_difficulty_v2"]["easy"]["pb_recoverable_rate"] == 0.5
    assert summary["recoverability_reasons"] == {"named-street-oov": 1}


def test_manifest_filter_can_require_pb_recoverable(tmp_path):
    valid_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    other_dir = tmp_path / "Toronto_Canada" / "easy" / "2"
    _write_route_example(
        valid_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    _write_route_example(
        other_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    valid_example = load_route_example(valid_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    other_example = load_route_example(other_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    records = [
        RouteAuditRecord(
            corpus="36kroutes",
            example_id="1",
            source_difficulty="easy",
            difficulty_v2="easy",
            paper_valid=True,
            invalid_reasons=[],
            route_length_m=800.0,
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
            city="Toronto_Canada",
            pb_recoverable=True,
        ),
        RouteAuditRecord(
            corpus="36kroutes",
            example_id="2",
            source_difficulty="easy",
            difficulty_v2="easy",
            paper_valid=True,
            invalid_reasons=[],
            route_length_m=800.0,
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
            city="Toronto_Canada",
            pb_recoverable=False,
            recoverability_reasons=["named-street-oov"],
        ),
    ]
    manifest_path = tmp_path / "paper_valid.json"
    write_route_audit_manifest(records, manifest_path)
    loaded = load_route_audit_manifest(manifest_path)
    filtered = filter_examples_by_manifest(
        [valid_example, other_example],
        loaded,
        paper_valid_only=True,
        pb_recoverable_only=True,
    )
    assert [example.example_id for example in filtered] == ["1"]


def test_audit_example_can_attach_pb_recoverability(tmp_path, monkeypatch):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    example = load_route_example(route_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    monkeypatch.setattr(
        paper_module,
        "_audit_pb_recoverability",
        lambda *args, **kwargs: {
            "pb_recoverable": True,
            "recoverability_reasons": [],
            "pb_similarity": 88.5,
            "pb_executor": "hybrid",
            "pb_hard_constraints": [],
            "pb_soft_constraints": ["high-local-ambiguity"],
        },
    )
    record = audit_example(example, pb_check=True)
    assert record.pb_recoverable is True
    assert record.pb_similarity == 88.5
    assert record.pb_executor == "hybrid"
    assert record.pb_soft_constraints == ["high-local-ambiguity"]


def test_audit_example_localizes_provided_builder_before_pb_check(tmp_path, monkeypatch):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    example = load_route_example(route_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")

    observed: dict[str, object] = {}

    class _LocalBuilder:
        def __init__(self):
            self.graph = nx.MultiDiGraph()
            self.graph.add_node("a", x=0.0, y=0.0)
            self.graph.add_node("b", x=0.001, y=0.0)
            self.graph.add_node("c", x=0.001, y=0.001)
            self.graph.add_edge("a", "b", key=0, length=111.0, name="Main Street")
            self.graph.add_edge("b", "c", key=0, length=111.0, name="Oak Street")

        def execute(self, commands, state, executor="hybrid"):
            observed["executor"] = executor
            return ExecutionTrace(
                initial_state=state,
                final_state=ExecutionState(current_coordinates=state.current_coordinates, current_heading=state.current_heading),
                waypoints=[state.current_coordinates],
            )

        def trace_to_geojson(self, trace):
            return {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [0.001, 0.0]]}, "properties": {}}],
            }

    class _SharedBuilder:
        def local_view(self, center, dist):
            observed["center"] = center
            observed["dist"] = dist
            return _LocalBuilder()

    monkeypatch.setattr(
        "path_builder.similarity.score_geojson_routes",
        lambda *_args, **_kwargs: SimpleNamespace(similarity=88.5),
    )
    monkeypatch.setattr(
        "path_builder.ceiling.summarize_execution_ceiling",
        lambda *args, **kwargs: {"summary": {"hard_constraints": [], "soft_constraints": []}},
    )

    record = audit_example(example, pb_check=True, builder=_SharedBuilder())
    assert observed["center"] == (0.0, 0.0)
    assert int(observed["dist"]) >= 1200
    assert observed["executor"] == "greedy"
    assert record.pb_recoverable is True


def test_audit_example_pb_check_short_circuits_on_greedy_recoverable(tmp_path, monkeypatch):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    example = load_route_example(route_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    observed: list[str] = []

    class _LocalBuilder:
        def __init__(self):
            self.graph = nx.MultiDiGraph()
            self.graph.add_node("a", x=0.0, y=0.0)
            self.graph.add_node("b", x=0.001, y=0.0)
            self.graph.add_node("c", x=0.001, y=0.001)
            self.graph.add_edge("a", "b", key=0, length=111.0, name="Main Street")
            self.graph.add_edge("b", "c", key=0, length=111.0, name="Oak Street")

        def execute(self, commands, state, executor="hybrid"):
            observed.append(executor)
            return ExecutionTrace(
                initial_state=state,
                final_state=ExecutionState(current_coordinates=state.current_coordinates, current_heading=state.current_heading),
                waypoints=[state.current_coordinates],
            )

        def trace_to_geojson(self, trace):
            return {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [0.001, 0.0]]}, "properties": {}}],
            }

    class _SharedBuilder:
        def local_view(self, center, dist):
            return _LocalBuilder()

    monkeypatch.setattr(
        "path_builder.similarity.score_geojson_routes",
        lambda *_args, **_kwargs: SimpleNamespace(similarity=88.5),
    )
    monkeypatch.setattr(
        "path_builder.ceiling.summarize_execution_ceiling",
        lambda *args, **kwargs: {"summary": {"hard_constraints": [], "soft_constraints": []}},
    )

    record = audit_example(example, pb_check=True, builder=_SharedBuilder(), executor="hybrid")
    assert observed == ["greedy"]
    assert record.pb_executor == "greedy"
    assert record.pb_recoverable is True


def test_audit_example_pb_check_escalates_to_requested_executor_on_greedy_hard_constraints(tmp_path, monkeypatch):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    example = load_route_example(route_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    observed: list[str] = []

    class _LocalBuilder:
        def __init__(self):
            self.graph = nx.MultiDiGraph()
            self.graph.add_node("a", x=0.0, y=0.0)
            self.graph.add_node("b", x=0.001, y=0.0)
            self.graph.add_node("c", x=0.001, y=0.001)
            self.graph.add_edge("a", "b", key=0, length=111.0, name="Main Street")
            self.graph.add_edge("b", "c", key=0, length=111.0, name="Oak Street")

        def execute(self, commands, state, executor="hybrid"):
            observed.append(executor)
            return ExecutionTrace(
                initial_state=state,
                final_state=ExecutionState(current_coordinates=state.current_coordinates, current_heading=state.current_heading),
                waypoints=[state.current_coordinates],
                step_diagnostics=[],
            )

        def trace_to_geojson(self, trace):
            return {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [0.001, 0.0]]}, "properties": {}}],
            }

    class _SharedBuilder:
        def local_view(self, center, dist):
            return _LocalBuilder()

    monkeypatch.setattr(
        "path_builder.similarity.score_geojson_routes",
        lambda *_args, **_kwargs: SimpleNamespace(similarity=88.5),
    )

    call_counter = {"count": 0}

    def _fake_summary(*args, **kwargs):
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return {"summary": {"hard_constraints": ["named-street-beyond-recovery"], "soft_constraints": []}}
        return {"summary": {"hard_constraints": [], "soft_constraints": ["high-local-ambiguity"]}}

    monkeypatch.setattr("path_builder.ceiling.summarize_execution_ceiling", _fake_summary)

    record = audit_example(example, pb_check=True, builder=_SharedBuilder(), executor="hybrid")
    assert observed == ["greedy", "hybrid"]
    assert record.pb_executor == "hybrid"
    assert record.pb_recoverable is True
    assert record.pb_soft_constraints == ["high-local-ambiguity"]


def test_audit_example_pb_check_short_circuits_on_greedy_oov_hard_constraint(tmp_path, monkeypatch):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    example = load_route_example(route_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")
    observed: list[str] = []

    class _LocalBuilder:
        def __init__(self):
            self.graph = nx.MultiDiGraph()
            self.graph.add_node("a", x=0.0, y=0.0)
            self.graph.add_node("b", x=0.001, y=0.0)
            self.graph.add_node("c", x=0.001, y=0.001)
            self.graph.add_edge("a", "b", key=0, length=111.0, name="Main Street")
            self.graph.add_edge("b", "c", key=0, length=111.0, name="Oak Street")

        def execute(self, commands, state, executor="hybrid"):
            observed.append(executor)
            return ExecutionTrace(
                initial_state=state,
                final_state=ExecutionState(current_coordinates=state.current_coordinates, current_heading=state.current_heading),
                waypoints=[state.current_coordinates],
                step_diagnostics=[],
            )

        def trace_to_geojson(self, trace):
            return {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [0.001, 0.0]]}, "properties": {}}],
            }

    class _SharedBuilder:
        def local_view(self, center, dist):
            return _LocalBuilder()

    monkeypatch.setattr(
        "path_builder.similarity.score_geojson_routes",
        lambda *_args, **_kwargs: SimpleNamespace(similarity=70.0),
    )
    monkeypatch.setattr(
        "path_builder.ceiling.summarize_execution_ceiling",
        lambda *args, **kwargs: {"summary": {"hard_constraints": ["named-street-oov"], "soft_constraints": []}},
    )

    record = audit_example(example, pb_check=True, builder=_SharedBuilder(), executor="hybrid")
    assert observed == ["greedy"]
    assert record.pb_executor == "greedy"
    assert record.pb_recoverable is False
    assert record.pb_hard_constraints == ["named-street-oov"]


def test_audit_example_pb_check_prechecks_oov_without_execution(tmp_path):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Missing Street, Instruction: Head east on Missing Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Another Missing Street, Instruction: Turn left onto Another Missing Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    example = load_route_example(route_dir, corpus="36kroutes", city="Toronto_Canada", difficulty="easy")

    class _LocalBuilder:
        def __init__(self):
            self.graph = nx.MultiDiGraph()
            self.graph.add_node("a", x=0.0, y=0.0)
            self.graph.add_node("b", x=0.001, y=0.0)
            self.graph.add_edge("a", "b", key=0, length=111.0, name="Existing Street")

        def execute(self, commands, state, executor="hybrid"):
            raise AssertionError("execute should not run for named-street-oov precheck")

    class _SharedBuilder:
        def local_view(self, center, dist):
            return _LocalBuilder()

    record = audit_example(example, pb_check=True, builder=_SharedBuilder(), executor="hybrid")
    assert record.pb_recoverable is False
    assert record.pb_executor == "greedy"
    assert record.pb_similarity is None
    assert record.pb_hard_constraints == ["named-street-oov"]


def test_audit_corpus_can_use_shared_graph_builder(tmp_path, monkeypatch):
    route_dir = tmp_path / "Toronto_Canada" / "easy" / "1"
    _write_route_example(
        route_dir,
        coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)],
        instructions=[
            "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
            "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
        ],
    )
    shared_builder = object()
    monkeypatch.setattr(
        "path_builder.evaluation.build_shared_graph_bundle",
        lambda *args, **kwargs: {"Toronto_Canada": shared_builder},
    )

    observed: list[object | None] = []
    original_audit_example = paper_module.audit_example

    def _fake_audit_example(example, **kwargs):
        observed.append(kwargs.get("builder"))
        return original_audit_example(example)

    monkeypatch.setattr(paper_module, "audit_example", _fake_audit_example)
    records = paper_module.audit_corpus(
        "36kroutes",
        root=tmp_path,
        cities=["Toronto_Canada"],
        difficulties=["easy"],
        shared_graph=True,
    )
    assert len(records) == 1
    assert observed == [shared_builder]


def test_audit_corpus_parallel_uses_process_pool_and_preserves_order(tmp_path, monkeypatch):
    route_one = tmp_path / "Toronto_Canada" / "easy" / "1"
    route_two = tmp_path / "Toronto_Canada" / "easy" / "2"
    instructions = [
        "Name: Main Street, Instruction: Head east on Main Street, Distance: 330.0 meters, Time: 240.0 seconds",
        "Name: Oak Street, Instruction: Turn left onto Oak Street, Distance: 330.0 meters, Time: 240.0 seconds",
        "Name: -, Instruction: Arrive at your destination, straight ahead, Distance: 0.0 meters, Time: 0.0 seconds",
    ]
    _write_route_example(route_one, coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)], instructions=instructions)
    _write_route_example(route_two, coordinates=[(0.0, 0.0), (0.003, 0.0), (0.003, 0.003)], instructions=instructions)

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
        return RouteAuditRecord(
            corpus=example.corpus,
            example_id=example.example_id,
            source_difficulty=example.difficulty,
            difficulty_v2=example.difficulty,
            paper_valid=True,
            invalid_reasons=[],
            route_length_m=800.0,
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
            city=example.city,
            pb_recoverable=True,
        )

    monkeypatch.setattr(paper_module, "ProcessPoolExecutor", _FakeExecutor)
    monkeypatch.setattr(paper_module, "_audit_example_worker", _fake_worker)

    records = paper_module.audit_corpus(
        "36kroutes",
        root=tmp_path,
        cities=["Toronto_Canada"],
        difficulties=["easy"],
        jobs=2,
    )

    assert observed["max_workers"] == 2
    assert [record.example_id for record in records] == ["1", "2"]


def test_build_success_summary_counts_rows_above_threshold():
    rows = [
        CorpusEvaluationRow(
            corpus="36kroutes",
            example_id="1",
            similarity=90.0,
            length_ratio=90.0,
            hausdorff=90.0,
            iou=90.0,
            angle=90.0,
            endpoints_shift=90.0,
            edr=90.0,
            waypoint_count=10,
            segment_count=9,
            graph_source="frozen",
            executor="greedy",
            city="Toronto_Canada",
            difficulty="easy",
        ),
        CorpusEvaluationRow(
            corpus="36kroutes",
            example_id="2",
            similarity=70.0,
            length_ratio=70.0,
            hausdorff=70.0,
            iou=70.0,
            angle=70.0,
            endpoints_shift=70.0,
            edr=70.0,
            waypoint_count=10,
            segment_count=9,
            graph_source="frozen",
            executor="greedy",
            city="Toronto_Canada",
            difficulty="easy",
        ),
    ]
    summary = build_success_summary(rows, success_threshold=85.0)
    assert summary["success_count"] == 1
    assert summary["success_rate"] == 0.5


def test_build_guardrail_records_balances_city_and_source_difficulty():
    records: list[RouteAuditRecord] = []
    for city in ["Toronto_Canada", "Tokyo_23_wards"]:
        for difficulty in ["easy", "medium"]:
            for index in range(4):
                records.append(
                    RouteAuditRecord(
                        corpus="36kroutes",
                        example_id=str(index),
                        source_difficulty=difficulty,
                        difficulty_v2=difficulty,
                        paper_valid=True,
                        invalid_reasons=[],
                        route_length_m=800.0 if difficulty == "easy" else 1500.0,
                        step_count=6,
                        turn_count=3,
                        named_step_ratio=0.4,
                        anonymous_turn_ratio=0.6,
                        longest_anonymous_chain=index + 1,
                        roundabout_count=0,
                        keep_count=0,
                        short_turn_count=0,
                        turn_density_per_km=6.0,
                        complexity_score=5.0 + index,
                        city=city,
                    )
                )
    selected = build_guardrail_records(records, per_city_difficulty=2)
    assert len(selected) == 8
    counts: dict[tuple[str | None, str | None], int] = {}
    for record in selected:
        key = (record.city, record.source_difficulty)
        counts[key] = counts.get(key, 0) + 1
    assert counts == {
        ("Tokyo_23_wards", "easy"): 2,
        ("Tokyo_23_wards", "medium"): 2,
        ("Toronto_Canada", "easy"): 2,
        ("Toronto_Canada", "medium"): 2,
    }


def test_build_guardrail_records_can_require_pb_recoverable():
    records = [
        RouteAuditRecord(
            corpus="36kroutes",
            example_id="0",
            source_difficulty="easy",
            difficulty_v2="easy",
            paper_valid=True,
            invalid_reasons=[],
            route_length_m=800.0,
            step_count=6,
            turn_count=3,
            named_step_ratio=0.4,
            anonymous_turn_ratio=0.6,
            longest_anonymous_chain=1,
            roundabout_count=0,
            keep_count=0,
            short_turn_count=0,
            turn_density_per_km=6.0,
            complexity_score=5.0,
            city="Toronto_Canada",
            pb_recoverable=True,
        ),
        RouteAuditRecord(
            corpus="36kroutes",
            example_id="1",
            source_difficulty="easy",
            difficulty_v2="easy",
            paper_valid=True,
            invalid_reasons=[],
            route_length_m=820.0,
            step_count=6,
            turn_count=3,
            named_step_ratio=0.4,
            anonymous_turn_ratio=0.6,
            longest_anonymous_chain=2,
            roundabout_count=0,
            keep_count=0,
            short_turn_count=0,
            turn_density_per_km=6.0,
            complexity_score=6.0,
            city="Toronto_Canada",
            pb_recoverable=False,
        ),
    ]
    selected = build_guardrail_records(records, per_city_difficulty=2, pb_recoverable_only=True)
    assert [record.example_id for record in selected] == ["0"]

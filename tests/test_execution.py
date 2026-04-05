import networkx as nx
import pytest
from shapely.geometry import LineString

import path_builder.execution as execution_module
from path_builder.execution import (
    EdgeCandidate,
    PathBuilder,
    _carry_forward_current_street,
    _named_street_recovery_limit,
    _prefer_current_street_for_step,
    recommended_graph_dist,
)
from path_builder.models import ExecutionCandidateDiagnostic, ExecutionState, ExecutionStepDiagnostic, ExecutionTrace, NavigationCommand


def build_synthetic_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.001, y=0.0)
    graph.add_node("c", x=0.001, y=-0.001)
    east = LineString([(0.0, 0.0), (0.001, 0.0)])
    south = LineString([(0.001, 0.0), (0.001, -0.001)])
    graph.add_edge("a", "b", key=0, geometry=east, length=111.0, name="East Road")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(east.coords)[::-1]), length=111.0, name="East Road")
    graph.add_edge("b", "c", key=0, geometry=south, length=111.0, name="South Road")
    graph.add_edge("c", "b", key=0, geometry=LineString(list(south.coords)[::-1]), length=111.0, name="South Road")
    return graph


def build_midblock_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.0, y=0.001)
    graph.add_node("c", x=0.0, y=0.002)
    north_1 = LineString([(0.0, 0.0), (0.0, 0.001)])
    north_2 = LineString([(0.0, 0.001), (0.0, 0.002)])
    graph.add_edge("a", "b", key=0, geometry=north_1, length=111.0, name="Main Road")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(north_1.coords)[::-1]), length=111.0, name="Main Road")
    graph.add_edge("b", "c", key=0, geometry=north_2, length=111.0, name="Main Road")
    graph.add_edge("c", "b", key=0, geometry=LineString(list(north_2.coords)[::-1]), length=111.0, name="Main Road")
    return graph


def build_diagonal_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.001, y=0.001)
    diagonal = LineString([(0.0, 0.0), (0.001, 0.001)])
    graph.add_edge("a", "b", key=0, geometry=diagonal, length=157.0, name=None)
    graph.add_edge("b", "a", key=0, geometry=LineString(list(diagonal.coords)[::-1]), length=157.0, name=None)
    return graph


def build_turn_bias_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.0, y=0.001)
    graph.add_node("c", x=0.001, y=0.001)
    north = LineString([(0.0, 0.0), (0.0, 0.001)])
    east = LineString([(0.0, 0.001), (0.001, 0.001)])
    graph.add_edge("a", "b", key=0, geometry=north, length=111.0, name="North Road")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(north.coords)[::-1]), length=111.0, name="North Road")
    graph.add_edge("b", "c", key=0, geometry=east, length=111.0, name="East Road")
    graph.add_edge("c", "b", key=0, geometry=LineString(list(east.coords)[::-1]), length=111.0, name="East Road")
    return graph


def build_local_view_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("near_a", x=0.0, y=0.0)
    graph.add_node("near_b", x=0.001, y=0.0)
    graph.add_node("far_a", x=0.02, y=0.02)
    graph.add_node("far_b", x=0.021, y=0.02)
    near = LineString([(0.0, 0.0), (0.001, 0.0)])
    far = LineString([(0.02, 0.02), (0.021, 0.02)])
    graph.add_edge("near_a", "near_b", key=0, geometry=near, length=111.0, name="Near Road")
    graph.add_edge("near_b", "near_a", key=0, geometry=LineString(list(near.coords)[::-1]), length=111.0, name="Near Road")
    graph.add_edge("far_a", "far_b", key=0, geometry=far, length=111.0, name="Far Road")
    graph.add_edge("far_b", "far_a", key=0, geometry=LineString(list(far.coords)[::-1]), length=111.0, name="Far Road")
    return graph


def build_maneuver_penalty_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.0, y=0.001)
    graph.add_node("c", x=0.0, y=0.002)
    graph.add_node("d", x=0.001, y=0.001)
    south = LineString([(0.0, 0.0), (0.0, 0.001)])
    north = LineString([(0.0, 0.001), (0.0, 0.002)])
    east = LineString([(0.0, 0.001), (0.001, 0.001)])
    graph.add_edge("a", "b", key=0, geometry=south, length=111.0, name="Main Street")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(south.coords)[::-1]), length=111.0, name="Main Street")
    graph.add_edge("b", "c", key=0, geometry=north, length=111.0, name="Main Street")
    graph.add_edge("c", "b", key=0, geometry=LineString(list(north.coords)[::-1]), length=111.0, name="Main Street")
    graph.add_edge("b", "d", key=0, geometry=east, length=111.0, name="Side Road")
    graph.add_edge("d", "b", key=0, geometry=LineString(list(east.coords)[::-1]), length=111.0, name="Side Road")
    return graph


def build_named_list_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.0, y=0.001)
    graph.add_node("c", x=0.001, y=0.001)
    north = LineString([(0.0, 0.0), (0.0, 0.001)])
    east = LineString([(0.0, 0.001), (0.001, 0.001)])
    graph.add_edge("a", "b", key=0, geometry=north, length=111.0, name="North Road")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(north.coords)[::-1]), length=111.0, name="North Road")
    graph.add_edge("b", "c", key=0, geometry=east, length=111.0, name=["Target Road", "Alias Road"])
    graph.add_edge("c", "b", key=0, geometry=LineString(list(east.coords)[::-1]), length=111.0, name=["Target Road", "Alias Road"])
    return graph


def build_named_corridor_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.0, y=-0.001)
    graph.add_node("c", x=0.0, y=-0.002)
    graph.add_node("d", x=0.001, y=-0.001)
    south_1 = LineString([(0.0, 0.0), (0.0, -0.001)])
    south_2 = LineString([(0.0, -0.001), (0.0, -0.002)])
    east = LineString([(0.0, -0.001), (0.001, -0.001)])
    graph.add_edge("a", "b", key=0, geometry=south_1, length=111.0, name="Main Street")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(south_1.coords)[::-1]), length=111.0, name="Main Street")
    graph.add_edge("b", "c", key=0, geometry=south_2, length=111.0, name="Main Street")
    graph.add_edge("c", "b", key=0, geometry=LineString(list(south_2.coords)[::-1]), length=111.0, name="Main Street")
    graph.add_edge("b", "d", key=0, geometry=east, length=111.0, name=None)
    graph.add_edge("d", "b", key=0, geometry=LineString(list(east.coords)[::-1]), length=111.0, name=None)
    return graph


def build_named_turn_lookahead_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=-0.001)
    graph.add_node("b", x=0.0, y=0.0)
    graph.add_node("c", x=0.001, y=0.0)
    graph.add_node("d", x=0.002, y=-0.002)
    graph.add_node("e", x=0.001, y=-0.003)
    graph.add_node("f", x=0.001, y=-0.001)
    north = LineString([(0.0, -0.001), (0.0, 0.0)])
    east = LineString([(0.0, 0.0), (0.001, 0.0)])
    southeast = LineString([(0.0, 0.0), (0.002, -0.002)])
    southwest = LineString([(0.002, -0.002), (0.001, -0.003)])
    south_wrong = LineString([(0.001, 0.0), (0.001, -0.001)])
    graph.add_edge("a", "b", key=0, geometry=north, length=111.0, name="North Road")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(north.coords)[::-1]), length=111.0, name="North Road")
    graph.add_edge("b", "c", key=0, geometry=east, length=111.0, name="Target Road")
    graph.add_edge("c", "b", key=0, geometry=LineString(list(east.coords)[::-1]), length=111.0, name="Target Road")
    graph.add_edge("b", "d", key=0, geometry=southeast, length=314.0, name="Target Road")
    graph.add_edge("d", "b", key=0, geometry=LineString(list(southeast.coords)[::-1]), length=314.0, name="Target Road")
    graph.add_edge("d", "e", key=0, geometry=southwest, length=157.0, name="Final Road")
    graph.add_edge("e", "d", key=0, geometry=LineString(list(southwest.coords)[::-1]), length=157.0, name="Final Road")
    graph.add_edge("c", "f", key=0, geometry=south_wrong, length=111.0, name="Wrong Road")
    graph.add_edge("f", "c", key=0, geometry=LineString(list(south_wrong.coords)[::-1]), length=111.0, name="Wrong Road")
    return graph


def build_anonymous_turn_rescue_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=0.0, y=0.0)
    graph.add_node("b", x=0.0, y=0.0003)
    graph.add_node("c", x=0.0, y=0.0006)
    graph.add_node("d", x=0.0004, y=0.0003)
    north_1 = LineString([(0.0, 0.0), (0.0, 0.0003)])
    north_2 = LineString([(0.0, 0.0003), (0.0, 0.0006)])
    east = LineString([(0.0, 0.0003), (0.0004, 0.0003)])
    graph.add_edge("a", "b", key=0, geometry=north_1, length=33.0, name="Main Street")
    graph.add_edge("b", "a", key=0, geometry=LineString(list(north_1.coords)[::-1]), length=33.0, name="Main Street")
    graph.add_edge("b", "c", key=0, geometry=north_2, length=33.0, name="Main Street")
    graph.add_edge("c", "b", key=0, geometry=LineString(list(north_2.coords)[::-1]), length=33.0, name="Main Street")
    graph.add_edge("b", "d", key=0, geometry=east, length=44.0, name="Side Road")
    graph.add_edge("d", "b", key=0, geometry=LineString(list(east.coords)[::-1]), length=44.0, name="Side Road")
    return graph


def make_arrive_diagnostic(initial_state: ExecutionState, *, notes: list[str] | None = None) -> ExecutionStepDiagnostic:
    return ExecutionStepDiagnostic(
        index=0,
        step_kind="arrive",
        action="arrive",
        direction=None,
        raw_text=None,
        desired_heading=initial_state.current_heading,
        start_coordinates=initial_state.current_coordinates,
        end_coordinates=initial_state.current_coordinates,
        notes=notes or [],
    )


def test_path_builder_executes_simple_turn_sequence():
    builder = PathBuilder(build_synthetic_graph())
    commands = [
        NavigationCommand(actions=["head"], directions=["east"], distances=[111.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[111.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(commands, ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0), align_start=False)
    assert trace.final_state.current_coordinates[1] > 0.0009
    assert trace.final_state.current_coordinates[0] < -0.0009
    geojson = builder.trace_to_geojson(trace)
    assert geojson["features"][0]["geometry"]["type"] == "LineString"


def test_path_builder_keeps_midblock_start_on_same_edge():
    builder = PathBuilder(build_midblock_graph())
    commands = [
        NavigationCommand(actions=["head"], directions=["north"], distances=[80.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    start = (0.0008, 0.0)
    trace = builder.execute(commands, ExecutionState(current_coordinates=start, current_heading=0.0), align_start=False)
    first_segment = trace.segment_coordinates[0]
    assert abs(first_segment[0][0] - start[1]) < 1e-6
    assert abs(first_segment[0][1] - start[0]) < 1e-6
    assert trace.final_state.current_coordinates[0] > start[0]


def test_short_anonymous_instruction_keeps_semantic_heading():
    builder = PathBuilder(build_diagonal_graph())
    commands = [
        NavigationCommand(actions=["head"], directions=["north"], distances=[5.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(commands, ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0), align_start=False)
    assert round(trace.final_state.current_heading, 6) == 0.0


def test_turn_command_prefers_actual_turn_over_nearest_straight_edge():
    builder = PathBuilder(build_turn_bias_graph())
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    start = (0.00092, 0.00002)
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=start, current_heading=0.0, current_street="North Road"),
        align_start=False,
    )
    assert trace.final_state.current_coordinates[1] > start[1]
    assert abs(trace.final_state.current_coordinates[0] - 0.001) < 0.0002


def test_local_view_clips_far_subgraph():
    builder = PathBuilder(build_local_view_graph())
    local_builder = builder.local_view((0.0, 0.0), 250)
    assert set(local_builder.graph.nodes) == {"near_a", "near_b"}
    assert all("Far Road" not in str(data.get("name")) for _, _, data in local_builder.graph.edges(data=True))


def test_turn_diagnostics_include_maneuver_penalty_for_wrong_branch():
    builder = PathBuilder(build_maneuver_penalty_graph())
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.00092, 0.0), current_heading=0.0, current_street="Main Street"),
        align_start=False,
    )
    diagnostics = trace.step_diagnostics[0].candidate_diagnostics
    assert trace.step_diagnostics[0].selected_street == "Side Road"
    assert any(item.street == "Main Street" and item.preview_penalty > 0.0 for item in diagnostics)


def test_named_turn_matches_list_valued_edge_name():
    builder = PathBuilder(build_named_list_graph())
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Target Road"], end_streets=["Target Road"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.00095, 0.00001), current_heading=0.0, current_street="North Road"),
        align_start=False,
    )
    assert trace.step_diagnostics[0].selected_street == "Target Road"


def test_named_head_keeps_named_corridor_across_multiple_segments():
    builder = PathBuilder(build_named_corridor_graph())
    commands = [
        NavigationCommand(actions=["head"], directions=["south"], start_streets=["Main Street"], distances=[170.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=180.0),
        align_start=False,
    )
    assert trace.final_state.current_street == "Main Street"
    assert abs(trace.final_state.current_coordinates[1]) < 1e-6
    assert trace.final_state.current_coordinates[0] < -0.0014


def test_named_head_recovers_to_target_street_on_first_step():
    builder = PathBuilder(build_named_corridor_graph())
    commands = [
        NavigationCommand(actions=["head"], directions=["south"], start_streets=["Main Street"], distances=[170.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(-0.001, 0.001), current_heading=180.0),
        align_start=False,
    )
    assert trace.step_diagnostics[0].selected_street == "Main Street"
    assert any(note.startswith("named-head-recovery:") for note in trace.step_diagnostics[0].notes)
    assert trace.final_state.current_street == "Main Street"


def test_named_turn_lookahead_prefers_future_compatible_branch():
    builder = PathBuilder(build_named_turn_lookahead_graph())
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Target Road"], end_streets=["Target Road"], distances=[300.0]),
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Final Road"], end_streets=["Final Road"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="North Road"),
        align_start=False,
    )
    assert trace.step_diagnostics[0].selected_street == "Target Road"
    assert "lookahead-choice" in trace.step_diagnostics[0].notes
    assert trace.step_diagnostics[1].selected_street == "Final Road"


def test_named_oov_head_lookahead_prefers_future_named_branch():
    builder = PathBuilder(build_named_turn_lookahead_graph())
    commands = [
        NavigationCommand(actions=["head"], directions=["east"], start_streets=["Missing Road"], distances=[300.0]),
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Final Road"], end_streets=["Final Road"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="North Road"),
        align_start=False,
    )
    assert "lookahead-choice" in trace.step_diagnostics[0].notes
    assert trace.step_diagnostics[1].selected_street == "Final Road"


def test_search_executor_keeps_future_compatible_named_branch():
    builder = PathBuilder(build_named_turn_lookahead_graph())
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Target Road"], end_streets=["Target Road"], distances=[300.0]),
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Final Road"], end_streets=["Final Road"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="North Road"),
        align_start=False,
        executor="search",
    )
    assert trace.step_diagnostics[0].selected_street == "Target Road"
    assert "override-choice" in trace.step_diagnostics[0].notes
    assert trace.step_diagnostics[1].selected_street == "Final Road"


def test_search_executor_falls_back_for_low_turn_routes():
    builder = PathBuilder(build_named_corridor_graph())
    commands = [
        NavigationCommand(actions=["head"], directions=["south"], start_streets=["Main Street"], distances=[170.0]),
        NavigationCommand(actions=["turn"], directions=["left"], start_streets=["Main Street"], end_streets=["Main Street"], distances=[20.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=180.0),
        align_start=False,
        executor="search",
    )
    assert trace.step_diagnostics
    assert "search-fallback:budget" in trace.step_diagnostics[0].notes


def test_hybrid_executor_prefers_search_when_selection_cost_is_lower(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    initial_state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0)
    commands = [NavigationCommand(actions=["arrive"])]
    greedy_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )
    search_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state, notes=["override-choice"])],
    )

    monkeypatch.setattr(builder, "_execute_sequence", lambda *args, **kwargs: greedy_trace)
    monkeypatch.setattr(builder, "_execute_search", lambda *args, **kwargs: search_trace)
    monkeypatch.setattr(builder, "_search_budget_eligible", lambda commands: True)
    monkeypatch.setattr(builder, "_trace_cost", lambda trace: 2.0 if trace is greedy_trace else 1.5)
    monkeypatch.setattr(builder, "_trace_selection_cost", lambda commands, trace: 20.0 if trace is greedy_trace else 18.0)

    trace = builder.execute(commands, initial_state, align_start=False, executor="hybrid")

    assert trace is search_trace


def test_hybrid_executor_keeps_greedy_when_search_cost_is_not_lower(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    initial_state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0)
    commands = [NavigationCommand(actions=["arrive"])]
    greedy_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )
    search_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state, notes=["override-choice"])],
    )

    monkeypatch.setattr(builder, "_execute_sequence", lambda *args, **kwargs: greedy_trace)
    monkeypatch.setattr(builder, "_execute_search", lambda *args, **kwargs: search_trace)
    monkeypatch.setattr(builder, "_search_budget_eligible", lambda commands: True)
    monkeypatch.setattr(builder, "_trace_cost", lambda trace: 2.0)

    trace = builder.execute(commands, initial_state, align_start=False, executor="hybrid")

    assert trace is greedy_trace


def test_hybrid_executor_keeps_low_cost_greedy_without_large_search_selection_gain(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    initial_state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0)
    commands = [NavigationCommand(actions=["arrive"])]
    greedy_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )
    search_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state, notes=["override-choice"])],
    )

    monkeypatch.setattr(builder, "_execute_sequence", lambda *args, **kwargs: greedy_trace)
    monkeypatch.setattr(builder, "_execute_search", lambda *args, **kwargs: search_trace)
    monkeypatch.setattr(builder, "_search_budget_eligible", lambda commands: True)
    monkeypatch.setattr(builder, "_trace_cost", lambda trace: 2.0 if trace is greedy_trace else 1.5)
    monkeypatch.setattr(builder, "_trace_selection_cost", lambda commands, trace: 3.0 if trace is greedy_trace else 2.1)

    trace = builder.execute(commands, initial_state, align_start=False, executor="hybrid")

    assert trace is greedy_trace


def test_hybrid_executor_allows_search_trace_cost_fallback_for_high_cost_base(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    initial_state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0)
    commands = [NavigationCommand(actions=["arrive"])]
    greedy_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )
    search_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state, notes=["override-choice"])],
    )

    monkeypatch.setattr(builder, "_execute_sequence", lambda *args, **kwargs: greedy_trace)
    monkeypatch.setattr(builder, "_execute_search", lambda *args, **kwargs: search_trace)
    monkeypatch.setattr(builder, "_search_budget_eligible", lambda commands: True)
    monkeypatch.setattr(builder, "_trace_cost", lambda trace: 2.0 if trace is greedy_trace else 1.85)
    monkeypatch.setattr(builder, "_trace_selection_cost", lambda commands, trace: 30.0 if trace is greedy_trace else 31.4)

    trace = builder.execute(commands, initial_state, align_start=False, executor="hybrid")

    assert trace is search_trace


def test_hybrid_executor_prefers_windowed_trace_when_selection_cost_margin_is_large(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    initial_state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0)
    commands = [
        NavigationCommand(actions=["head"], directions=["north"], distances=[30.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[40.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[50.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[60.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[70.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[80.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[90.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[100.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    greedy_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )
    windowed_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )

    monkeypatch.setattr(builder, "_execute_sequence", lambda *args, **kwargs: greedy_trace)
    monkeypatch.setattr(builder, "_windowed_search_budget_eligible", lambda commands: True)
    monkeypatch.setattr(builder, "_search_budget_eligible", lambda commands: False)
    monkeypatch.setattr(builder, "_execute_windowed_search", lambda *args, **kwargs: windowed_trace)
    monkeypatch.setattr(builder, "_trace_selection_cost", lambda commands, trace: 10.0 if trace is greedy_trace else 8.5)

    trace = builder.execute(commands, initial_state, align_start=False, executor="hybrid")

    assert trace is windowed_trace
    assert "hybrid-windowed" in trace.step_diagnostics[0].notes


def test_hybrid_executor_keeps_base_trace_when_windowed_margin_is_too_small(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    initial_state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0)
    commands = [
        NavigationCommand(actions=["head"], directions=["north"], distances=[30.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[40.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[50.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[60.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[70.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[80.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[90.0]),
        NavigationCommand(actions=["turn"], directions=["left"], distances=[100.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    greedy_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )
    windowed_trace = ExecutionTrace(
        initial_state=initial_state,
        final_state=initial_state,
        waypoints=[initial_state.current_coordinates],
        traversed_edges=[],
        segment_coordinates=[],
        step_segments=[[]],
        step_diagnostics=[make_arrive_diagnostic(initial_state)],
    )

    monkeypatch.setattr(builder, "_execute_sequence", lambda *args, **kwargs: greedy_trace)
    monkeypatch.setattr(builder, "_windowed_search_budget_eligible", lambda commands: True)
    monkeypatch.setattr(builder, "_search_budget_eligible", lambda commands: False)
    monkeypatch.setattr(builder, "_execute_windowed_search", lambda *args, **kwargs: windowed_trace)
    monkeypatch.setattr(builder, "_trace_selection_cost", lambda commands, trace: 10.0 if trace is greedy_trace else 9.2)

    trace = builder.execute(commands, initial_state, align_start=False, executor="hybrid")

    assert trace is greedy_trace


def test_search_candidate_pool_skips_oov_named_turn(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    command = NavigationCommand(
        actions=["turn"],
        directions=["right"],
        start_streets=["Missing Street"],
        end_streets=["Missing Street"],
        distances=[40.0],
    )
    commands = [command, NavigationCommand(actions=["arrive"])]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="East Road")
    base_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=90.0,
        names=("East Road",),
        name="East Road",
        length_m=111.0,
    )
    alt_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, -0.001)]),
        bearing=135.0,
        names=(),
        name=None,
        length_m=157.0,
    )
    ranked_candidates = [
        (
            "a",
            base_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="East Road",
                bearing=90.0,
                street_penalty=1.0,
                turn_penalty=0.2,
                continuity_penalty=0.0,
                projection_distance_m=1.0,
                node_distance_m=1.0,
                preview_penalty=0.0,
                total_score=6.2,
            ),
        ),
        (
            "a",
            alt_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street=None,
                bearing=135.0,
                street_penalty=1.0,
                turn_penalty=0.25,
                continuity_penalty=0.0,
                projection_distance_m=2.0,
                node_distance_m=2.0,
                preview_penalty=0.0,
                total_score=6.35,
            ),
        ),
    ]

    monkeypatch.setattr(
        builder,
        "_rank_command_entry_candidates",
        lambda *args, **kwargs: (90.0, "named_turn", ["Missing Street"], ranked_candidates),
    )
    pool = builder._search_candidate_pool(commands, 0, state, command, candidate_limit=2)
    assert pool == []


def test_search_candidate_pool_skips_non_ambiguous_anonymous_turn():
    builder = PathBuilder(build_synthetic_graph())
    command = NavigationCommand(actions=["turn"], directions=["left"], distances=[35.0])
    commands = [
        command,
        NavigationCommand(actions=["continue"], directions=["keep left"], distances=[40.0]),
        NavigationCommand(actions=["continue"], directions=["keep left"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street=None)
    base_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=90.0,
        names=(),
        name=None,
        length_m=111.0,
    )
    alt_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, -0.001)]),
        bearing=135.0,
        names=(),
        name=None,
        length_m=157.0,
    )
    ranked_candidates = [
        (
            "a",
            base_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street=None,
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.12,
                continuity_penalty=0.0,
                projection_distance_m=1.0,
                node_distance_m=1.0,
                preview_penalty=0.0,
                total_score=0.42,
            ),
        ),
        (
            "a",
            alt_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street=None,
                bearing=135.0,
                street_penalty=0.0,
                turn_penalty=0.14,
                continuity_penalty=0.0,
                projection_distance_m=2.0,
                node_distance_m=2.0,
                preview_penalty=0.0,
                total_score=0.73,
            ),
        ),
    ]
    original = builder._rank_command_entry_candidates
    builder._rank_command_entry_candidates = lambda *args, **kwargs: (90.0, "anonymous_turn", [], ranked_candidates)  # type: ignore[method-assign]
    try:
        pool = builder._search_candidate_pool(commands, 0, state, command, candidate_limit=2)
    finally:
        builder._rank_command_entry_candidates = original  # type: ignore[method-assign]
    assert len(pool) == 0


def test_anonymous_turn_rescue_prefers_nearby_true_branch():
    builder = PathBuilder(build_anonymous_turn_rescue_graph())
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="Main Street"),
        align_start=False,
    )
    assert trace.step_diagnostics[0].selected_street == "Side Road"
    assert trace.final_state.current_coordinates[1] > 0.0002
    assert abs(trace.final_state.current_coordinates[0] - 0.0003) < 0.0001


def test_long_anonymous_chain_prefers_lower_suffix_cost_branch():
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=0.0,
        names=(),
        name=None,
        length_m=111.0,
    )
    alternate_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, -0.001)]),
        bearing=315.0,
        names=(),
        name=None,
        length_m=157.0,
    )
    ranked_candidates = [
        (
            "b",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="b",
                street=None,
                bearing=0.0,
                street_penalty=0.0,
                turn_penalty=0.08,
                continuity_penalty=0.0,
                projection_distance_m=1.0,
                node_distance_m=12.0,
                preview_penalty=0.0,
                total_score=0.62,
            ),
        ),
        (
            "c",
            alternate_edge,
            ExecutionCandidateDiagnostic(
                node="c",
                street=None,
                bearing=315.0,
                street_penalty=0.0,
                turn_penalty=0.24,
                continuity_penalty=0.0,
                projection_distance_m=0.5,
                node_distance_m=2.0,
                preview_penalty=0.0,
                total_score=0.78,
            ),
        ),
    ]
    commands = [
        NavigationCommand(actions=["turn"], directions=["left"], distances=[40.0]),
        NavigationCommand(actions=["continue"], directions=["keep left"], distances=[35.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[50.0]),
        NavigationCommand(actions=["continue"], directions=["keep right"], distances=[45.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street=None)

    def fake_preview_cost(
        preview_commands: list[NavigationCommand],
        preview_state: ExecutionState,
        choice: tuple[str, EdgeCandidate],
        preview_length: int,
    ) -> float:
        del preview_commands, preview_state, preview_length
        return 3.4 if choice[1] is baseline_edge else 3.1

    builder._preview_choice_cost = fake_preview_cost  # type: ignore[method-assign]
    choice = builder._choose_anonymous_chain_lookahead_edge(commands, 0, state, commands[0], ranked_candidates)

    assert choice == ("c", alternate_edge)


def test_long_anonymous_chain_can_leave_named_corridor_when_suffix_cost_is_lower():
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=0.0,
        names=("Current Road",),
        name="Current Road",
        length_m=111.0,
    )
    alternate_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, -0.001)]),
        bearing=315.0,
        names=(),
        name=None,
        length_m=157.0,
    )
    ranked_candidates = [
        (
            "b",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="b",
                street="Current Road",
                bearing=0.0,
                street_penalty=0.0,
                turn_penalty=0.08,
                continuity_penalty=0.0,
                projection_distance_m=1.0,
                node_distance_m=12.0,
                preview_penalty=0.0,
                total_score=0.62,
            ),
        ),
        (
            "c",
            alternate_edge,
            ExecutionCandidateDiagnostic(
                node="c",
                street=None,
                bearing=315.0,
                street_penalty=0.0,
                turn_penalty=0.24,
                continuity_penalty=0.0,
                projection_distance_m=0.5,
                node_distance_m=2.0,
                preview_penalty=0.0,
                total_score=0.78,
            ),
        ),
    ]
    commands = [
        NavigationCommand(actions=["turn"], directions=["left"], distances=[40.0]),
        NavigationCommand(actions=["continue"], directions=["keep left"], distances=[35.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[50.0]),
        NavigationCommand(actions=["continue"], directions=["keep right"], distances=[45.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="Current Road")

    def fake_preview_cost(
        preview_commands: list[NavigationCommand],
        preview_state: ExecutionState,
        choice: tuple[str, EdgeCandidate],
        preview_length: int,
    ) -> float:
        del preview_commands, preview_state, preview_length
        return 3.6 if choice[1] is baseline_edge else 3.2

    builder._preview_choice_cost = fake_preview_cost  # type: ignore[method-assign]
    choice = builder._choose_anonymous_chain_lookahead_edge(commands, 0, state, commands[0], ranked_candidates)

    assert choice == ("c", alternate_edge)


def test_long_anonymous_chain_lookahead_skips_long_turns():
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=0.0,
        names=(),
        name=None,
        length_m=111.0,
    )
    alternate_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, -0.001)]),
        bearing=315.0,
        names=(),
        name=None,
        length_m=157.0,
    )
    ranked_candidates = [
        (
            "b",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="b",
                street=None,
                bearing=0.0,
                street_penalty=0.0,
                turn_penalty=0.08,
                continuity_penalty=0.0,
                projection_distance_m=1.0,
                node_distance_m=12.0,
                preview_penalty=0.0,
                total_score=0.62,
            ),
        ),
        (
            "c",
            alternate_edge,
            ExecutionCandidateDiagnostic(
                node="c",
                street=None,
                bearing=315.0,
                street_penalty=0.0,
                turn_penalty=0.24,
                continuity_penalty=0.0,
                projection_distance_m=0.5,
                node_distance_m=2.0,
                preview_penalty=0.0,
                total_score=0.78,
            ),
        ),
    ]
    commands = [
        NavigationCommand(actions=["turn"], directions=["left"], distances=[180.0]),
        NavigationCommand(actions=["continue"], directions=["keep left"], distances=[35.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[50.0]),
        NavigationCommand(actions=["continue"], directions=["keep right"], distances=[45.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street=None)

    choice = builder._choose_anonymous_chain_lookahead_edge(commands, 0, state, commands[0], ranked_candidates)

    assert choice is None


def test_anonymous_chain_lookahead_records_diagnostic_note(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    chosen_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=90.0,
        names=("East Road",),
        name="East Road",
        length_m=111.0,
    )
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], distances=[40.0]),
        NavigationCommand(actions=["continue"], directions=["keep right"], distances=[35.0]),
        NavigationCommand(actions=["continue"], directions=["keep left"], distances=[45.0]),
        NavigationCommand(actions=["continue"], directions=["north"], distances=[30.0]),
        NavigationCommand(actions=["arrive"]),
    ]

    monkeypatch.setattr(builder, "_choose_anonymous_turn_rescue_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr(builder, "_choose_anonymous_chain_lookahead_edge", lambda *args, **kwargs: ("b", chosen_edge))
    monkeypatch.setattr(builder, "_choose_lookahead_edge", lambda *args, **kwargs: None)

    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street=None),
        align_start=False,
    )

    assert "anonymous-chain-lookahead" in trace.step_diagnostics[0].notes


def test_continue_lookahead_prefers_branch_that_reaches_future_named_street(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=0.0,
        names=("Main Road",),
        name="Main Road",
        length_m=111.0,
    )
    alternate_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, -0.001)]),
        bearing=45.0,
        names=("Branch Road",),
        name="Branch Road",
        length_m=157.0,
    )
    ranked_candidates = [
        (
            "b",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="b",
                street="Main Road",
                bearing=0.0,
                street_penalty=0.0,
                turn_penalty=0.10,
                continuity_penalty=0.0,
                projection_distance_m=1.0,
                node_distance_m=1.0,
                preview_penalty=0.0,
                total_score=0.40,
            ),
        ),
        (
            "c",
            alternate_edge,
            ExecutionCandidateDiagnostic(
                node="c",
                street="Branch Road",
                bearing=45.0,
                street_penalty=0.0,
                turn_penalty=0.18,
                continuity_penalty=0.0,
                projection_distance_m=2.0,
                node_distance_m=2.0,
                preview_penalty=0.0,
                total_score=0.58,
            ),
        ),
    ]
    commands = [
        NavigationCommand(actions=["continue"], directions=["keep right"], distances=[120.0]),
        NavigationCommand(actions=["turn"], directions=["left"], start_streets=["Target Road"], end_streets=["Target Road"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="Main Road")

    def fake_preview_metrics(
        preview_commands: list[NavigationCommand],
        preview_state: ExecutionState,
        choice: tuple[str, EdgeCandidate],
        preview_length: int,
        *,
        target_streets: list[str] | None = None,
    ) -> tuple[float, float]:
        del preview_commands, preview_state, preview_length, target_streets
        return (2.4, 120.0) if choice[1] is baseline_edge else (2.3, 70.0)

    monkeypatch.setattr(builder, "_preview_trace_metrics", fake_preview_metrics)
    choice = builder._choose_continue_lookahead_edge(commands, 0, state, commands[0], ranked_candidates)

    assert choice == ("c", alternate_edge)


def test_recommended_graph_dist_scales_with_route_length():
    commands = [NavigationCommand(actions=["continue"], distances=[1500.0])]
    assert recommended_graph_dist(commands) >= 2200


def test_named_street_recovery_limit_scales_with_command_distance():
    short = NavigationCommand(actions=["turn"], directions=["left"], end_streets=["Target Road"], distances=[5.0])
    medium = NavigationCommand(actions=["turn"], directions=["left"], end_streets=["Target Road"], distances=[64.8])
    long = NavigationCommand(actions=["turn"], directions=["left"], end_streets=["Target Road"], distances=[400.0])

    assert _named_street_recovery_limit(short) == 180.0
    assert round(_named_street_recovery_limit(medium), 1) == 226.8
    assert _named_street_recovery_limit(long) == 650.0


def test_short_anonymous_turn_carries_forward_previous_named_street():
    command = NavigationCommand(actions=["turn"], directions=["left"], distances=[15.0])

    assert _carry_forward_current_street("Fürstenrieder Straße", None, command, []) == "Fürstenrieder Straße"
    assert _carry_forward_current_street("Fürstenrieder Straße", "Connector Road", command, []) == "Connector Road"


def test_continue_across_short_unnamed_connector_keeps_previous_street():
    builder = PathBuilder(build_synthetic_graph())
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="Main Street")
    edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.00025, 0.0)]),
        bearing=0.0,
        names=(),
        name=None,
        length_m=27.5,
    )
    command = NavigationCommand(actions=["continue"], directions=["keep right"], distances=[300.0])

    builder._advance_along_edge(  # type: ignore[attr-defined]
        state,
        edge,
        remaining=27.5,
        command=command,
        desired_heading=0.0,
        preferred_streets=[],
        short_instruction_heading_threshold_m=15.0,
    )

    assert state.current_street == "Main Street"


def test_long_anonymous_turn_prefers_current_street_after_short_connector():
    commands = [
        NavigationCommand(actions=["turn"], directions=["left"], distances=[15.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[180.0]),
    ]

    assert _prefer_current_street_for_step(
        commands,
        1,
        commands[1],
        "anonymous_turn",
        "Fürstenrieder Straße",
    )


def test_long_anonymous_turn_without_short_connector_does_not_prefer_current_street():
    commands = [
        NavigationCommand(actions=["continue"], directions=["keep right"], distances=[30.0]),
        NavigationCommand(actions=["turn"], directions=["right"], distances=[180.0]),
    ]

    assert not _prefer_current_street_for_step(
        commands,
        1,
        commands[1],
        "anonymous_turn",
        "Fürstenrieder Straße",
    )


def test_named_turn_fallback_prefers_unnamed_branch_when_target_street_is_unknown(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=90.0,
        names=("Main Street",),
        name="Main Street",
        length_m=111.0,
    )
    unnamed_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.0007, -0.0007)]),
        bearing=135.0,
        names=(),
        name=None,
        length_m=111.0,
    )
    ranked_candidates = [
        (
            "a",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="Main Street",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.1,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.25,
            ),
        ),
        (
            "a",
            unnamed_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street=None,
                bearing=135.0,
                street_penalty=1.0,
                turn_penalty=0.2,
                continuity_penalty=0.0,
                projection_distance_m=4.0,
                node_distance_m=4.0,
                preview_penalty=0.0,
                total_score=0.9,
            ),
        ),
    ]
    command = NavigationCommand(
        actions=["turn"],
        directions=["right"],
        start_streets=["Target Road"],
        end_streets=["Target Road"],
        distances=[80.0],
    )
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=90.0, current_street="North Road")

    monkeypatch.setattr(execution_module, "distance_to_named_street", lambda graph, point, streets: float("inf"))
    choice = builder._choose_named_turn_fallback_edge([command], 0, state, command, ranked_candidates)

    assert choice == ("a", unnamed_edge)


def test_named_turn_fallback_skips_short_unreachable_turns(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=90.0,
        names=("Main Street",),
        name="Main Street",
        length_m=111.0,
    )
    unnamed_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.0007, -0.0007)]),
        bearing=135.0,
        names=(),
        name=None,
        length_m=111.0,
    )
    ranked_candidates = [
        (
            "a",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="Main Street",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.1,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.25,
            ),
        ),
        (
            "a",
            unnamed_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street=None,
                bearing=135.0,
                street_penalty=1.0,
                turn_penalty=0.2,
                continuity_penalty=0.0,
                projection_distance_m=4.0,
                node_distance_m=4.0,
                preview_penalty=0.0,
                total_score=0.9,
            ),
        ),
    ]
    command = NavigationCommand(
        actions=["turn"],
        directions=["right"],
        start_streets=["Target Road"],
        end_streets=["Target Road"],
        distances=[30.0],
    )
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=90.0, current_street="North Road")

    monkeypatch.setattr(execution_module, "distance_to_named_street", lambda graph, point, streets: float("inf"))
    choice = builder._choose_named_turn_fallback_edge([command], 0, state, command, ranked_candidates)

    assert choice is None


def test_named_turn_fallback_prefers_branch_that_makes_large_target_progress(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=90.0,
        names=("Main Street",),
        name="Main Street",
        length_m=111.0,
    )
    better_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.0007, -0.0007)]),
        bearing=135.0,
        names=("Connector",),
        name="Connector",
        length_m=111.0,
    )
    ranked_candidates = [
        (
            "a",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="Main Street",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.1,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.2,
            ),
        ),
        (
            "a",
            better_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="Connector",
                bearing=135.0,
                street_penalty=0.4,
                turn_penalty=0.15,
                continuity_penalty=0.0,
                projection_distance_m=6.0,
                node_distance_m=6.0,
                preview_penalty=0.0,
                total_score=0.5,
            ),
        ),
    ]
    commands = [
        NavigationCommand(
            actions=["turn"],
            directions=["right"],
            start_streets=["Target Road"],
            end_streets=["Target Road"],
            distances=[20.0],
        ),
        NavigationCommand(actions=["continue"], directions=["keep right"], distances=[25.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=90.0, current_street="North Road")

    monkeypatch.setattr(
        execution_module,
        "distance_to_named_street",
        lambda graph, point, streets: 600.0 if point == state.current_coordinates else 0.0,
    )

    def fake_preview_trace_metrics(
        preview_commands: list[NavigationCommand],
        preview_state: ExecutionState,
        choice: tuple[str, EdgeCandidate],
        preview_length: int,
        *,
        target_streets: list[str] | None = None,
    ) -> tuple[float, float]:
        del preview_commands, preview_state, preview_length, target_streets
        if choice[1].name == "Main Street":
            return 4.5, 520.0
        return 4.8, 430.0

    monkeypatch.setattr(builder, "_preview_trace_metrics", fake_preview_trace_metrics)
    choice = builder._choose_named_turn_fallback_edge(commands, 0, state, commands[0], ranked_candidates)

    assert choice == ("a", better_edge)


def test_named_turn_fallback_keeps_baseline_when_preview_target_is_already_equivalent(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_synthetic_graph())
    baseline_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=90.0,
        names=("Main Street",),
        name="Main Street",
        length_m=111.0,
    )
    alternate_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.0007, -0.0007)]),
        bearing=135.0,
        names=("Connector",),
        name="Connector",
        length_m=111.0,
    )
    ranked_candidates = [
        (
            "a",
            baseline_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="Main Street",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.1,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.2,
            ),
        ),
        (
            "a",
            alternate_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="Connector",
                bearing=135.0,
                street_penalty=0.4,
                turn_penalty=0.15,
                continuity_penalty=0.0,
                projection_distance_m=6.0,
                node_distance_m=6.0,
                preview_penalty=0.0,
                total_score=0.5,
            ),
        ),
    ]
    commands = [
        NavigationCommand(
            actions=["turn"],
            directions=["right"],
            start_streets=["Target Road"],
            end_streets=["Target Road"],
            distances=[20.0],
        ),
        NavigationCommand(actions=["arrive"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=90.0, current_street="North Road")

    monkeypatch.setattr(
        execution_module,
        "distance_to_named_street",
        lambda graph, point, streets: 400.0 if point == state.current_coordinates else 0.0,
    )

    def fake_preview_trace_metrics(
        preview_commands: list[NavigationCommand],
        preview_state: ExecutionState,
        choice: tuple[str, EdgeCandidate],
        preview_length: int,
        *,
        target_streets: list[str] | None = None,
    ) -> tuple[float, float]:
        del preview_commands, preview_state, preview_length, target_streets
        if choice[1].name == "Main Street":
            return 4.5, 50.0
        return 4.8, 50.0

    monkeypatch.setattr(builder, "_preview_trace_metrics", fake_preview_trace_metrics)
    choice = builder._choose_named_turn_fallback_edge(commands, 0, state, commands[0], ranked_candidates)

    assert choice is None


def test_named_turn_fallback_records_diagnostic_note(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_named_list_graph())
    chosen_edge = EdgeCandidate(
        source="b",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.001), (0.001, 0.001)]),
        bearing=90.0,
        names=("Target Road",),
        name="Target Road",
        length_m=111.0,
    )
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Target Road"], end_streets=["Target Road"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]

    monkeypatch.setattr(builder, "_choose_named_turn_lookahead_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr(builder, "_choose_named_turn_fallback_edge", lambda *args, **kwargs: ("b", chosen_edge))

    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.00095, 0.00001), current_heading=0.0, current_street="North Road"),
        align_start=False,
    )

    assert "named-turn-fallback" in trace.step_diagnostics[0].notes


def test_named_street_continuation_prefers_longer_same_name_edge():
    builder = PathBuilder(build_synthetic_graph())
    short_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.00005, 0.0)]),
        bearing=90.0,
        names=("Birkenhofstraße",),
        name="Birkenhofstraße",
        length_m=5.9,
    )
    long_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.0041, 0.0)]),
        bearing=90.0,
        names=("Birkenhofstraße",),
        name="Birkenhofstraße",
        length_m=457.1,
    )
    ranked_candidates = [
        (
            "b",
            short_edge,
            ExecutionCandidateDiagnostic(
                node="b",
                street="Birkenhofstraße",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.02,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.0785,
            ),
        ),
        (
            "c",
            long_edge,
            ExecutionCandidateDiagnostic(
                node="c",
                street="Birkenhofstraße",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.02,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.0868,
            ),
        ),
    ]

    choice = builder._choose_named_street_continuation_edge(
        ranked_candidates,
        preferred_streets=["Birkenhofstraße"],
        step_kind="named_turn",
        remaining_distance=1078.0,
    )

    assert choice == ranked_candidates[1]


def test_named_street_continuation_skips_short_remaining_distance():
    builder = PathBuilder(build_synthetic_graph())
    short_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.00005, 0.0)]),
        bearing=90.0,
        names=("Birkenhofstraße",),
        name="Birkenhofstraße",
        length_m=5.9,
    )
    long_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.0041, 0.0)]),
        bearing=90.0,
        names=("Birkenhofstraße",),
        name="Birkenhofstraße",
        length_m=457.1,
    )
    ranked_candidates = [
        (
            "b",
            short_edge,
            ExecutionCandidateDiagnostic(
                node="b",
                street="Birkenhofstraße",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.02,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.0785,
            ),
        ),
        (
            "c",
            long_edge,
            ExecutionCandidateDiagnostic(
                node="c",
                street="Birkenhofstraße",
                bearing=90.0,
                street_penalty=0.0,
                turn_penalty=0.02,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.0868,
            ),
        ),
    ]

    choice = builder._choose_named_street_continuation_edge(
        ranked_candidates,
        preferred_streets=["Birkenhofstraße"],
        step_kind="named_turn",
        remaining_distance=40.0,
    )

    assert choice is None


def test_named_street_continuation_records_diagnostic_note(monkeypatch: pytest.MonkeyPatch):
    builder = PathBuilder(build_named_list_graph())
    chosen_edge = EdgeCandidate(
        source="b",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.001), (0.001, 0.001)]),
        bearing=90.0,
        names=("Target Road",),
        name="Target Road",
        length_m=111.0,
    )
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Target Road"], end_streets=["Target Road"], distances=[120.0]),
        NavigationCommand(actions=["arrive"]),
    ]

    monkeypatch.setattr(builder, "_choose_named_turn_lookahead_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr(builder, "_choose_named_turn_fallback_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        builder,
        "_choose_named_street_continuation_edge",
        lambda *args, **kwargs: ("b", chosen_edge, args[0][0][2]),
    )

    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.00095, 0.00001), current_heading=0.0, current_street="North Road"),
        align_start=False,
    )

    assert "named-street-continuation" in trace.step_diagnostics[0].notes


def test_medium_anonymous_turn_can_defer_named_corridor_to_unnamed_connector():
    builder = PathBuilder(build_synthetic_graph())
    named_edge = EdgeCandidate(
        source="a",
        target="b",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.001, 0.0)]),
        bearing=0.0,
        names=("Main Street",),
        name="Main Street",
        length_m=111.0,
    )
    unnamed_edge = EdgeCandidate(
        source="a",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.0), (0.0007, -0.0007)]),
        bearing=315.0,
        names=(),
        name=None,
        length_m=111.0,
    )
    ranked_candidates = [
        (
            "a",
            named_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street="Main Street",
                bearing=0.0,
                street_penalty=0.0,
                turn_penalty=0.1,
                continuity_penalty=0.0,
                projection_distance_m=0.0,
                node_distance_m=0.0,
                preview_penalty=0.0,
                total_score=0.1,
            ),
        ),
        (
            "a",
            unnamed_edge,
            ExecutionCandidateDiagnostic(
                node="a",
                street=None,
                bearing=315.0,
                street_penalty=0.0,
                turn_penalty=0.2,
                continuity_penalty=0.0,
                projection_distance_m=6.0,
                node_distance_m=6.0,
                preview_penalty=0.0,
                total_score=0.4,
            ),
        ),
    ]
    commands = [
        NavigationCommand(actions=["turn"], directions=["left"], distances=[70.0]),
        NavigationCommand(actions=["continue"], directions=["keep left"], distances=[26.0]),
        NavigationCommand(actions=["arrive"], end_streets=["your destination"]),
    ]
    state = ExecutionState(current_coordinates=(0.0, 0.0), current_heading=0.0, current_street="Main Street")

    def fake_preview_cost(
        preview_commands: list[NavigationCommand],
        preview_state: ExecutionState,
        choice: tuple[str, EdgeCandidate],
        preview_length: int,
    ) -> float:
        del preview_commands, preview_state, preview_length
        return 1.5 if choice[1].name == "Main Street" else 0.8

    builder._preview_choice_cost = fake_preview_cost  # type: ignore[method-assign]
    choice = builder._choose_anonymous_turn_rescue_edge(commands, 0, state, commands[0], ranked_candidates)

    assert choice == ("a", unnamed_edge)


def test_trace_cost_uses_selected_override_score_instead_of_top_ranked_candidate():
    builder = PathBuilder(build_maneuver_penalty_graph())
    primary_edge = EdgeCandidate(
        source="b",
        target="c",
        key=0,
        geometry=LineString([(0.0, 0.001), (0.0, 0.002)]),
        bearing=0.0,
        names=("Main Street",),
        name="Main Street",
        length_m=111.0,
    )
    override_edge = EdgeCandidate(
        source="b",
        target="d",
        key=0,
        geometry=LineString([(0.0, 0.001), (0.001, 0.001)]),
        bearing=90.0,
        names=("Side Road",),
        name="Side Road",
        length_m=111.0,
    )
    primary_diagnostic = ExecutionCandidateDiagnostic(
        node="b",
        street="Main Street",
        bearing=0.0,
        street_penalty=0.0,
        turn_penalty=0.1,
        continuity_penalty=0.0,
        projection_distance_m=0.0,
        node_distance_m=0.0,
        preview_penalty=0.0,
        total_score=0.1,
    )
    override_diagnostic = ExecutionCandidateDiagnostic(
        node="b",
        street="Side Road",
        bearing=90.0,
        street_penalty=0.0,
        turn_penalty=0.3,
        continuity_penalty=0.0,
        projection_distance_m=0.0,
        node_distance_m=0.0,
        preview_penalty=0.0,
        total_score=0.4,
    )
    builder._score_candidates = lambda *args, **kwargs: [  # type: ignore[method-assign]
        ("b", primary_edge, primary_diagnostic),
        ("b", override_edge, override_diagnostic),
    ]
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]

    trace = builder._execute_sequence(
        commands,
        ExecutionState(current_coordinates=(0.001, 0.0), current_heading=0.0, current_street="Main Street"),
        align_start=False,
        allow_lookahead=False,
        override_choices={0: ("b", override_edge)},
    )

    assert trace.step_diagnostics[0].candidate_diagnostics[0].total_score == pytest.approx(0.1)
    assert trace.step_diagnostics[0].selected_score == pytest.approx(0.4)
    assert builder._trace_cost(trace) == pytest.approx(0.4)

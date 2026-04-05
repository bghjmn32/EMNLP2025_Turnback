from pathlib import Path

from path_builder.ceiling import summarize_execution_ceiling
from path_builder.models import DatasetExample, ExecutionState, NavigationCommand
from path_builder.execution import PathBuilder

from test_execution import build_named_corridor_graph, build_named_turn_lookahead_graph


def _synthetic_example() -> DatasetExample:
    return DatasetExample(
        corpus="data_set",
        example_id="synthetic",
        root=Path("."),
        route_geojson_path=Path("route.geojson"),
        instructions_path=None,
        natural_instructions_path=None,
        parsed_instructions_path=None,
        reverse_route_path=None,
        start=(0.0, 0.0),
        end=(0.0, 0.0),
    )


def test_ceiling_report_flags_oov_named_street():
    builder = PathBuilder(build_named_corridor_graph())
    commands = [
        NavigationCommand(actions=["continue"], start_streets=["Missing Street"], end_streets=["Missing Street"], distances=[120.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, 0.0), current_heading=180.0, current_street="Main Street"),
        align_start=False,
    )

    report = summarize_execution_ceiling(
        _synthetic_example(),
        builder=builder,
        commands=commands,
        trace=trace,
        similarity=0.0,
        graph_source="synthetic",
    )

    assert "named-street-oov" in report["summary"]["hard_constraints"]
    assert "named-street-oov" in report["step_reports"][0]["flags"]


def test_ceiling_report_flags_named_street_beyond_recovery():
    builder = PathBuilder(build_named_turn_lookahead_graph())
    commands = [
        NavigationCommand(actions=["turn"], directions=["right"], start_streets=["Final Road"], end_streets=["Final Road"], distances=[40.0]),
        NavigationCommand(actions=["arrive"]),
    ]
    trace = builder.execute(
        commands,
        ExecutionState(current_coordinates=(0.0, -0.001), current_heading=0.0, current_street="North Road"),
        align_start=False,
    )

    report = summarize_execution_ceiling(
        _synthetic_example(),
        builder=builder,
        commands=commands,
        trace=trace,
        similarity=0.0,
        graph_source="synthetic",
    )

    assert "named-street-beyond-recovery" in report["summary"]["hard_constraints"]
    assert "named-street-beyond-recovery" in report["step_reports"][0]["flags"]

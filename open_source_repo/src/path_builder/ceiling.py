from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .datasets import load_reference_route
from .execution import (
    PathBuilder,
    _command_step_kind,
    _is_placeholder_street_name,
    _named_street_recovery_limit,
    distance_to_named_street,
    graph_contains_named_street,
    recommended_graph_dist,
)
from .graphs import GraphSnapshotStore
from .models import DatasetExample, ExecutionState, ExecutionTrace, NavigationCommand, SimilarityThresholds, SimilarityWeights
from .similarity import score_geojson_routes


def _step_preferred_streets(command: NavigationCommand) -> list[str]:
    return [
        street
        for street in command.end_streets + command.start_streets
        if street and not _is_placeholder_street_name(street)
    ]


def _graph_contains_street(builder: PathBuilder, preferred_streets: list[str]) -> bool:
    return graph_contains_named_street(builder.graph, preferred_streets)


def _step_repeat_count(segments: list[list[tuple[float, float]]]) -> int:
    if not segments:
        return 0
    keys = [tuple(segment) for segment in segments]
    counts = Counter(keys)
    return sum(count - 1 for count in counts.values() if count > 1)


def summarize_execution_ceiling(
    example: DatasetExample,
    *,
    builder: PathBuilder,
    commands: list[NavigationCommand],
    trace: ExecutionTrace,
    similarity: float,
    graph_source: str,
) -> dict[str, Any]:
    step_reports: list[dict[str, Any]] = []
    anonymous_chain = 0
    longest_anonymous_chain = 0
    missing_named_steps = 0
    far_named_steps = 0
    unresolved_named_steps = 0
    ambiguous_steps = 0
    loop_steps = 0
    street_shift_count = 0

    for command, step in zip(commands, trace.step_diagnostics):
        preferred_streets = _step_preferred_streets(command)
        step_kind = _command_step_kind(command)
        if step_kind == "anonymous_turn":
            anonymous_chain += 1
            longest_anonymous_chain = max(longest_anonymous_chain, anonymous_chain)
        elif preferred_streets:
            anonymous_chain = 0
        else:
            anonymous_chain = 0

        street_present = _graph_contains_street(builder, preferred_streets) if preferred_streets else None
        street_distance = distance_to_named_street(builder.graph, step.start_coordinates, preferred_streets) if preferred_streets else None
        recovery_limit = _named_street_recovery_limit(command) if preferred_streets else None
        selected_matches = step.selected_street in preferred_streets if preferred_streets else None
        candidate_gap = None
        if len(step.candidate_diagnostics) >= 2:
            candidate_gap = step.candidate_diagnostics[1].total_score - step.candidate_diagnostics[0].total_score
            if candidate_gap <= 0.15:
                ambiguous_steps += 1
        step_segments = [trace.segment_coordinates[index] for index in step.segment_indexes if index < len(trace.segment_coordinates)]
        repeated_edges = _step_repeat_count(step_segments)
        if repeated_edges > 0:
            loop_steps += 1
        street_shifts = sum(1 for note in step.notes if note.startswith("street-shift:"))
        street_shift_count += street_shifts

        flags: list[str] = []
        if preferred_streets and street_present is False:
            missing_named_steps += 1
            flags.append("named-street-oov")
        if (
            preferred_streets
            and street_present
            and street_distance is not None
            and recovery_limit is not None
            and street_distance > recovery_limit
        ):
            far_named_steps += 1
            flags.append("named-street-beyond-recovery")
        if preferred_streets and selected_matches is False:
            unresolved_named_steps += 1
            flags.append("named-street-unresolved")
        if repeated_edges > 0:
            flags.append("local-looping")
        if street_shifts >= 3:
            flags.append("corridor-drift")
        if candidate_gap is not None and candidate_gap <= 0.15:
            flags.append("high-local-ambiguity")

        step_reports.append(
            {
                "index": step.index,
                "step_kind": step.step_kind,
                "action": step.action,
                "direction": step.direction,
                "preferred_streets": preferred_streets,
                "selected_street": step.selected_street,
                "street_present": street_present,
                "street_distance_m": street_distance,
                "recovery_limit_m": recovery_limit,
                "selected_matches_preferred": selected_matches,
                "candidate_gap": candidate_gap,
                "repeated_edges": repeated_edges,
                "street_shifts": street_shifts,
                "notes": step.notes,
                "flags": flags,
            }
        )

    total_segments = len(trace.segment_coordinates)
    repeated_edge_ratio = _step_repeat_count(trace.segment_coordinates) / total_segments if total_segments else 0.0

    hard_constraints: list[str] = []
    if missing_named_steps:
        hard_constraints.append("named-street-oov")
    if far_named_steps:
        hard_constraints.append("named-street-beyond-recovery")

    soft_constraints: list[str] = []
    if longest_anonymous_chain >= 3:
        soft_constraints.append("long-anonymous-chain")
    if repeated_edge_ratio >= 0.2 or loop_steps:
        soft_constraints.append("local-looping")
    if street_shift_count >= 4:
        soft_constraints.append("corridor-drift")
    if ambiguous_steps >= 2:
        soft_constraints.append("high-local-ambiguity")

    return {
        "example": {
            "label": example.label,
            "corpus": example.corpus,
            "example_id": example.example_id,
            "graph_source": graph_source,
        },
        "similarity": similarity,
        "summary": {
            "named_step_count": sum(1 for command in commands if _step_preferred_streets(command)),
            "missing_named_steps": missing_named_steps,
            "far_named_steps": far_named_steps,
            "unresolved_named_steps": unresolved_named_steps,
            "ambiguous_steps": ambiguous_steps,
            "loop_steps": loop_steps,
            "street_shift_count": street_shift_count,
            "longest_anonymous_chain": longest_anonymous_chain,
            "repeated_edge_ratio": repeated_edge_ratio,
            "hard_constraints": hard_constraints,
            "soft_constraints": soft_constraints,
        },
        "step_reports": step_reports,
    }


def analyze_execution_ceiling(
    example: DatasetExample,
    *,
    builder: PathBuilder | None = None,
    snapshot_dir: str | Path | None = None,
    dist: int = 1200,
    weights: SimilarityWeights | None = None,
    thresholds: SimilarityThresholds | None = None,
    network_type: str = "walk",
) -> dict[str, Any]:
    from .datasets import load_parsed_instructions

    if example.start is None:
        raise ValueError("Example does not contain route start metadata.")

    commands = load_parsed_instructions(example)
    start = (example.start[1], example.start[0])
    target_dist = max(dist, recommended_graph_dist(commands))
    graph_source = "live"
    active_builder = builder
    if active_builder is None and snapshot_dir is not None:
        active_builder, graph_source = GraphSnapshotStore(snapshot_dir).load_or_create_builder(
            example,
            center=start,
            dist=target_dist,
            network_type=network_type,
            refresh=False,
        )
    if active_builder is None:
        active_builder = PathBuilder.from_osm(start, dist=target_dist, network_type=network_type)
    else:
        active_builder = active_builder.local_view(start, target_dist)
    trace = active_builder.execute(commands, ExecutionState(current_coordinates=start, current_heading=0.0))
    similarity = score_geojson_routes(
        active_builder.trace_to_geojson(trace),
        load_reference_route(example),
        weights=weights or SimilarityWeights(),
        thresholds=thresholds or SimilarityThresholds(),
    ).similarity
    return summarize_execution_ceiling(
        example,
        builder=active_builder,
        commands=commands,
        trace=trace,
        similarity=similarity,
        graph_source=graph_source,
    )

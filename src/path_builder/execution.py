from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any

import networkx as nx
from shapely.geometry import LineString

from .geo import ABSOLUTE_DIRECTIONS, angular_difference, bearing_between_points, extract_line_segment, heading_for_instruction, path_length_meters, point_distance_meters, project_point_onto_line, signed_heading_delta
from .io import feature_collection_from_linestring, save_geojson
from .models import (
    ExecutionCandidateDiagnostic,
    ExecutionState,
    ExecutionStepDiagnostic,
    ExecutionTrace,
    LatLon,
    NavigationCommand,
)


@dataclass(slots=True)
class EdgeCandidate:
    source: Any
    target: Any
    key: Any | None
    geometry: LineString
    bearing: float
    names: tuple[str, ...]
    name: str | None
    length_m: float


@dataclass(slots=True)
class RankedEdgeInput:
    node: Any
    node_distance_m: float
    candidate: EdgeCandidate
    projection_distance_m: float


@dataclass(slots=True)
class SearchHypothesis:
    overrides: dict[int, tuple[Any, EdgeCandidate]] = field(default_factory=dict)
    score: float = 0.0
    trace: ExecutionTrace | None = None


def _diagnostic_for_choice(
    ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
    choice: tuple[Any, EdgeCandidate],
) -> ExecutionCandidateDiagnostic | None:
    node, edge = choice
    for candidate_node, candidate_edge, diagnostic in ranked_candidates:
        if (
            candidate_node == node
            and candidate_edge.source == edge.source
            and candidate_edge.target == edge.target
            and candidate_edge.key == edge.key
        ):
            return diagnostic
    return None


def _node_coordinate(graph: nx.Graph, node: Any) -> LatLon:
    return graph.nodes[node]["y"], graph.nodes[node]["x"]


def _node_label(node: Any) -> str:
    return str(node)


def _command_step_kind(command: NavigationCommand) -> str:
    action = command.primary_action
    if action == "arrive":
        return "arrive"
    if action == "head" and command.primary_direction in ABSOLUTE_DIRECTIONS:
        return "absolute_head"
    if action == "turn" and command.end_streets:
        return "named_turn"
    if command.primary_distance <= 15.0 and not command.end_streets:
        return "short_connector"
    if action == "turn":
        return "anonymous_turn"
    if action == "continue":
        return "continue"
    return action or "unknown"


def _command_street_targets(command: NavigationCommand) -> list[str]:
    return [street for street in command.all_street_targets if street]


def recommended_graph_dist(
    commands: list[NavigationCommand],
    minimum: int = 1200,
    scale: float = 1.2,
    buffer_m: int = 400,
    maximum: int = 3500,
) -> int:
    total_distance = sum(command.primary_distance for command in commands)
    estimate = int(total_distance * scale + buffer_m)
    return max(minimum, min(maximum, estimate))


def _named_street_recovery_limit(command: NavigationCommand) -> float:
    if command.primary_distance <= 0.0:
        return 180.0
    return min(650.0, max(180.0, command.primary_distance * 3.5))


def _carry_forward_current_street(
    previous_street: str | None,
    edge_name: str | None,
    command: NavigationCommand,
    preferred_streets: list[str],
) -> str | None:
    if edge_name is not None:
        return edge_name
    if (
        previous_street
        and command.primary_action == "turn"
        and not preferred_streets
        and 0.0 < command.primary_distance <= 20.0
    ):
        return previous_street
    return None


def _prefer_current_street_for_step(
    commands: list[NavigationCommand],
    index: int,
    command: NavigationCommand,
    step_kind: str,
    current_street: str | None,
) -> bool:
    if step_kind == "short_connector":
        return True
    if step_kind != "anonymous_turn" or not current_street or command.primary_distance < 120.0 or index <= 0:
        return False
    previous = commands[index - 1]
    return (
        previous.primary_action == "turn"
        and not previous.start_streets
        and not previous.end_streets
        and 0.0 < previous.primary_distance <= 20.0
    )

def _edge_geometry(graph: nx.Graph, source: Any, target: Any, data: dict[str, Any]) -> LineString:
    geometry = data.get("geometry")
    if geometry is None:
        return LineString([(graph.nodes[source]["x"], graph.nodes[source]["y"]), (graph.nodes[target]["x"], graph.nodes[target]["y"])])
    return geometry


def _oriented_line(graph: nx.Graph, source: Any, target: Any, data: dict[str, Any]) -> LineString:
    geometry = _edge_geometry(graph, source, target, data)
    coords = list(geometry.coords)
    source_lonlat = (graph.nodes[source]["x"], graph.nodes[source]["y"])
    if coords[0] != source_lonlat:
        coords.reverse()
    return LineString(coords)


def _edge_candidate_from_line(
    source: Any,
    target: Any,
    key: Any | None,
    line: LineString,
    raw_name: Any,
) -> EdgeCandidate:
    start = (line.coords[0][1], line.coords[0][0])
    next_point = (line.coords[1][1], line.coords[1][0]) if len(line.coords) > 1 else start
    names = _extract_edge_name_variants(raw_name)
    return EdgeCandidate(
        source=source,
        target=target,
        key=key,
        geometry=line,
        bearing=bearing_between_points(start, next_point),
        names=names,
        name=names[0] if names else None,
        length_m=path_length_meters([(lat, lon) for lon, lat in line.coords]),
    )


def _edge_candidate_from_data(
    graph: nx.Graph,
    source: Any,
    target: Any,
    key: Any | None,
    data: dict[str, Any],
) -> EdgeCandidate:
    return _edge_candidate_from_line(source, target, key, _oriented_line(graph, source, target, data), data.get("name"))


def _extract_edge_name_variants(raw_name: Any) -> tuple[str, ...]:
    if isinstance(raw_name, str):
        cleaned = raw_name.strip()
        return (cleaned,) if cleaned else ()
    if isinstance(raw_name, (list, tuple, set)):
        values: list[str] = []
        for item in raw_name:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned and cleaned not in values:
                    values.append(cleaned)
        return tuple(values)
    return ()


def _is_placeholder_street_name(name: str) -> bool:
    return name.strip().lower() in {"destination", "your destination"}


def _best_edge_data(edge_map: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(edge_map, dict) and "length" in edge_map:
        return None, edge_map
    items = edge_map.items()
    best_key, best_data = min(items, key=lambda item: float(item[1].get("length", 0.0)))
    return best_key, best_data


def nearest_node(graph: nx.Graph, point: LatLon) -> Any:
    return min(graph.nodes, key=lambda node: point_distance_meters(point, _node_coordinate(graph, node)))


def nearest_nodes(
    graph: nx.Graph,
    point: LatLon,
    limit: int = 6,
    max_distance_m: float = 120.0,
) -> list[tuple[Any, float]]:
    ranked = sorted(
        ((node, point_distance_meters(point, _node_coordinate(graph, node))) for node in graph.nodes),
        key=lambda item: item[1],
    )
    return [(node, distance) for node, distance in ranked[:limit] if distance <= max_distance_m] or ranked[:1]


def _local_bbox_deltas(center: LatLon, dist_m: float) -> tuple[float, float]:
    lat, _ = center
    lat_delta = dist_m / 111_320.0
    cos_lat = max(abs(math.cos(math.radians(lat))), 0.2)
    lon_delta = dist_m / (111_320.0 * cos_lat)
    return lat_delta, lon_delta


def _anchor_neighborhood_nodes(graph: nx.Graph, anchor: Any) -> set[Any]:
    nodes = {anchor}
    if hasattr(graph, "successors"):
        nodes.update(graph.successors(anchor))
    if hasattr(graph, "predecessors"):
        nodes.update(graph.predecessors(anchor))
    if hasattr(graph, "neighbors"):
        nodes.update(graph.neighbors(anchor))
    return nodes


def _connected_component_nodes(graph: nx.Graph, anchor: Any) -> set[Any]:
    if anchor not in graph:
        return set(graph.nodes)
    if graph.is_directed():
        for component in nx.weakly_connected_components(graph):  # type: ignore[arg-type]
            if anchor in component:
                return set(component)
    else:
        for component in nx.connected_components(graph):  # type: ignore[arg-type]
            if anchor in component:
                return set(component)
    return {anchor}


def _local_subgraph(graph: nx.Graph, center: LatLon, dist_m: float) -> nx.Graph:
    if graph.number_of_nodes() == 0:
        return graph.copy()

    anchor = nearest_node(graph, center)
    lat, lon = center
    lat_delta, lon_delta = _local_bbox_deltas(center, dist_m * 1.05)
    node_ids = {
        node
        for node, data in graph.nodes(data=True)
        if abs(float(data.get("y", 0.0)) - lat) <= lat_delta and abs(float(data.get("x", 0.0)) - lon) <= lon_delta
    }
    if not node_ids:
        node_ids = _anchor_neighborhood_nodes(graph, anchor)

    local_graph = graph.subgraph(node_ids).copy()
    if local_graph.number_of_edges() == 0:
        local_graph = graph.subgraph(_anchor_neighborhood_nodes(graph, anchor)).copy()
    if local_graph.number_of_nodes() == 0:
        return graph.subgraph([anchor]).copy()

    if anchor not in local_graph:
        anchor = nearest_node(local_graph, center)
    component_nodes = _connected_component_nodes(local_graph, anchor)
    return local_graph.subgraph(component_nodes).copy()


def _candidate_search_nodes(
    graph: nx.Graph,
    point: LatLon,
    *,
    include_nearby: bool,
    nearby_limit: int = 8,
    nearby_distance_m: float = 50.0,
) -> list[tuple[Any, float]]:
    if include_nearby:
        return nearest_nodes(graph, point, limit=nearby_limit, max_distance_m=nearby_distance_m)
    node = nearest_node(graph, point)
    return [(node, point_distance_meters(point, _node_coordinate(graph, node)))]


def iter_edge_candidates(graph: nx.Graph, node: Any) -> list[EdgeCandidate]:
    candidates: list[EdgeCandidate] = []
    if hasattr(graph, "out_edges"):
        for _, target, key, data in graph.out_edges(node, keys=True, data=True):
            candidates.append(_edge_candidate_from_data(graph, node, target, key, data))
        for source, _, key, data in graph.in_edges(node, keys=True, data=True):
            candidates.append(_edge_candidate_from_data(graph, node, source, key, data))
    else:
        for source, target, data in graph.edges(node, data=True):
            other = target if source == node else source
            candidates.append(_edge_candidate_from_data(graph, node, other, None, data))
    return candidates


def _ranked_edge_inputs(
    graph: nx.Graph,
    point: LatLon,
    *,
    include_nearby: bool = False,
    nearby_limit: int = 8,
    nearby_distance_m: float = 50.0,
) -> list[RankedEdgeInput]:
    ranked_inputs: list[RankedEdgeInput] = []
    seen: set[tuple[Any, Any, Any | None]] = set()
    for node, node_distance in _candidate_search_nodes(
        graph,
        point,
        include_nearby=include_nearby,
        nearby_limit=nearby_limit,
        nearby_distance_m=nearby_distance_m,
    ):
        for candidate in iter_edge_candidates(graph, node):
            key = (candidate.source, candidate.target, candidate.key)
            if key in seen:
                continue
            seen.add(key)
            snapped, _ = project_point_onto_line(candidate.geometry, point)
            ranked_inputs.append(
                RankedEdgeInput(
                    node=node,
                    node_distance_m=node_distance,
                    candidate=candidate,
                    projection_distance_m=point_distance_meters(point, snapped),
                )
            )
    return ranked_inputs


def _street_match_score(candidate_name: str | list[str] | tuple[str, ...] | None, preferred_streets: list[str] | None) -> float:
    if not preferred_streets:
        return 0.0
    candidate_values = _extract_edge_name_variants(candidate_name)
    if not candidate_values:
        return 1.0
    scores = []
    for street in preferred_streets:
        target = _normalize_street_name(street)
        if not target:
            continue
        best = 1.0
        for candidate_name in candidate_values:
            candidate = _normalize_street_name(candidate_name)
            if candidate == target:
                best = 0.0
                break
            prefix = max(3, min(8, len(target), len(candidate)))
            if prefix > 0 and (
                candidate.startswith(target[:prefix]) or target.startswith(candidate[:prefix])
            ):
                best = min(best, 0.2)
        scores.append(best)
    return min(scores) if scores else 1.0


def pick_edge(
    graph: nx.Graph,
    point: LatLon,
    heading: float,
    preferred_streets: list[str] | None = None,
) -> tuple[Any, EdgeCandidate]:
    node = nearest_node(graph, point)
    candidates = iter_edge_candidates(graph, node)
    if not candidates:
        raise ValueError(f"No traversable edges found around node {node!r}")
    best = min(
        candidates,
        key=lambda candidate: (
            _street_match_score(candidate.name, preferred_streets),
            angular_difference(candidate.bearing, heading),
        ),
    )
    return node, best


def pick_edge_from_nearby_geometry(
    graph: nx.Graph,
    point: LatLon,
    heading: float,
    preferred_streets: list[str] | None = None,
) -> tuple[Any, EdgeCandidate]:
    candidates = _ranked_edge_inputs(graph, point, include_nearby=True)
    if not candidates:
        node = nearest_node(graph, point)
        raise ValueError(f"No traversable edges found around node {node!r}")
    best = min(
        candidates,
        key=lambda item: (
            _street_match_score(item.candidate.name, preferred_streets),
            0 if item.projection_distance_m <= 12.0 else 1,
            angular_difference(item.candidate.bearing, heading),
            item.projection_distance_m,
            item.node_distance_m,
        ),
    )
    return best.node, best.candidate


def pick_turn_edge(
    graph: nx.Graph,
    point: LatLon,
    heading: float,
    current_street: str | None = None,
    preferred_streets: list[str] | None = None,
) -> tuple[Any, EdgeCandidate]:
    current_street_key = _normalize_street_name(current_street) if current_street else ""
    candidates = _ranked_edge_inputs(graph, point, include_nearby=True, nearby_limit=8, nearby_distance_m=50.0)
    if not candidates:
        node = nearest_node(graph, point)
        raise ValueError(f"No turn candidates found around node {node!r}")
    best = min(
        candidates,
        key=lambda item: (
            _street_match_score(item.candidate.name, preferred_streets),
            1 if _same_street(item.candidate.names, current_street_key) else 0,
            angular_difference(item.candidate.bearing, heading),
            item.node_distance_m,
        ),
    )
    return best.node, best.candidate


def rank_edge_candidates(
    graph: nx.Graph,
    point: LatLon,
    heading: float,
    preferred_streets: list[str] | None = None,
    current_street: str | None = None,
    include_nearby: bool = False,
    nearby_limit: int = 8,
    nearby_distance_m: float = 50.0,
) -> list[tuple[Any, EdgeCandidate]]:
    current_street_key = _normalize_street_name(current_street) if current_street else ""
    ranked: list[tuple[tuple[float, int, float, float, float], Any, EdgeCandidate]] = []
    for ranked_input in _ranked_edge_inputs(
        graph,
        point,
        include_nearby=include_nearby,
        nearby_limit=nearby_limit,
        nearby_distance_m=nearby_distance_m,
    ):
        candidate = ranked_input.candidate
        ranked.append(
            (
                (
                    _street_match_score(candidate.names, preferred_streets),
                    1 if _same_street(candidate.names, current_street_key) else 0,
                    angular_difference(candidate.bearing, heading),
                    ranked_input.projection_distance_m,
                    ranked_input.node_distance_m,
                    round(candidate.bearing, 6),
                    _node_label(ranked_input.node),
                    _node_label(candidate.target),
                    str(candidate.key),
                ),
                ranked_input.node,
                candidate,
            )
        )
    ranked.sort(key=lambda item: item[0])
    return [(node, candidate) for _, node, candidate in ranked]


def _normalize_street_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _street_line_index(graph: nx.Graph) -> dict[str, list[LineString]]:
    cached = graph.graph.get("_pb_street_line_index")
    if cached is not None:
        return cached
    index: dict[str, list[LineString]] = {}
    edge_iter = graph.edges(keys=True, data=True) if hasattr(graph, "out_edges") else ((u, v, None, data) for u, v, data in graph.edges(data=True))
    for source, target, key, data in edge_iter:
        del key
        names = _extract_edge_name_variants(data.get("name"))
        if not names:
            continue
        line = _edge_geometry(graph, source, target, data)
        for name in names:
            normalized = _normalize_street_name(name)
            if normalized:
                index.setdefault(normalized, []).append(line)
    graph.graph["_pb_street_line_index"] = index
    return index


def graph_contains_named_street(graph: nx.Graph, street_names: list[str]) -> bool:
    if not street_names:
        return False
    index = _street_line_index(graph)
    return any(_normalize_street_name(street) in index for street in street_names if street)


def _same_street(candidate_names: tuple[str, ...], current_street_key: str) -> bool:
    return bool(current_street_key) and any(_normalize_street_name(name) == current_street_key for name in candidate_names)


def _candidate_penalty_scales(step_kind: str) -> tuple[float, float, float]:
    if step_kind == "named_turn":
        return 6.0, 35.0, 220.0
    if step_kind == "anonymous_turn":
        return 3.0, 32.0, 200.0
    if step_kind == "continue":
        return 2.5, 18.0, 120.0
    return 3.0, 15.0, 120.0


def _nearby_candidate_distance(
    nearest_distance: float,
    *,
    node_snap_threshold_m: float,
    preferred_streets: list[str],
    step_kind: str | None = None,
) -> float:
    if step_kind == "named_turn":
        return 180.0
    if nearest_distance > node_snap_threshold_m:
        return 120.0
    if preferred_streets:
        return 100.0
    return 50.0


def distance_to_named_street(graph: nx.Graph, point: LatLon, street_names: list[str]) -> float:
    if not street_names:
        return float("inf")
    index = _street_line_index(graph)
    candidate_lines: list[LineString] = []
    for street in street_names:
        normalized = _normalize_street_name(street)
        if normalized:
            candidate_lines.extend(index.get(normalized, ()))
    if not candidate_lines:
        return float("inf")
    best = float("inf")
    for line in candidate_lines:
        snapped, _ = project_point_onto_line(line, point)
        best = min(best, point_distance_meters(point, snapped))
    return best


def find_named_street_candidate(
    graph: nx.Graph,
    point: LatLon,
    preferred_streets: list[str],
    desired_heading: float,
    max_distance_m: float = 650.0,
) -> tuple[EdgeCandidate, LatLon, float] | None:
    best: tuple[float, EdgeCandidate, LatLon, float] | None = None
    if hasattr(graph, "edges"):
        edge_iter = graph.edges(keys=True, data=True) if hasattr(graph, "out_edges") else ((u, v, None, data) for u, v, data in graph.edges(data=True))
    else:
        return None
    for source, target, key, data in edge_iter:
        names = _extract_edge_name_variants(data.get("name"))
        if _street_match_score(names, preferred_streets) >= 1.0:
            continue
        candidate = _edge_candidate_from_data(graph, source, target, key, data)
        line = candidate.geometry
        snapped, _ = project_point_onto_line(line, point)
        projection_distance = point_distance_meters(point, snapped)
        if projection_distance > max_distance_m:
            continue
        score = projection_distance / 40.0 + angular_difference(candidate.bearing, desired_heading) / 180.0
        if best is None or score < best[0]:
            best = (score, candidate, snapped, projection_distance)
    if best is None:
        return None
    _, candidate, snapped, projection_distance = best
    return candidate, snapped, projection_distance


def _maneuver_penalty(
    current_heading: float | None,
    candidate_heading: float,
    direction: str | None,
    action: str | None,
) -> float:
    if current_heading is None or not direction:
        return 0.0
    direction = " ".join(direction.lower().split())
    if direction in ABSOLUTE_DIRECTIONS or direction in {"straight", "continue straight"}:
        return 0.0
    if "left" in direction:
        expected_sign = -1.0
    elif "right" in direction:
        expected_sign = 1.0
    else:
        return 0.0
    signed_delta = expected_sign * signed_heading_delta(current_heading, candidate_heading)
    if direction.startswith("sharp"):
        minimum, maximum = 75.0, 180.0
    elif direction.startswith("slight"):
        minimum, maximum = 8.0, 65.0
    elif direction.startswith("keep"):
        minimum, maximum = 5.0, 85.0
    else:
        minimum, maximum = (35.0, 170.0) if action == "turn" else (15.0, 120.0)
    penalty = 0.0
    if signed_delta < 0.0:
        penalty += 1.35 + min(abs(signed_delta), 120.0) / 120.0
        return penalty
    if signed_delta < minimum:
        penalty += (minimum - signed_delta) / max(minimum, 1.0)
    if signed_delta > maximum:
        penalty += (signed_delta - maximum) / 90.0
    return penalty


def align_state_to_street(graph: nx.Graph, state: ExecutionState, command: NavigationCommand) -> ExecutionState:
    preferred_streets = _command_street_targets(command)
    if not preferred_streets:
        return state
    desired_heading = state.current_heading
    if command.primary_direction:
        try:
            desired_heading = heading_for_instruction(state.current_heading, command.primary_direction)
        except ValueError:
            desired_heading = state.current_heading
    ranked = rank_edge_candidates(
        graph,
        state.current_coordinates,
        desired_heading,
        preferred_streets=preferred_streets,
        include_nearby=True,
        nearby_limit=8,
        nearby_distance_m=80.0,
    )
    if not ranked:
        return state
    _, edge = ranked[0]
    snapped, _ = project_point_onto_line(edge.geometry, state.current_coordinates)
    heading = edge.bearing if command.primary_action in {"head", "continue"} else desired_heading
    return ExecutionState(current_coordinates=snapped, current_heading=heading, current_street=edge.name)


class PathBuilder:
    def __init__(self, graph: nx.Graph):
        self.graph = graph

    @classmethod
    def from_osm(cls, center: LatLon, dist: int = 1000, network_type: str = "walk") -> "PathBuilder":
        import osmnx as ox

        graph = ox.graph_from_point(center, dist=dist, network_type=network_type, simplify=True)
        return cls(graph)

    def local_view(self, center: LatLon, dist: int) -> "PathBuilder":
        return PathBuilder(_local_subgraph(self.graph, center, float(dist)))

    def _score_candidates(
        self,
        point: LatLon,
        desired_heading: float,
        *,
        preferred_streets: list[str] | None = None,
        current_street: str | None = None,
        include_nearby: bool = False,
        nearby_limit: int = 8,
        nearby_distance_m: float = 50.0,
        step_kind: str = "continue",
        continuity_heading: float | None = None,
        prefer_current_street: bool = False,
        maneuver_direction: str | None = None,
        action: str | None = None,
    ) -> list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]]:
        current_street_key = _normalize_street_name(current_street) if current_street else ""
        ranked: list[tuple[float, Any, EdgeCandidate, ExecutionCandidateDiagnostic]] = []
        street_weight, projection_scale, node_scale = _candidate_penalty_scales(step_kind)
        continuity_weight = 0.0 if step_kind == "absolute_head" else (0.55 if prefer_current_street else 0.25)
        for ranked_input in _ranked_edge_inputs(
            self.graph,
            point,
            include_nearby=include_nearby,
            nearby_limit=nearby_limit,
            nearby_distance_m=nearby_distance_m,
        ):
            node = ranked_input.node
            candidate = ranked_input.candidate
            street_penalty = _street_match_score(candidate.names, preferred_streets)
            turn_penalty = angular_difference(candidate.bearing, desired_heading) / 180.0
            if step_kind == "short_connector":
                turn_penalty *= 0.35
            elif step_kind == "continue":
                turn_penalty *= 0.75
            if step_kind in {"anonymous_turn", "named_turn"}:
                turn_penalty *= 1.65
            same_street = _same_street(candidate.names, current_street_key)
            continuity_penalty = 0.0
            if continuity_heading is not None and continuity_weight > 0.0:
                continuity_penalty += angular_difference(candidate.bearing, continuity_heading) / 180.0 * continuity_weight
            if current_street_key and prefer_current_street and not same_street:
                continuity_penalty += 0.5
            maneuver_penalty = _maneuver_penalty(
                continuity_heading,
                candidate.bearing,
                maneuver_direction,
                action,
            )
            projection_penalty = ranked_input.projection_distance_m / projection_scale
            node_penalty = ranked_input.node_distance_m / node_scale
            total_score = (
                street_penalty * street_weight
                + turn_penalty
                + continuity_penalty
                + projection_penalty
                + node_penalty
            )
            diagnostic = ExecutionCandidateDiagnostic(
                node=_node_label(node),
                street=candidate.name,
                bearing=candidate.bearing,
                street_penalty=street_penalty,
                turn_penalty=turn_penalty,
                continuity_penalty=continuity_penalty,
                projection_distance_m=ranked_input.projection_distance_m,
                node_distance_m=ranked_input.node_distance_m,
                preview_penalty=maneuver_penalty,
                total_score=total_score,
            )
            ranked.append((total_score, node, candidate, diagnostic))
        ranked.sort(
            key=lambda item: (
                round(item[0], 12),
                item[3].street_penalty,
                item[3].turn_penalty,
                item[3].continuity_penalty,
                item[3].projection_distance_m,
                item[3].node_distance_m,
                round(item[2].bearing, 6),
                _node_label(item[1]),
                _node_label(item[2].target),
                str(item[2].key),
            )
        )
        return [(node, candidate, diagnostic) for _, node, candidate, diagnostic in ranked]

    def _advance_along_edge(
        self,
        state: ExecutionState,
        edge: EdgeCandidate,
        remaining: float,
        command: NavigationCommand,
        desired_heading: float,
        preferred_streets: list[str],
        short_instruction_heading_threshold_m: float,
    ) -> tuple[list[tuple[float, float]] | None, float]:
        previous_street = state.current_street
        segment_points, endpoint, moved = extract_line_segment(edge.geometry, state.current_coordinates, remaining)
        state.current_coordinates = endpoint
        if (
            command.primary_direction
            and not preferred_streets
            and command.primary_distance <= short_instruction_heading_threshold_m
            and moved <= short_instruction_heading_threshold_m
        ):
            state.current_heading = desired_heading
        elif len(segment_points) >= 2 and segment_points[-2] != segment_points[-1]:
            state.current_heading = bearing_between_points(segment_points[-2], segment_points[-1])
        else:
            state.current_heading = edge.bearing
        state.current_street = _carry_forward_current_street(previous_street, edge.name, command, preferred_streets)
        if (
            state.current_street is None
            and previous_street
            and command.primary_action == "continue"
            and not preferred_streets
            and moved <= 40.0
        ):
            state.current_street = previous_street
        if len(segment_points) < 2:
            return None, moved
        return [(lon, lat) for lat, lon in segment_points], moved

    def _path_coordinates_between_points(self, start: LatLon, end: LatLon) -> list[tuple[float, float]] | None:
        source = nearest_node(self.graph, start)
        target = nearest_node(self.graph, end)
        coordinates: list[tuple[float, float]] = [(start[1], start[0])]
        if source == target:
            if coordinates[-1] != (end[1], end[0]):
                coordinates.append((end[1], end[0]))
            return coordinates if len(coordinates) >= 2 else None
        try:
            node_path = nx.shortest_path(self.graph, source, target, weight="length")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            coordinates.append((end[1], end[0]))
            return coordinates
        for u, v in zip(node_path, node_path[1:]):
            edge_map = self.graph.get_edge_data(u, v)
            if edge_map is None:
                segment = [(self.graph.nodes[u]["x"], self.graph.nodes[u]["y"]), (self.graph.nodes[v]["x"], self.graph.nodes[v]["y"])]
            else:
                _, data = _best_edge_data(edge_map)
                segment = list(_oriented_line(self.graph, u, v, data).coords)
            if coordinates[-1] == segment[0]:
                coordinates.extend(segment[1:])
            else:
                coordinates.extend(segment)
        if coordinates[-1] != (end[1], end[0]):
            coordinates.append((end[1], end[0]))
        return coordinates if len(coordinates) >= 2 else None

    def _default_action_edge(
        self,
        state: ExecutionState,
        command: NavigationCommand,
        desired_heading: float,
        preferred_streets: list[str],
        node_snap_threshold_m: float,
    ) -> tuple[Any, EdgeCandidate]:
        nearest = nearest_node(self.graph, state.current_coordinates)
        nearest_distance = point_distance_meters(state.current_coordinates, _node_coordinate(self.graph, nearest))
        action = command.primary_action
        step_kind = _command_step_kind(command)
        include_nearby = nearest_distance > node_snap_threshold_m or action == "turn" or bool(preferred_streets)
        nearby_distance = _nearby_candidate_distance(
            nearest_distance,
            node_snap_threshold_m=node_snap_threshold_m,
            preferred_streets=preferred_streets,
            step_kind=step_kind if action == "turn" else None,
        )
        ranked = self._score_candidates(
            state.current_coordinates,
            desired_heading,
            preferred_streets=preferred_streets,
            current_street=state.current_street,
            include_nearby=include_nearby,
            nearby_distance_m=nearby_distance,
            step_kind=step_kind,
            continuity_heading=state.current_heading,
            prefer_current_street=action == "continue" or step_kind == "short_connector",
            maneuver_direction=command.primary_direction,
            action=action,
        )
        if not ranked:
            raise ValueError("No traversable edges found for command selection.")
        node, edge, _ = ranked[0]
        return node, edge

    def _preview_target_streets(
        self,
        commands: list[NavigationCommand],
        index: int,
        max_offset: int = 3,
    ) -> tuple[list[str], int]:
        for offset in range(1, max_offset + 1):
            next_index = index + offset
            if next_index >= len(commands):
                break
            future = commands[next_index]
            streets = [street for street in future.all_street_targets if street and not _is_placeholder_street_name(street)]
            if streets:
                return streets, offset
        return [], 0

    def _anonymous_chain_preview_length(
        self,
        commands: list[NavigationCommand],
        index: int,
        *,
        max_length: int = 6,
    ) -> int:
        preview_length = 1
        for offset in range(1, max_length):
            next_index = index + offset
            if next_index >= len(commands):
                break
            future = commands[next_index]
            if future.primary_action == "arrive":
                break
            if future.start_streets or future.end_streets:
                break
            future_step_kind = _command_step_kind(future)
            if future_step_kind not in {"anonymous_turn", "continue", "short_connector"}:
                break
            preview_length += 1
        return preview_length

    def _choose_lookahead_edge(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        desired_heading: float,
        preferred_streets: list[str],
        node_snap_threshold_m: float,
    ) -> tuple[Any, EdgeCandidate] | None:
        if command.primary_action not in {"head", "turn"}:
            return None
        allow_named_head_oov = False
        if preferred_streets:
            if command.primary_action == "head" and index == 0:
                named_distance = distance_to_named_street(self.graph, state.current_coordinates, preferred_streets)
                named_recovery_limit = min(_named_street_recovery_limit(command), 250.0)
                allow_named_head_oov = named_distance == float("inf") or named_distance > named_recovery_limit
            if not allow_named_head_oov:
                return None
        if command.primary_distance > 15.0 and not (command.primary_action == "turn" and command.primary_distance >= 150.0):
            if not allow_named_head_oov:
                return None
        if allow_named_head_oov:
            preferred_streets = []
        target_streets, preview_length = self._preview_target_streets(commands, index)
        if not target_streets or preview_length <= 0:
            return None
        include_nearby = command.primary_action == "turn" and command.primary_distance >= 150.0
        candidates = self._score_candidates(
            state.current_coordinates,
            desired_heading,
            preferred_streets=preferred_streets,
            current_street=state.current_street if command.primary_action == "turn" else None,
            include_nearby=include_nearby,
            step_kind=_command_step_kind(command),
            continuity_heading=state.current_heading,
            maneuver_direction=command.primary_direction,
            action=command.primary_action,
        )
        if not candidates:
            return None
        default_choice = self._default_action_edge(state, command, desired_heading, preferred_streets, node_snap_threshold_m)
        preview_commands = commands[index : index + preview_length]

        def preview_distance(choice: tuple[Any, EdgeCandidate]) -> float:
            preview = self._execute_sequence(
                preview_commands,
                state,
                align_start=False,
                allow_lookahead=False,
                override_choices={0: choice},
            )
            return distance_to_named_street(self.graph, preview.final_state.current_coordinates, target_streets)

        baseline_distance = preview_distance(default_choice)
        best_choice = default_choice
        best_distance = baseline_distance
        for node, edge, _ in candidates[:4]:
            choice = (node, edge)
            candidate_distance = preview_distance(choice)
            if candidate_distance < best_distance:
                best_choice = choice
                best_distance = candidate_distance
        if best_choice != default_choice and best_distance + 15.0 < baseline_distance:
            return best_choice
        return None

    def _preview_choice_cost(
        self,
        commands: list[NavigationCommand],
        state: ExecutionState,
        choice: tuple[Any, EdgeCandidate],
        preview_length: int,
    ) -> float:
        preview = self._preview_trace(commands, state, choice, preview_length)
        total = 0.0
        for step_diagnostic in preview.step_diagnostics:
            if step_diagnostic.candidate_diagnostics:
                total += step_diagnostic.candidate_diagnostics[0].total_score
        return total

    def _preview_trace(
        self,
        commands: list[NavigationCommand],
        state: ExecutionState,
        choice: tuple[Any, EdgeCandidate],
        preview_length: int,
    ) -> ExecutionTrace:
        return self._execute_sequence(
            commands[:preview_length],
            state,
            align_start=False,
            allow_lookahead=False,
            override_choices={0: choice},
        )

    def _preview_trace_metrics(
        self,
        commands: list[NavigationCommand],
        state: ExecutionState,
        choice: tuple[Any, EdgeCandidate],
        preview_length: int,
        *,
        target_streets: list[str] | None = None,
    ) -> tuple[float, float]:
        preview_trace = self._preview_trace(commands, state, choice, preview_length)
        preview_cost = 0.0
        for step_diagnostic in preview_trace.step_diagnostics:
            if step_diagnostic.candidate_diagnostics:
                preview_cost += step_diagnostic.candidate_diagnostics[0].total_score
        preview_target_distance = (
            distance_to_named_street(self.graph, preview_trace.final_state.current_coordinates, target_streets)
            if target_streets
            else float("inf")
        )
        return preview_cost, preview_target_distance

    def _choose_named_turn_lookahead_edge(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
    ) -> tuple[Any, EdgeCandidate] | None:
        if command.primary_distance < 120.0:
            return None
        if command.primary_direction not in {"left", "right"}:
            return None
        exact_matches = [
            (node, edge, diagnostic)
            for node, edge, diagnostic in ranked_candidates
            if diagnostic.street_penalty <= 0.01
        ]
        if len(exact_matches) < 2:
            return None
        baseline_score = exact_matches[0][2].total_score
        candidate_pool = [
            (node, edge, diagnostic)
            for node, edge, diagnostic in exact_matches[:4]
            if diagnostic.total_score <= baseline_score + 0.5
        ]
        if len(candidate_pool) < 2:
            return None
        target_streets, target_offset = self._preview_target_streets(commands, index, max_offset=3)
        preview_length = min(4, len(commands) - index)
        if target_offset > 0:
            preview_length = max(preview_length, min(len(commands) - index, target_offset + 1))
        if preview_length < 2:
            return None
        baseline_choice = (candidate_pool[0][0], candidate_pool[0][1])
        baseline_cost, baseline_target_distance = self._preview_trace_metrics(
            commands[index : index + preview_length],
            state,
            baseline_choice,
            preview_length,
            target_streets=target_streets,
        )
        best_choice = baseline_choice
        best_cost = baseline_cost
        best_target_distance = baseline_target_distance
        for node, edge, _ in candidate_pool[1:]:
            choice = (node, edge)
            preview_cost, preview_target_distance = self._preview_trace_metrics(
                commands[index : index + preview_length],
                state,
                choice,
                preview_length,
                target_streets=target_streets,
            )
            if (preview_target_distance, preview_cost) < (best_target_distance, best_cost):
                best_choice = choice
                best_cost = preview_cost
                best_target_distance = preview_target_distance
        if (
            target_streets
            and best_choice != baseline_choice
            and (
                best_target_distance + 15.0 < baseline_target_distance
                or (
                    best_target_distance <= baseline_target_distance + 10.0
                    and best_cost + 0.2 < baseline_cost
                )
            )
        ):
            return best_choice
        if best_choice != baseline_choice and best_cost + 0.2 < baseline_cost:
            return best_choice
        return None

    def _choose_named_turn_fallback_edge(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
    ) -> tuple[Any, EdgeCandidate] | None:
        preferred_streets = [street for street in command.all_street_targets if street and not _is_placeholder_street_name(street)]
        if command.primary_action != "turn" or not preferred_streets:
            return None
        if command.primary_direction not in {"left", "right"}:
            return None
        if len(ranked_candidates) < 2:
            return None

        baseline_node, baseline_edge, baseline_diagnostic = ranked_candidates[0]
        start_target_distance = distance_to_named_street(self.graph, state.current_coordinates, preferred_streets)
        if start_target_distance == float("inf"):
            if command.primary_distance < 80.0 or baseline_edge.name is None:
                return None
            for node, edge, diagnostic in ranked_candidates[1:6]:
                if edge.name is not None:
                    continue
                if diagnostic.total_score <= baseline_diagnostic.total_score + 1.0:
                    return node, edge
            return None
        if start_target_distance <= 250.0 or command.primary_distance > 40.0:
            return None

        preview_length = min(3, len(commands) - index)
        preview_commands = commands[index : index + preview_length]
        baseline_choice = (baseline_node, baseline_edge)
        baseline_cost, baseline_target_distance = self._preview_trace_metrics(
            preview_commands,
            state,
            baseline_choice,
            preview_length,
            target_streets=preferred_streets,
        )
        best_choice = baseline_choice
        best_cost = baseline_cost
        best_target_distance = baseline_target_distance
        for node, edge, _ in ranked_candidates[1:6]:
            preview_cost, preview_target_distance = self._preview_trace_metrics(
                preview_commands,
                state,
                (node, edge),
                preview_length,
                target_streets=preferred_streets,
            )
            if (preview_target_distance, preview_cost) < (best_target_distance, best_cost):
                best_choice = (node, edge)
                best_cost = preview_cost
                best_target_distance = preview_target_distance
        if best_choice == baseline_choice:
            return None
        if best_target_distance <= start_target_distance - 75.0:
            return best_choice
        if best_target_distance <= start_target_distance - 25.0 and best_cost + 0.2 < baseline_cost:
            return best_choice
        return None

    def _choose_named_street_continuation_edge(
        self,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
        *,
        preferred_streets: list[str],
        step_kind: str,
        remaining_distance: float,
    ) -> tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic] | None:
        if step_kind != "named_turn" or not preferred_streets or remaining_distance < 80.0:
            return None
        if len(ranked_candidates) < 2:
            return None

        top_node, top_edge, top_diagnostic = ranked_candidates[0]
        if top_diagnostic.street_penalty > 0.01 or top_edge.length_m >= 20.0:
            return None

        best_choice: tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic] | None = None
        best_key: tuple[float, float, float, float, float] | None = None
        minimum_length = max(80.0, top_edge.length_m * 8.0)
        for node, edge, diagnostic in ranked_candidates[1:6]:
            if diagnostic.street_penalty > 0.01:
                continue
            if edge.length_m < minimum_length:
                continue
            if diagnostic.total_score > top_diagnostic.total_score + 0.25:
                continue
            choice_key = (
                diagnostic.total_score,
                -edge.length_m,
                diagnostic.turn_penalty,
                diagnostic.projection_distance_m,
                diagnostic.node_distance_m,
            )
            if best_key is None or choice_key < best_key:
                best_choice = (node, edge, diagnostic)
                best_key = choice_key
        return best_choice

    def _choose_anonymous_turn_rescue_edge(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
    ) -> tuple[Any, EdgeCandidate] | None:
        if command.primary_action != "turn":
            return None
        if command.start_streets or command.end_streets:
            return None
        if len(ranked_candidates) < 2:
            return None
        connector_choice = self._choose_anonymous_turn_connector_edge(
            commands,
            index,
            state,
            command,
            ranked_candidates,
        )
        if command.primary_distance <= 15.0 or command.primary_distance > 80.0:
            return connector_choice

        baseline_node, baseline_edge, baseline_diagnostic = ranked_candidates[0]
        if baseline_diagnostic.turn_penalty < 0.55:
            return connector_choice

        preview_length = min(3, len(commands) - index)
        preview_commands = commands[index : index + preview_length]
        baseline_choice = (baseline_node, baseline_edge)
        baseline_cost = baseline_diagnostic.total_score
        if preview_length >= 2:
            baseline_cost = self._preview_choice_cost(preview_commands, state, baseline_choice, preview_length)

        current_street_key = _normalize_street_name(state.current_street) if state.current_street else ""
        best_choice: tuple[Any, EdgeCandidate] | None = None
        best_key: tuple[float, float, float, float] | None = None
        for node, edge, diagnostic in ranked_candidates[1:4]:
            if diagnostic.turn_penalty + 0.2 >= baseline_diagnostic.turn_penalty:
                continue
            if diagnostic.projection_distance_m > 40.0 or diagnostic.node_distance_m > 40.0:
                continue
            if current_street_key and any(_normalize_street_name(name) == current_street_key for name in edge.names):
                continue
            preview_cost = diagnostic.total_score
            if preview_length >= 2:
                preview_cost = self._preview_choice_cost(preview_commands, state, (node, edge), preview_length)
            if preview_cost > baseline_cost + 0.35:
                continue
            choice_key = (
                preview_cost,
                diagnostic.turn_penalty,
                diagnostic.projection_distance_m,
                diagnostic.node_distance_m,
            )
            if best_key is None or choice_key < best_key:
                best_choice = (node, edge)
                best_key = choice_key
        if best_choice is not None:
            return best_choice
        return connector_choice

    def _choose_anonymous_chain_lookahead_edge(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
    ) -> tuple[Any, EdgeCandidate] | None:
        if command.primary_action != "turn":
            return None
        if command.start_streets or command.end_streets:
            return None
        if command.primary_distance > 80.0:
            return None
        if len(ranked_candidates) < 2:
            return None

        preview_length = self._anonymous_chain_preview_length(commands, index)
        if preview_length < 4:
            return None

        baseline_node, baseline_edge, baseline_diagnostic = ranked_candidates[0]
        current_street_key = _normalize_street_name(state.current_street) if state.current_street else ""
        baseline_same_street = _same_street(baseline_edge.names, current_street_key)

        preview_commands = commands[index : index + preview_length]
        baseline_choice = (baseline_node, baseline_edge)
        baseline_cost = self._preview_choice_cost(preview_commands, state, baseline_choice, preview_length)

        best_choice = baseline_choice
        best_cost = baseline_cost
        max_total_delta = 0.85 if baseline_same_street else 0.25
        max_turn_delta = 0.55 if baseline_same_street else 0.2
        for node, edge, diagnostic in ranked_candidates[1:4]:
            if current_street_key and _same_street(edge.names, current_street_key):
                continue
            if diagnostic.total_score > baseline_diagnostic.total_score + max_total_delta:
                continue
            if diagnostic.turn_penalty > baseline_diagnostic.turn_penalty + max_turn_delta:
                continue
            if diagnostic.projection_distance_m > baseline_diagnostic.projection_distance_m + 10.0:
                continue
            if diagnostic.node_distance_m > baseline_diagnostic.node_distance_m + 15.0:
                continue
            preview_cost = self._preview_choice_cost(preview_commands, state, (node, edge), preview_length)
            if preview_cost < best_cost:
                best_choice = (node, edge)
                best_cost = preview_cost
        required_margin = 0.18 if baseline_same_street else 0.08
        if best_choice != baseline_choice and best_cost + required_margin < baseline_cost:
            return best_choice
        return None

    def _choose_continue_lookahead_edge(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
    ) -> tuple[Any, EdgeCandidate] | None:
        if command.primary_action != "continue":
            return None
        if command.start_streets or command.end_streets:
            return None
        if command.primary_distance < 80.0:
            return None
        if command.primary_direction not in {"keep left", "keep right", "straight"}:
            return None
        if len(ranked_candidates) < 2:
            return None

        target_streets, target_offset = self._preview_target_streets(commands, index, max_offset=2)
        if not target_streets or target_offset <= 0:
            return None

        preview_length = max(2, min(4, len(commands) - index, target_offset + 1))
        preview_commands = commands[index : index + preview_length]
        baseline_node, baseline_edge, baseline_diagnostic = ranked_candidates[0]
        baseline_choice = (baseline_node, baseline_edge)
        baseline_cost, baseline_target_distance = self._preview_trace_metrics(
            preview_commands,
            state,
            baseline_choice,
            preview_length,
            target_streets=target_streets,
        )

        best_choice = baseline_choice
        best_cost = baseline_cost
        best_target_distance = baseline_target_distance
        for node, edge, diagnostic in ranked_candidates[1:5]:
            if diagnostic.total_score > baseline_diagnostic.total_score + 0.35:
                continue
            if diagnostic.projection_distance_m > baseline_diagnostic.projection_distance_m + 20.0:
                continue
            if diagnostic.node_distance_m > baseline_diagnostic.node_distance_m + 20.0:
                continue
            preview_cost, preview_target_distance = self._preview_trace_metrics(
                preview_commands,
                state,
                (node, edge),
                preview_length,
                target_streets=target_streets,
            )
            if (preview_target_distance, preview_cost) < (best_target_distance, best_cost):
                best_choice = (node, edge)
                best_cost = preview_cost
                best_target_distance = preview_target_distance
        if best_choice == baseline_choice:
            return None
        if best_target_distance + 15.0 < baseline_target_distance:
            return best_choice
        if best_target_distance <= baseline_target_distance + 10.0 and best_cost + 0.15 < baseline_cost:
            return best_choice
        return None

    def _choose_anonymous_turn_connector_edge(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
    ) -> tuple[Any, EdgeCandidate] | None:
        if command.primary_action != "turn":
            return None
        if command.start_streets or command.end_streets:
            return None
        if not state.current_street or not (60.0 < command.primary_distance <= 90.0):
            return None
        if len(ranked_candidates) < 2:
            return None
        target_streets, _ = self._preview_target_streets(commands, index)
        if target_streets:
            return None

        baseline_node, baseline_edge, _ = ranked_candidates[0]
        if baseline_edge.name is None:
            return None
        preview_length = min(3, len(commands) - index)
        preview_commands = commands[index : index + preview_length]
        baseline_cost = self._preview_choice_cost(preview_commands, state, (baseline_node, baseline_edge), preview_length)

        best_choice: tuple[Any, EdgeCandidate] | None = None
        best_cost: float | None = None
        for node, edge, diagnostic in ranked_candidates[1:5]:
            if edge.name is not None:
                continue
            if diagnostic.projection_distance_m > 40.0 or diagnostic.node_distance_m > 40.0:
                continue
            preview_cost = self._preview_choice_cost(preview_commands, state, (node, edge), preview_length)
            if best_cost is None or preview_cost < best_cost:
                best_choice = (node, edge)
                best_cost = preview_cost
        if best_choice is not None and best_cost is not None and best_cost + 0.4 < baseline_cost:
            return best_choice
        return None

    def _choose_corridor_retention_edge(
        self,
        ranked_candidates: list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]],
        *,
        current_street: str | None,
        preferred_streets: list[str],
        step_kind: str,
    ) -> tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic] | None:
        if preferred_streets:
            return None
        if step_kind not in {"anonymous_turn", "continue"}:
            return None
        current_street_key = _normalize_street_name(current_street) if current_street else ""
        if not current_street_key or len(ranked_candidates) < 2:
            return None
        baseline = ranked_candidates[0]
        if _same_street(baseline[1].names, current_street_key):
            return None
        baseline_diagnostic = baseline[2]
        best_same_street: tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic] | None = None
        best_score = float("inf")
        for node, edge, diagnostic in ranked_candidates[1:6]:
            if not _same_street(edge.names, current_street_key):
                continue
            if diagnostic.projection_distance_m > baseline_diagnostic.projection_distance_m + 25.0:
                continue
            if diagnostic.total_score > baseline_diagnostic.total_score + 0.35:
                continue
            if diagnostic.total_score < best_score:
                best_same_street = (node, edge, diagnostic)
                best_score = diagnostic.total_score
        return best_same_street

    def _rank_command_entry_candidates(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        *,
        node_snap_threshold_m: float = 15.0,
    ) -> tuple[float, str, list[str], list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]]]:
        desired_heading = state.current_heading
        if command.primary_direction:
            try:
                desired_heading = heading_for_instruction(state.current_heading, command.primary_direction)
            except ValueError:
                desired_heading = state.current_heading
        step_kind = _command_step_kind(command)
        preferred_streets = _command_street_targets(command)
        ranked_candidates = self._score_candidates(
            state.current_coordinates,
            desired_heading,
            preferred_streets=preferred_streets,
            current_street=state.current_street,
            include_nearby=True,
            nearby_limit=20 if step_kind == "named_turn" else 8,
            nearby_distance_m=_nearby_candidate_distance(
                point_distance_meters(
                    state.current_coordinates,
                    _node_coordinate(self.graph, nearest_node(self.graph, state.current_coordinates)),
                ),
                node_snap_threshold_m=node_snap_threshold_m,
                preferred_streets=preferred_streets,
                step_kind=step_kind,
            ),
            step_kind=step_kind,
            continuity_heading=state.current_heading,
            prefer_current_street=_prefer_current_street_for_step(commands, index, command, step_kind, state.current_street),
            maneuver_direction=command.primary_direction,
            action=command.primary_action,
        )
        return desired_heading, step_kind, preferred_streets, ranked_candidates

    def _search_candidate_pool(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        command: NavigationCommand,
        *,
        candidate_limit: int,
    ) -> list[tuple[Any, EdgeCandidate, ExecutionCandidateDiagnostic]]:
        if command.primary_action != "turn":
            return []
        _, step_kind, preferred_streets, ranked_candidates = self._rank_command_entry_candidates(commands, index, state, command)
        if not ranked_candidates:
            return []
        baseline_diagnostic = ranked_candidates[0][2]
        ambiguous_turn = len(ranked_candidates) > 1 and ranked_candidates[1][2].total_score <= baseline_diagnostic.total_score + 0.25
        if step_kind == "named_turn":
            exact_matches = sum(1 for _, _, diagnostic in ranked_candidates[:6] if diagnostic.street_penalty <= 0.01)
            preview_targets, _ = self._preview_target_streets(commands, index)
            if exact_matches == 0 and baseline_diagnostic.street_penalty >= 0.99:
                return []
            if exact_matches < 2 and not preview_targets:
                return []
        elif step_kind == "anonymous_turn":
            if not (ambiguous_turn or baseline_diagnostic.turn_penalty > 0.75):
                return []
        else:
            return []
        if step_kind == "named_turn" and preferred_streets:
            street_distance = distance_to_named_street(self.graph, state.current_coordinates, preferred_streets)
            if 40.0 < street_distance <= _named_street_recovery_limit(command):
                return [ranked_candidates[0]]
        pool = [ranked_candidates[0]]
        for node, edge, diagnostic in ranked_candidates[1:8]:
            if diagnostic.total_score > baseline_diagnostic.total_score + 0.9:
                continue
            if diagnostic.projection_distance_m > baseline_diagnostic.projection_distance_m + 30.0:
                continue
            if diagnostic.node_distance_m > baseline_diagnostic.node_distance_m + 30.0:
                continue
            pool.append((node, edge, diagnostic))
            if len(pool) >= candidate_limit:
                break
        return pool

    def _trace_cost(self, trace: ExecutionTrace) -> float:
        total = 0.0
        repeated_edges = max(0, len(trace.traversed_edges) - len(set(trace.traversed_edges)))
        street_shifts = 0
        for step_diagnostic in trace.step_diagnostics:
            if step_diagnostic.selected_score is not None:
                total += step_diagnostic.selected_score
            elif step_diagnostic.candidate_diagnostics:
                total += step_diagnostic.candidate_diagnostics[0].total_score
            street_shifts += sum(1 for note in step_diagnostic.notes if note.startswith("street-shift:"))
        total += repeated_edges * 0.45
        total += street_shifts * 0.1
        return total

    def _trace_selection_cost(
        self,
        commands: list[NavigationCommand],
        trace: ExecutionTrace,
        *,
        length_ratio_weight: float = 100.0,
    ) -> float:
        total = self._trace_cost(trace)
        expected_length = sum(command.primary_distance for command in commands)
        if expected_length <= 0.0:
            return total
        actual_length = path_length_meters(trace.waypoints)
        total += abs((actual_length / expected_length) - 1.0) * length_ratio_weight
        return total

    def _prefer_search_trace(
        self,
        commands: list[NavigationCommand],
        base_trace: ExecutionTrace,
        search_trace: ExecutionTrace,
    ) -> bool:
        base_cost = self._trace_cost(base_trace)
        search_cost = self._trace_cost(search_trace)
        if search_cost + 1e-9 >= base_cost:
            return False
        base_selection_cost = self._trace_selection_cost(commands, base_trace)
        search_selection_cost = self._trace_selection_cost(commands, search_trace)
        if base_selection_cost < 10.0:
            return search_selection_cost + 1.2 < base_selection_cost
        if search_selection_cost + 1e-9 < base_selection_cost:
            return True
        return (
            search_cost + 0.1 < base_cost
            and search_selection_cost <= base_selection_cost + 1.5
        )

    def _search_signature(self, index: int, trace: ExecutionTrace) -> tuple[int, str, int, str]:
        final_state = trace.final_state
        node = nearest_node(self.graph, final_state.current_coordinates)
        heading_bin = int(round(final_state.current_heading / 20.0)) % 18
        street_key = _normalize_street_name(final_state.current_street) if final_state.current_street else ""
        return index, _node_label(node), heading_bin, street_key

    def _search_window_end(
        self,
        commands: list[NavigationCommand],
        index: int,
        *,
        max_commands: int = 6,
        max_turns: int = 4,
    ) -> int:
        turns = 0
        end = index
        while end < len(commands) and end - index < max_commands:
            command = commands[end]
            end += 1
            if command.primary_action == "arrive":
                break
            if command.primary_action == "turn":
                turns += 1
                if turns >= max_turns and end - index >= 2:
                    break
        return end

    def _choose_window_search_override(
        self,
        commands: list[NavigationCommand],
        index: int,
        state: ExecutionState,
        *,
        beam_width: int = 3,
        candidate_limit: int = 2,
        max_commands: int = 6,
        max_turns: int = 4,
    ) -> tuple[Any, EdgeCandidate] | None:
        command = commands[index]
        candidate_pool = self._search_candidate_pool(
            commands,
            index,
            state,
            command,
            candidate_limit=candidate_limit,
        )
        if len(candidate_pool) <= 1:
            return None
        window_end = self._search_window_end(
            commands,
            index,
            max_commands=max_commands,
            max_turns=max_turns,
        )
        local_commands = commands[index:window_end]
        if len(local_commands) < 2:
            return None
        baseline_trace = self._execute_sequence(
            local_commands,
            state,
            align_start=False,
            allow_lookahead=False,
        )
        baseline_score = self._trace_cost(baseline_trace)
        hypotheses = [SearchHypothesis()]
        for local_offset, local_command in enumerate(local_commands):
            expanded: list[SearchHypothesis] = []
            for hypothesis in hypotheses:
                prefix_trace = self._execute_sequence(
                    local_commands[:local_offset],
                    state,
                    align_start=False,
                    allow_lookahead=False,
                    override_choices=hypothesis.overrides,
                )
                if local_command.primary_action == "arrive":
                    expanded.append(
                        SearchHypothesis(
                            overrides=dict(hypothesis.overrides),
                            score=self._trace_cost(prefix_trace),
                            trace=prefix_trace,
                        )
                    )
                    continue
                local_pool = self._search_candidate_pool(
                    commands,
                    index + local_offset,
                    prefix_trace.final_state,
                    local_command,
                    candidate_limit=candidate_limit,
                )
                if len(local_pool) <= 1:
                    next_trace = self._execute_sequence(
                        local_commands[: local_offset + 1],
                        state,
                        align_start=False,
                        allow_lookahead=False,
                        override_choices=hypothesis.overrides,
                    )
                    expanded.append(
                        SearchHypothesis(
                            overrides=dict(hypothesis.overrides),
                            score=self._trace_cost(next_trace),
                            trace=next_trace,
                        )
                    )
                    continue
                for node, edge, _ in local_pool:
                    overrides = dict(hypothesis.overrides)
                    overrides[local_offset] = (node, edge)
                    next_trace = self._execute_sequence(
                        local_commands[: local_offset + 1],
                        state,
                        align_start=False,
                        allow_lookahead=False,
                        override_choices=overrides,
                    )
                    expanded.append(
                        SearchHypothesis(
                            overrides=overrides,
                            score=self._trace_cost(next_trace),
                            trace=next_trace,
                        )
                    )
            deduped: dict[tuple[int, str, int, str], SearchHypothesis] = {}
            for hypothesis in expanded:
                if hypothesis.trace is None:
                    continue
                signature = self._search_signature(local_offset, hypothesis.trace)
                best = deduped.get(signature)
                if best is None or hypothesis.score < best.score:
                    deduped[signature] = hypothesis
            if not deduped:
                return None
            hypotheses = sorted(
                deduped.values(),
                key=lambda hypothesis: hypothesis.score,
            )[:beam_width]
        if not hypotheses:
            return None
        best = min(hypotheses, key=lambda hypothesis: hypothesis.score)
        override = best.overrides.get(0)
        if override is None:
            return None
        if best.score + 0.05 >= baseline_score:
            return None
        return override

    def _execute_windowed_search(
        self,
        commands: list[NavigationCommand],
        initial_state: ExecutionState,
        *,
        align_start: bool = True,
        beam_width: int = 3,
        candidate_limit: int = 2,
        max_commands: int = 6,
        max_turns: int = 4,
    ) -> ExecutionTrace:
        overrides: dict[int, tuple[Any, EdgeCandidate]] = {}
        for index, command in enumerate(commands):
            if command.primary_action == "arrive":
                break
            prefix_trace = self._execute_sequence(
                commands[:index],
                initial_state,
                align_start=align_start,
                allow_lookahead=False,
                override_choices=overrides,
            )
            override = self._choose_window_search_override(
                commands,
                index,
                prefix_trace.final_state,
                beam_width=beam_width,
                candidate_limit=candidate_limit,
                max_commands=max_commands,
                max_turns=max_turns,
            )
            if override is not None:
                overrides[index] = override
        return self._execute_sequence(
            commands,
            initial_state,
            align_start=align_start,
            allow_lookahead=False,
            override_choices=overrides,
        )

    def _execute_search(
        self,
        commands: list[NavigationCommand],
        initial_state: ExecutionState,
        *,
        align_start: bool = True,
        beam_width: int = 4,
        candidate_limit: int = 2,
        preview_weight: float = 0.18,
        preview_length: int = 4,
    ) -> ExecutionTrace:
        if not self._search_budget_eligible(commands):
            fallback = self._execute_sequence(commands, initial_state, align_start=align_start, allow_lookahead=True)
            if fallback.step_diagnostics:
                fallback.step_diagnostics[0].notes.append("search-fallback:budget")
            return fallback
        hypotheses = [SearchHypothesis()]
        for index, command in enumerate(commands):
            expanded: list[SearchHypothesis] = []
            for hypothesis in hypotheses:
                prefix_trace = self._execute_sequence(
                    commands[:index],
                    initial_state,
                    align_start=align_start,
                    allow_lookahead=False,
                    override_choices=hypothesis.overrides,
                )
                if command.primary_action == "arrive":
                    expanded.append(SearchHypothesis(overrides=dict(hypothesis.overrides), score=self._trace_cost(prefix_trace), trace=prefix_trace))
                    continue
                candidate_pool = self._search_candidate_pool(
                    commands,
                    index,
                    prefix_trace.final_state,
                    command,
                    candidate_limit=candidate_limit,
                )
                if len(candidate_pool) <= 1:
                    next_trace = self._execute_sequence(
                        commands[: index + 1],
                        initial_state,
                        align_start=align_start,
                        allow_lookahead=False,
                        override_choices=hypothesis.overrides,
                    )
                    expanded.append(SearchHypothesis(overrides=dict(hypothesis.overrides), score=self._trace_cost(next_trace), trace=next_trace))
                    continue
                for node, edge, _ in candidate_pool:
                    overrides = dict(hypothesis.overrides)
                    overrides[index] = (node, edge)
                    next_trace = self._execute_sequence(
                        commands[: index + 1],
                        initial_state,
                        align_start=align_start,
                        allow_lookahead=False,
                        override_choices=overrides,
                    )
                    candidate_score = self._trace_cost(next_trace)
                    tail_length = min(preview_length, len(commands) - index)
                    if tail_length >= 2:
                        candidate_score += preview_weight * self._preview_choice_cost(
                            commands[index : index + tail_length],
                            prefix_trace.final_state,
                            (node, edge),
                            tail_length,
                        )
                    expanded.append(SearchHypothesis(overrides=overrides, score=candidate_score, trace=next_trace))
            deduped: dict[tuple[int, str, int, str], SearchHypothesis] = {}
            for hypothesis in expanded:
                if hypothesis.trace is None:
                    continue
                signature = self._search_signature(index, hypothesis.trace)
                best = deduped.get(signature)
                if best is None or hypothesis.score < best.score:
                    deduped[signature] = hypothesis
            if not deduped:
                break
            hypotheses = sorted(deduped.values(), key=lambda hypothesis: hypothesis.score)[:beam_width]
        if not hypotheses:
            return self._execute_sequence(commands, initial_state, align_start=align_start, allow_lookahead=True)
        best = min(hypotheses, key=lambda hypothesis: hypothesis.score)
        return self._execute_sequence(
            commands,
            initial_state,
            align_start=align_start,
            allow_lookahead=False,
            override_choices=best.overrides,
        )

    def _search_budget_eligible(self, commands: list[NavigationCommand]) -> bool:
        searchable_turns = sum(1 for command in commands if command.primary_action == "turn")
        return searchable_turns >= 2 and len(commands) <= 10 and searchable_turns < 8

    def _windowed_search_budget_eligible(self, commands: list[NavigationCommand]) -> bool:
        searchable_turns = sum(1 for command in commands if command.primary_action == "turn")
        if searchable_turns < 2:
            return False
        if self._search_budget_eligible(commands):
            return False
        return len(commands) > 10 or searchable_turns >= 8

    def _execute_hybrid(
        self,
        commands: list[NavigationCommand],
        initial_state: ExecutionState,
        *,
        align_start: bool = True,
    ) -> ExecutionTrace:
        base_trace = self._execute_sequence(commands, initial_state, align_start=align_start, allow_lookahead=True)
        if self._search_budget_eligible(commands):
            search_trace = self._execute_search(commands, initial_state, align_start=align_start)
            if self._prefer_search_trace(commands, base_trace, search_trace):
                base_trace = search_trace
        elif self._windowed_search_budget_eligible(commands):
            windowed_trace = self._execute_windowed_search(commands, initial_state, align_start=align_start)
            if self._trace_selection_cost(commands, base_trace) - self._trace_selection_cost(commands, windowed_trace) > 1.0:
                if windowed_trace.step_diagnostics:
                    windowed_trace.step_diagnostics[0].notes.append("hybrid-windowed")
                base_trace = windowed_trace
        return base_trace

    def _execute_sequence(
        self,
        commands: list[NavigationCommand],
        initial_state: ExecutionState,
        align_start: bool = True,
        allow_lookahead: bool = True,
        override_choices: dict[int, tuple[Any, EdgeCandidate]] | None = None,
    ) -> ExecutionTrace:
        state = ExecutionState(
            current_coordinates=initial_state.current_coordinates,
            current_heading=initial_state.current_heading,
            current_street=initial_state.current_street,
        )
        if align_start and commands:
            state = align_state_to_street(self.graph, state, commands[0])
        initial = ExecutionState(
            current_coordinates=state.current_coordinates,
            current_heading=state.current_heading,
            current_street=state.current_street,
        )
        waypoints = [state.current_coordinates]
        traversed_edges: list[tuple[Any, Any, Any | None]] = []
        segment_coordinates: list[list[tuple[float, float]]] = []
        step_segments: list[list[int]] = []
        step_diagnostics: list[ExecutionStepDiagnostic] = []
        node_snap_threshold_m = 15.0
        short_instruction_heading_threshold_m = 15.0

        for index, command in enumerate(commands):
            action = command.primary_action
            step_kind = _command_step_kind(command)
            step_diagnostic = ExecutionStepDiagnostic(
                index=index,
                step_kind=step_kind,
                action=action,
                direction=command.primary_direction,
                raw_text=command.raw_text,
                desired_heading=state.current_heading,
                start_coordinates=state.current_coordinates,
                end_coordinates=state.current_coordinates,
            )
            if action == "arrive":
                step_segments.append([])
                step_diagnostics.append(step_diagnostic)
                break
            desired_heading = state.current_heading
            if command.primary_direction:
                try:
                    desired_heading = heading_for_instruction(state.current_heading, command.primary_direction)
                except ValueError:
                    desired_heading = state.current_heading
            step_diagnostic.desired_heading = desired_heading
            preferred_streets = _command_street_targets(command)
            prefer_current_street = _prefer_current_street_for_step(
                commands,
                index,
                command,
                step_kind,
                state.current_street,
            )
            command_segment_indexes: list[int] = []
            first_move_choice: tuple[Any, EdgeCandidate] | None = None
            first_move_diagnostic: ExecutionCandidateDiagnostic | None = None
            if action in {"head", "turn"}:
                recovered_choice: tuple[Any, EdgeCandidate] | None = None
                allows_named_recovery = bool(preferred_streets) and (
                    step_kind == "named_turn" or (action == "head" and index == 0)
                )
                if allows_named_recovery:
                    recovery_limit = _named_street_recovery_limit(command)
                    recovery_floor = 40.0
                    note_prefix = "named-street-recovery"
                    if action == "head":
                        recovery_limit = min(recovery_limit, 250.0)
                        recovery_floor = 25.0
                        note_prefix = "named-head-recovery"
                    street_distance = distance_to_named_street(self.graph, state.current_coordinates, preferred_streets)
                    if recovery_floor < street_distance <= recovery_limit:
                        recovered = find_named_street_candidate(
                            self.graph,
                            state.current_coordinates,
                            preferred_streets,
                            desired_heading,
                            max_distance_m=recovery_limit,
                        )
                        if recovered is not None:
                            edge, snapped, snapped_distance = recovered
                            recovery_segment = self._path_coordinates_between_points(state.current_coordinates, snapped)
                            if recovery_segment is not None:
                                segment_coordinates.append(recovery_segment)
                                command_segment_indexes.append(len(segment_coordinates) - 1)
                            state.current_coordinates = snapped
                            recovered_choice = (edge.source, edge)
                            step_diagnostic.notes.append(f"{note_prefix}:{snapped_distance:.1f}m")
                ranked_candidates = self._score_candidates(
                    state.current_coordinates,
                    desired_heading,
                    preferred_streets=preferred_streets,
                    current_street=state.current_street,
                    include_nearby=True,
                    nearby_limit=20 if step_kind == "named_turn" else 8,
                    nearby_distance_m=_nearby_candidate_distance(
                        point_distance_meters(
                            state.current_coordinates,
                            _node_coordinate(self.graph, nearest_node(self.graph, state.current_coordinates)),
                        ),
                        node_snap_threshold_m=node_snap_threshold_m,
                        preferred_streets=preferred_streets,
                        step_kind=step_kind,
                    ),
                    step_kind=step_kind,
                    continuity_heading=state.current_heading,
                    prefer_current_street=prefer_current_street,
                    maneuver_direction=command.primary_direction,
                    action=action,
                )
                step_diagnostic.candidate_diagnostics = [diagnostic for _, _, diagnostic in ranked_candidates[:4]]
                forced_choice = override_choices.get(index) if override_choices else None
                if forced_choice is not None:
                    node, edge = forced_choice
                    first_move_diagnostic = _diagnostic_for_choice(ranked_candidates, forced_choice)
                    step_diagnostic.notes.append("override-choice")
                elif recovered_choice is not None:
                    node, edge = recovered_choice
                    first_move_diagnostic = _diagnostic_for_choice(ranked_candidates, recovered_choice)
                else:
                    lookahead_choice = None
                    lookahead_note = "lookahead-choice"
                    named_street_continuation_choice = None
                    if allow_lookahead:
                        if step_kind == "named_turn":
                            lookahead_choice = self._choose_named_turn_lookahead_edge(
                                commands,
                                index,
                                state,
                                command,
                                ranked_candidates,
                            )
                            if lookahead_choice is None:
                                lookahead_choice = self._choose_named_turn_fallback_edge(
                                    commands,
                                    index,
                                    state,
                                    command,
                                    ranked_candidates,
                                )
                                if lookahead_choice is not None:
                                    lookahead_note = "named-turn-fallback"
                        elif step_kind == "anonymous_turn":
                            lookahead_choice = self._choose_anonymous_turn_rescue_edge(
                                commands,
                                index,
                                state,
                                command,
                                ranked_candidates,
                            )
                            if lookahead_choice is not None:
                                lookahead_note = "anonymous-turn-rescue"
                            else:
                                lookahead_choice = self._choose_anonymous_chain_lookahead_edge(
                                    commands,
                                    index,
                                    state,
                                    command,
                                    ranked_candidates,
                                )
                                if lookahead_choice is not None:
                                    lookahead_note = "anonymous-chain-lookahead"
                        elif step_kind == "continue":
                            lookahead_choice = self._choose_continue_lookahead_edge(
                                commands,
                                index,
                                state,
                                command,
                                ranked_candidates,
                            )
                            if lookahead_choice is not None:
                                lookahead_note = "continue-lookahead"
                        if lookahead_choice is None:
                            lookahead_choice = self._choose_lookahead_edge(
                                commands,
                                index,
                                state,
                                command,
                                desired_heading,
                                preferred_streets,
                                node_snap_threshold_m,
                            )
                    if lookahead_choice is None:
                        named_street_continuation_choice = self._choose_named_street_continuation_edge(
                            ranked_candidates,
                            preferred_streets=preferred_streets,
                            step_kind=step_kind,
                            remaining_distance=command.primary_distance,
                        )
                    if lookahead_choice is not None:
                        node, edge = lookahead_choice
                        first_move_diagnostic = _diagnostic_for_choice(ranked_candidates, lookahead_choice)
                        step_diagnostic.notes.append(lookahead_note)
                    elif named_street_continuation_choice is not None:
                        node, edge, first_move_diagnostic = named_street_continuation_choice
                        step_diagnostic.notes.append("named-street-continuation")
                    elif ranked_candidates:
                        node, edge, first_move_diagnostic = ranked_candidates[0]
                    else:
                        node, edge = self._default_action_edge(
                            state,
                            command,
                            desired_heading,
                            preferred_streets,
                            node_snap_threshold_m,
                        )
                node_coordinate = _node_coordinate(self.graph, node)
                if action == "turn":
                    state.current_coordinates = node_coordinate
                elif point_distance_meters(state.current_coordinates, node_coordinate) <= node_snap_threshold_m:
                    state.current_coordinates = node_coordinate
                state.current_heading = edge.bearing
                state.current_street = edge.name
                step_diagnostic.selected_street = edge.name
                step_diagnostic.selected_bearing = edge.bearing
                if first_move_diagnostic is not None:
                    step_diagnostic.selected_score = first_move_diagnostic.total_score
                first_move_choice = (node, edge)
                if waypoints[-1] != state.current_coordinates:
                    waypoints.append(state.current_coordinates)
            remaining = command.primary_distance
            if remaining <= 0:
                step_diagnostic.end_coordinates = state.current_coordinates
                step_segments.append(command_segment_indexes)
                step_diagnostic.segment_indexes = command_segment_indexes
                step_diagnostics.append(step_diagnostic)
                continue
            movement_heading = desired_heading if action == "continue" else state.current_heading
            while remaining > 0.5:
                selected_diagnostic: ExecutionCandidateDiagnostic | None = None
                if first_move_choice is not None:
                    node, edge = first_move_choice
                    first_move_choice = None
                    selected_diagnostic = first_move_diagnostic
                    first_move_diagnostic = None
                else:
                    nearest = nearest_node(self.graph, state.current_coordinates)
                    nearest_distance = point_distance_meters(state.current_coordinates, _node_coordinate(self.graph, nearest))
                    first_segment_for_command = not command_segment_indexes
                    ranked_move_candidates = self._score_candidates(
                        state.current_coordinates,
                        movement_heading,
                        preferred_streets=preferred_streets if preferred_streets else None,
                        current_street=state.current_street,
                        include_nearby=nearest_distance > node_snap_threshold_m or bool(preferred_streets),
                        nearby_distance_m=_nearby_candidate_distance(
                            nearest_distance,
                            node_snap_threshold_m=node_snap_threshold_m,
                            preferred_streets=preferred_streets,
                        ),
                        step_kind=step_kind,
                        continuity_heading=state.current_heading,
                        prefer_current_street=True,
                        maneuver_direction=command.primary_direction if first_segment_for_command else None,
                        action=action if first_segment_for_command else "continue",
                    )
                    if not ranked_move_candidates:
                        break
                    node, edge, selected_diagnostic = ranked_move_candidates[0]
                    retained_choice = self._choose_corridor_retention_edge(
                        ranked_move_candidates,
                        current_street=state.current_street,
                        preferred_streets=preferred_streets,
                        step_kind=step_kind,
                    )
                    if retained_choice is not None:
                        node, edge, selected_diagnostic = retained_choice
                        step_diagnostic.notes.append("corridor-retention")
                    named_street_continuation_choice = self._choose_named_street_continuation_edge(
                        ranked_move_candidates,
                        preferred_streets=preferred_streets,
                        step_kind=step_kind,
                        remaining_distance=remaining,
                    )
                    if named_street_continuation_choice is not None:
                        node, edge, selected_diagnostic = named_street_continuation_choice
                        step_diagnostic.notes.append("named-street-continuation")
                    if not step_diagnostic.candidate_diagnostics:
                        step_diagnostic.candidate_diagnostics = [diagnostic for _, _, diagnostic in ranked_move_candidates[:4]]
                        step_diagnostic.selected_street = edge.name
                        step_diagnostic.selected_bearing = edge.bearing
                        if selected_diagnostic is not None:
                            step_diagnostic.selected_score = selected_diagnostic.total_score
                    elif selected_diagnostic.street != step_diagnostic.selected_street:
                        step_diagnostic.notes.append(f"street-shift:{selected_diagnostic.street or '-'}")
                segment_line, moved = self._advance_along_edge(
                    state,
                    edge,
                    remaining,
                    command,
                    desired_heading,
                    preferred_streets,
                    short_instruction_heading_threshold_m,
                )
                traversed_edges.append((edge.source, edge.target, edge.key))
                if segment_line is not None:
                    segment_coordinates.append(segment_line)
                    command_segment_indexes.append(len(segment_coordinates) - 1)
                if waypoints[-1] != state.current_coordinates:
                    waypoints.append(state.current_coordinates)
                if moved <= 0.01:
                    break
                remaining -= moved
                movement_heading = state.current_heading
            step_diagnostic.end_coordinates = state.current_coordinates
            step_diagnostic.segment_indexes = command_segment_indexes
            step_segments.append(command_segment_indexes)
            step_diagnostics.append(step_diagnostic)

        return ExecutionTrace(
            initial_state=initial,
            final_state=state,
            waypoints=waypoints,
            traversed_edges=traversed_edges,
            segment_coordinates=segment_coordinates,
            step_segments=step_segments,
            step_diagnostics=step_diagnostics,
        )

    def execute(
        self,
        commands: list[NavigationCommand],
        initial_state: ExecutionState,
        align_start: bool = True,
        executor: str = "greedy",
    ) -> ExecutionTrace:
        if executor == "greedy":
            return self._execute_sequence(commands, initial_state, align_start=align_start, allow_lookahead=True)
        if executor == "search":
            return self._execute_search(commands, initial_state, align_start=align_start)
        if executor == "hybrid":
            return self._execute_hybrid(commands, initial_state, align_start=align_start)
        raise ValueError(f"Unsupported executor: {executor}")

    def _route_nodes_between_waypoints(self, waypoints: list[LatLon]) -> list[Any]:
        node_path: list[Any] = []
        for start, end in zip(waypoints, waypoints[1:]):
            source = nearest_node(self.graph, start)
            target = nearest_node(self.graph, end)
            if source == target:
                if not node_path or node_path[-1] != source:
                    node_path.append(source)
                continue
            try:
                segment = nx.shortest_path(self.graph, source, target, weight="length")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                segment = [source, target]
            if not node_path:
                node_path.extend(segment)
            else:
                node_path.extend(segment[1:])
        return node_path

    def trace_to_linestring(self, trace: ExecutionTrace) -> LineString:
        if trace.segment_coordinates:
            coordinates: list[tuple[float, float]] = []
            for segment in trace.segment_coordinates:
                if not coordinates:
                    coordinates.extend(segment)
                elif coordinates[-1] == segment[0]:
                    coordinates.extend(segment[1:])
                else:
                    coordinates.extend(segment)
            return LineString(coordinates)
        if len(trace.waypoints) < 2:
            point = trace.waypoints[0]
            return LineString([(point[1], point[0]), (point[1], point[0])])
        nodes = self._route_nodes_between_waypoints(trace.waypoints)
        if len(nodes) < 2:
            return LineString([(lon, lat) for lat, lon in trace.waypoints])
        coordinates: list[tuple[float, float]] = []
        for source, target in zip(nodes, nodes[1:]):
            edge_map = self.graph.get_edge_data(source, target)
            if edge_map is None and hasattr(self.graph, "get_edge_data"):
                coordinates.extend([(self.graph.nodes[source]["x"], self.graph.nodes[source]["y"]), (self.graph.nodes[target]["x"], self.graph.nodes[target]["y"])])
                continue
            key, data = _best_edge_data(edge_map)
            line = _oriented_line(self.graph, source, target, data)
            segment_coords = list(line.coords)
            if coordinates and coordinates[-1] == segment_coords[0]:
                coordinates.extend(segment_coords[1:])
            else:
                coordinates.extend(segment_coords)
        return LineString(coordinates)

    def trace_to_geojson(self, trace: ExecutionTrace) -> dict[str, Any]:
        line = self.trace_to_linestring(trace)
        return feature_collection_from_linestring(line, properties={"waypoints": len(trace.waypoints)})

    def write_trace_geojson(self, trace: ExecutionTrace, path: str | Path) -> None:
        save_geojson(path, self.trace_to_geojson(trace))

from __future__ import annotations

import json
import inspect
import logging
import re
import shutil
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from shapely.geometry import Point

from .difficulty import DIFFICULTY_DISTANCE_RANGES, classify_difficulty_v2

logger = logging.getLogger("path_builder.generation")


@dataclass(slots=True)
class RouteBucket:
    name: str
    need: int
    distance_range: tuple[float, float]
    routes: list[tuple[Any, Any, float]] = field(default_factory=list)
    routes_latlon: list[tuple[tuple[float, float], tuple[float, float], float]] = field(default_factory=list)
    pairs: set[tuple[Any, Any]] = field(default_factory=set)


def prepare_city_graph(city_name: str, network_type: str = "walk", buffer_m: int = 15_000):
    import geopandas as gpd
    import osmnx as ox

    logger.info("Preparing graph for %s", city_name)
    polygon = None
    graph = None

    try:
        gdf = ox.geocode_to_gdf(city_name)
        if len(gdf) > 0:
            geom = gdf.geometry.iloc[0]
            if geom.geom_type in {"Polygon", "MultiPolygon"}:
                polygon = geom
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("geocode_to_gdf failed for %s: %s", city_name, exc)

    if polygon is not None:
        try:
            graph = ox.graph_from_polygon(polygon, network_type=network_type, simplify=True)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.warning("graph_from_polygon failed for %s: %s", city_name, exc)

    if graph is None:
        try:
            graph = ox.graph_from_place(city_name, network_type=network_type, simplify=True)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.warning("graph_from_place failed for %s: %s", city_name, exc)

    if graph is None:
        lat, lon = ox.geocode(city_name)
        center = gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs="EPSG:4326")
        projected = ox.project_gdf(center)
        buffered = gpd.GeoSeries([projected.buffer(buffer_m).geometry.iloc[0]], crs=projected.crs).to_crs("EPSG:4326").iloc[0]
        graph = ox.graph_from_polygon(buffered, network_type=network_type, simplify=True)

    graph = ox.utils_graph.get_largest_component(graph, strongly=False)
    degree = dict(graph.degree())
    candidate_nodes = np.array([node for node, value in degree.items() if value >= 2], dtype=object)
    if len(candidate_nodes) == 0:
        raise RuntimeError("No degree>=2 nodes available for route generation.")
    nodes_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=False)
    node_index = list(graph.nodes())
    node_to_index = {node: index for index, node in enumerate(node_index)}
    node_xy = nodes_gdf[["x", "y"]].to_dict("index")
    return graph, nodes_gdf, candidate_nodes, node_index, node_to_index, node_xy


def build_adjacency(graph: nx.MultiDiGraph, node_index: list[Any], weight: str = "length"):
    from scipy.sparse import csr_matrix

    index = {node: position for position, node in enumerate(node_index)}
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for source, target, attributes in graph.edges(data=True):
        rows.append(index[source])
        cols.append(index[target])
        edge_weight = float(attributes.get(weight, 1.0) or 1.0)
        data.append(edge_weight if edge_weight > 0 else 1.0)
    return csr_matrix((data, (rows, cols)), shape=(len(node_index), len(node_index)), dtype=np.float64)


def _bucket_distance(distance: float, buckets: dict[str, RouteBucket]) -> list[str]:
    matched = []
    for name, bucket in buckets.items():
        lower, upper = bucket.distance_range
        if lower <= distance <= upper and len(bucket.routes) < bucket.need:
            matched.append(name)
    return matched


def _best_edge_length(graph: nx.MultiDiGraph, source: Any, target: Any) -> float:
    edge_map = graph.get_edge_data(source, target) or {}
    if not edge_map:
        return 0.0
    return min(float((data or {}).get("length", 0.0) or 0.0) for data in edge_map.values())


def _call_audit_example(audit_fn: Any, example: Any, **kwargs: Any):
    try:
        parameters = inspect.signature(audit_fn).parameters.values()
    except (TypeError, ValueError):
        return audit_fn(example, **kwargs)

    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return audit_fn(example, **kwargs)

    accepted_names = {
        parameter.name
        for parameter in parameters
        if parameter.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    filtered_kwargs = {name: value for name, value in kwargs.items() if name in accepted_names}
    return audit_fn(example, **filtered_kwargs)


def estimate_path_complexity(graph: nx.MultiDiGraph, node_path: list[Any]) -> dict[str, float]:
    if len(node_path) < 2:
        return {
            "turn_count": 0.0,
            "branch_density": 0.0,
            "short_segment_ratio": 0.0,
            "roundabout_count": 0.0,
            "complexity_score": 0.0,
        }
    turn_count = max(0, len(node_path) - 2)
    branch_density = 0.0
    short_segments = 0
    segment_count = max(0, len(node_path) - 1)
    roundabout_count = 0
    for source, target in zip(node_path, node_path[1:]):
        length = _best_edge_length(graph, source, target)
        if 0.0 < length <= 20.0:
            short_segments += 1
        branch_density += max(0, int(graph.degree(source)) - 2)
        for _, data in (graph.get_edge_data(source, target) or {}).items():
            if (data or {}).get("junction") == "roundabout":
                roundabout_count += 1
                break
    branch_density = branch_density / max(segment_count, 1)
    short_segment_ratio = short_segments / max(segment_count, 1)
    complexity_score = (
        min(turn_count / 4.0, 3.0)
        + min(branch_density, 2.5)
        + short_segment_ratio * 1.5
        + min(roundabout_count, 3) * 0.75
    )
    return {
        "turn_count": float(turn_count),
        "branch_density": float(branch_density),
        "short_segment_ratio": float(short_segment_ratio),
        "roundabout_count": float(roundabout_count),
        "complexity_score": float(complexity_score),
    }


def classify_path_difficulty_v2(
    distance: float,
    complexity_score: float,
    *,
    longest_anonymous_chain: int = 0,
    turn_count: int = 1,
    easy_range: tuple[float, float] = DIFFICULTY_DISTANCE_RANGES["easy"],
    medium_range: tuple[float, float] = DIFFICULTY_DISTANCE_RANGES["medium"],
    hard_range: tuple[float, float] = DIFFICULTY_DISTANCE_RANGES["hard"],
) -> str | None:
    if easy_range != DIFFICULTY_DISTANCE_RANGES["easy"] or medium_range != DIFFICULTY_DISTANCE_RANGES["medium"] or hard_range != DIFFICULTY_DISTANCE_RANGES["hard"]:
        if easy_range[0] <= distance <= easy_range[1]:
            if complexity_score <= 7.95 and longest_anonymous_chain <= 12 and turn_count >= 1:
                return "easy"
            return None
        if medium_range[0] <= distance <= medium_range[1]:
            if 5.0 <= complexity_score <= 8.05 and longest_anonymous_chain <= 16 and turn_count >= 1:
                return "medium"
            return None
        if hard_range[0] <= distance <= hard_range[1]:
            if complexity_score >= 5.0 and longest_anonymous_chain <= 24 and turn_count >= 1:
                return "hard"
            return None
        return None
    return classify_difficulty_v2(
        route_length_m=distance,
        complexity_score=complexity_score,
        longest_anonymous_chain=longest_anonymous_chain,
        turn_count=turn_count,
    )


def generate_routes_all_levels(
    city_name: str,
    num_easy: int,
    num_medium: int,
    num_hard: int,
    easy_range: tuple[float, float] = (500, 1200),
    medium_range: tuple[float, float] = (1200, 1800),
    hard_range: tuple[float, float] = (1800, 2500),
    network_type: str = "walk",
    seed: int = 42,
    max_endpoints_per_start: int = 8,
    max_start_attempts: int = 20_000,
) -> dict[str, RouteBucket]:
    graph, _, candidate_nodes, _, _, node_xy = prepare_city_graph(city_name, network_type=network_type)
    rng = np.random.default_rng(seed)
    buckets = {
        "easy": RouteBucket("easy", num_easy, easy_range),
        "medium": RouteBucket("medium", num_medium, medium_range),
        "hard": RouteBucket("hard", num_hard, hard_range),
    }
    pool = candidate_nodes.copy()
    rng.shuffle(pool)
    position = 0
    attempts = 0
    while any(len(bucket.routes) < bucket.need for bucket in buckets.values()):
        attempts += 1
        if attempts > max_start_attempts:
            raise RuntimeError("Unable to satisfy route buckets within max_start_attempts.")
        if position >= len(pool):
            rng.shuffle(pool)
            position = 0
        start_node = pool[position]
        position += 1
        try:
            distances = nx.single_source_dijkstra_path_length(graph, start_node, cutoff=hard_range[1], weight="length")
        except Exception as exc:  # pragma: no cover - graph edge case
            logger.warning("Skipping start node %s: %s", start_node, exc)
            continue
        endpoints = [(node, distance) for node, distance in distances.items() if node != start_node]
        rng.shuffle(endpoints)
        harvested = 0
        for end_node, distance in endpoints:
            for bucket_name in _bucket_distance(distance, buckets):
                bucket = buckets[bucket_name]
                pair = (start_node, end_node)
                if pair in bucket.pairs:
                    continue
                start_latlon = (node_xy[start_node]["y"], node_xy[start_node]["x"])
                end_latlon = (node_xy[end_node]["y"], node_xy[end_node]["x"])
                bucket.routes.append((start_node, end_node, float(distance)))
                bucket.routes_latlon.append((start_latlon, end_latlon, float(distance)))
                bucket.pairs.add(pair)
                harvested += 1
                break
            if harvested >= max_endpoints_per_start:
                break
    return buckets


def generate_routes_all_levels_v2(
    city_name: str,
    num_easy: int,
    num_medium: int,
    num_hard: int,
    easy_range: tuple[float, float] = (500, 1200),
    medium_range: tuple[float, float] = (1200, 1800),
    hard_range: tuple[float, float] = (1800, 2500),
    network_type: str = "walk",
    seed: int = 42,
    max_endpoints_per_start: int = 8,
    max_start_attempts: int = 20_000,
    return_graph: bool = False,
) -> dict[str, RouteBucket] | tuple[dict[str, RouteBucket], nx.MultiDiGraph]:
    prepared = prepare_city_graph(city_name, network_type=network_type)
    buckets = _generate_routes_all_levels_v2_from_prepared_graph(
        prepared[0],
        prepared[2],
        prepared[5],
        num_easy=num_easy,
        num_medium=num_medium,
        num_hard=num_hard,
        easy_range=easy_range,
        medium_range=medium_range,
        hard_range=hard_range,
        seed=seed,
        max_endpoints_per_start=max_endpoints_per_start,
        max_start_attempts=max_start_attempts,
    )
    if return_graph:
        return buckets, prepared[0]
    return buckets


def _generate_routes_all_levels_v2_from_prepared_graph(
    graph: nx.MultiDiGraph,
    candidate_nodes: np.ndarray,
    node_xy: dict[Any, dict[str, float]],
    *,
    num_easy: int,
    num_medium: int,
    num_hard: int,
    easy_range: tuple[float, float],
    medium_range: tuple[float, float],
    hard_range: tuple[float, float],
    seed: int,
    max_endpoints_per_start: int,
    max_start_attempts: int,
) -> dict[str, RouteBucket]:
    rng = np.random.default_rng(seed)
    buckets = {
        "easy": RouteBucket("easy", num_easy, easy_range),
        "medium": RouteBucket("medium", num_medium, medium_range),
        "hard": RouteBucket("hard", num_hard, hard_range),
    }
    pool = candidate_nodes.copy()
    rng.shuffle(pool)
    position = 0
    attempts = 0
    while any(len(bucket.routes) < bucket.need for bucket in buckets.values()):
        attempts += 1
        if attempts > max_start_attempts:
            raise RuntimeError("Unable to satisfy route buckets within max_start_attempts.")
        if position >= len(pool):
            rng.shuffle(pool)
            position = 0
        start_node = pool[position]
        position += 1
        try:
            distances, paths = nx.single_source_dijkstra(graph, start_node, cutoff=hard_range[1], weight="length")
        except Exception as exc:  # pragma: no cover - graph edge case
            logger.warning("Skipping start node %s: %s", start_node, exc)
            continue
        endpoints = [(node, float(distance), paths[node]) for node, distance in distances.items() if node != start_node]
        rng.shuffle(endpoints)
        harvested = 0
        for end_node, distance, node_path in endpoints:
            complexity = estimate_path_complexity(graph, list(node_path))
            bucket_name = classify_path_difficulty_v2(
                distance,
                complexity["complexity_score"],
                longest_anonymous_chain=max(0, len(node_path) - 2),
                turn_count=max(0, len(node_path) - 2),
                easy_range=easy_range,
                medium_range=medium_range,
                hard_range=hard_range,
            )
            if bucket_name is None:
                continue
            bucket = buckets[bucket_name]
            if len(bucket.routes) >= bucket.need:
                continue
            pair = (start_node, end_node)
            if pair in bucket.pairs:
                continue
            start_latlon = (node_xy[start_node]["y"], node_xy[start_node]["x"])
            end_latlon = (node_xy[end_node]["y"], node_xy[end_node]["x"])
            bucket.routes.append((start_node, end_node, distance))
            bucket.routes_latlon.append((start_latlon, end_latlon, distance))
            bucket.pairs.add(pair)
            harvested += 1
            if harvested >= max_endpoints_per_start:
                break
    return buckets


def _safe_city_dirname(city_name: str) -> str:
    collapsed = re.sub(r"\s+", "_", city_name.strip())
    collapsed = collapsed.replace(",", "")
    collapsed = collapsed.replace("/", "_")
    collapsed = re.sub(r"[^A-Za-z0-9_.-]", "_", collapsed)
    return collapsed or "city"


def _next_route_id(bucket_root: Path) -> int:
    existing = [int(path.name) for path in bucket_root.iterdir() if path.is_dir() and path.name.isdigit()]
    return max(existing, default=-1) + 1


def _ors_profile_for_network_type(network_type: str) -> str:
    value = network_type.strip().lower()
    if value in {"walk", "walking", "foot", "foot-walking"}:
        return "foot-walking"
    if value in {"bike", "bicycle", "cycle", "cycling", "cycling-regular"}:
        return "cycling-regular"
    if value in {"drive", "driving", "car", "driving-car"}:
        return "driving-car"
    return "foot-walking"


def _is_valid_route_geojson_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        return False
    first = features[0]
    if not isinstance(first, dict):
        return False
    geometry = first.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return False
    coordinates = geometry.get("coordinates")
    return isinstance(coordinates, list) and len(coordinates) >= 2


def _write_route_folder_payload(payload: dict[str, Any], route_dir: Path) -> None:
    from .instructions import (
        format_ors_steps_as_instruction_lines,
        format_ors_steps_as_natural_lines,
        parse_instruction_lines,
        write_parsed_instructions,
    )
    from .io import save_geojson

    route_dir.mkdir(parents=True, exist_ok=True)
    save_geojson(route_dir / "route.geojson", payload)
    instruction_lines = format_ors_steps_as_instruction_lines(payload)
    natural_lines = format_ors_steps_as_natural_lines(payload)
    if not natural_lines:
        natural_lines = instruction_lines
    (route_dir / "instructions.txt").write_text("\n".join(instruction_lines) + ("\n" if instruction_lines else ""), encoding="utf-8")
    (route_dir / "natural_instructions.txt").write_text("\n".join(natural_lines) + ("\n" if natural_lines else ""), encoding="utf-8")
    commands = parse_instruction_lines(natural_lines)
    write_parsed_instructions(route_dir / "instructions_parse.txt", commands)


def _build_ors_client(
    ors_api_key: str,
    network_type: str,
    ors_client_factory: Any,
):
    profile = _ors_profile_for_network_type(network_type)
    if ors_client_factory is not None:
        try:
            return ors_client_factory(ors_api_key, profile)
        except TypeError:
            return ors_client_factory(ors_api_key)
    from .directions import ORSClient

    return ORSClient(api_key=ors_api_key, profile=profile)


def _sample_probe_routes(
    routes: list[tuple[tuple[float, float], tuple[float, float], float]],
    sample_size: int,
) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
    if sample_size <= 0 or not routes:
        return []
    if sample_size >= len(routes):
        return list(routes)
    if sample_size == 1:
        return [routes[len(routes) // 2]]
    step = (len(routes) - 1) / float(sample_size - 1)
    indexes = sorted({int(round(position * step)) for position in range(sample_size)})
    return [routes[index] for index in indexes]


def _run_city_attempt(
    city_name: str,
    requested_counts: dict[str, int],
    *,
    stage_city_dir: Path,
    ors_api_key: str,
    network_type: str,
    seed: int,
    oversample_factor: int,
    max_endpoints_per_start: int,
    max_start_attempts: int,
    paper_valid_gate: float,
    probe_sample_size: int,
    require_pb_recoverable: bool,
    pb_executor: str,
    ors_client_factory: Any = None,
) -> tuple[dict[str, Any], dict[str, list[tuple[Path, Any]]]]:
    from .datasets import load_route_example
    from .paper import audit_example
    from .execution import PathBuilder

    targets = {
        "easy": max(0, requested_counts.get("easy", 0)),
        "medium": max(0, requested_counts.get("medium", 0)),
        "hard": max(0, requested_counts.get("hard", 0)),
    }
    sampled_targets = {name: (count * oversample_factor if count > 0 else 0) for name, count in targets.items()}
    attempt_summary: dict[str, Any] = {
        "city": city_name,
        "requested_counts": dict(targets),
        "sampled_targets": dict(sampled_targets),
        "candidate_counts": {"easy": 0, "medium": 0, "hard": 0},
        "probe_total": 0,
        "probe_paper_valid": 0,
        "probe_pb_recoverable": 0,
        "probe_rate": 0.0,
        "processed_count": 0,
        "paper_valid_count": 0,
        "pb_recoverable_count": 0,
        "paper_valid_rate": 0.0,
        "pb_recoverable_rate": 0.0,
        "accepted_counts": {"easy": 0, "medium": 0, "hard": 0},
        "rejected_reasons": {},
        "gate_metric": "pb_recoverable_rate" if require_pb_recoverable else "paper_valid_rate",
        "quotas_met": False,
        "gate_met": False,
        "success": False,
        "failure_reason": None,
    }
    accepted_by_difficulty: dict[str, list[tuple[Path, Any]]] = {"easy": [], "medium": [], "hard": []}
    try:
        generated = generate_routes_all_levels_v2(
            city_name,
            sampled_targets["easy"],
            sampled_targets["medium"],
            sampled_targets["hard"],
            network_type=network_type,
            seed=seed,
            max_endpoints_per_start=max_endpoints_per_start,
            max_start_attempts=max_start_attempts,
            return_graph=require_pb_recoverable,
        )
    except RuntimeError as exc:
        attempt_summary["failure_reason"] = f"candidate_generation_failed:{exc}"
        return attempt_summary, accepted_by_difficulty
    if isinstance(generated, tuple):
        buckets, candidate_graph = generated
    else:
        buckets, candidate_graph = generated, None
    city_builder = PathBuilder(candidate_graph) if require_pb_recoverable and candidate_graph is not None else None

    candidate_counts = {name: len(bucket.routes_latlon) for name, bucket in buckets.items()}
    attempt_summary["candidate_counts"] = candidate_counts
    missing_candidates = [
        name for name, count in targets.items() if count > 0 and candidate_counts.get(name, 0) <= 0
    ]
    if missing_candidates:
        attempt_summary["failure_reason"] = "missing_candidate_pairs"
        attempt_summary["missing_difficulties"] = missing_candidates
        return attempt_summary, accepted_by_difficulty

    client = _build_ors_client(ors_api_key, network_type, ors_client_factory)
    rejected_reasons: Counter[str] = Counter()
    probe_total = 0
    probe_paper_valid = 0
    probe_pb_recoverable = 0
    probe_dir = stage_city_dir / "_probe"
    for difficulty_name in ("easy", "medium", "hard"):
        need = targets[difficulty_name]
        if need <= 0:
            continue
        sample_size = min(
            candidate_counts.get(difficulty_name, 0),
            max(2, min(probe_sample_size, need * 2)),
        )
        sampled = _sample_probe_routes(buckets[difficulty_name].routes_latlon, sample_size)
        if not sampled:
            continue
        probe_results = client.batch_directions(sampled)
        for index, payload in enumerate(probe_results):
            probe_total += 1
            if not _is_valid_route_geojson_payload(payload):
                rejected_reasons["probe_ors_error"] += 1
                continue
            probe_route_dir = probe_dir / difficulty_name / str(index)
            _write_route_folder_payload(payload, probe_route_dir)
            example = load_route_example(
                probe_route_dir,
                corpus="36kroutes",
                city=city_name,
                difficulty=difficulty_name,
            )
            record = _call_audit_example(
                audit_example,
                example,
                pb_check=require_pb_recoverable,
                builder=city_builder,
                executor=pb_executor,
            )
            accepted = record.paper_valid and record.difficulty_v2 == difficulty_name
            if accepted and require_pb_recoverable:
                accepted = record.pb_recoverable is True
            if record.paper_valid and record.difficulty_v2 == difficulty_name:
                probe_paper_valid += 1
            if record.pb_recoverable is True:
                probe_pb_recoverable += 1
            if not accepted:
                for reason in (record.invalid_reasons or ["probe_audit_rejected"]):
                    rejected_reasons[f"probe:{reason}"] += 1
                if require_pb_recoverable:
                    for reason in (record.recoverability_reasons or ["probe_pb_unrecoverable"]):
                        rejected_reasons[f"probe:{reason}"] += 1
            shutil.rmtree(probe_route_dir, ignore_errors=True)
    probe_rate_numerator = probe_pb_recoverable if require_pb_recoverable else probe_paper_valid
    probe_rate = probe_rate_numerator / probe_total if probe_total else 0.0
    attempt_summary["probe_total"] = probe_total
    attempt_summary["probe_paper_valid"] = probe_paper_valid
    attempt_summary["probe_pb_recoverable"] = probe_pb_recoverable
    attempt_summary["probe_rate"] = probe_rate
    if probe_total > 0 and probe_rate < paper_valid_gate:
        attempt_summary["failure_reason"] = "probe_rate_below_gate"
        attempt_summary["rejected_reasons"] = dict(sorted(rejected_reasons.items()))
        return attempt_summary, accepted_by_difficulty

    processed_count = 0
    paper_valid_count = 0
    pb_recoverable_count = 0
    for difficulty_name in ("easy", "medium", "hard"):
        need = targets[difficulty_name]
        if need <= 0:
            continue
        candidates = buckets[difficulty_name].routes_latlon
        chunk_size = 24
        for chunk_start in range(0, len(candidates), chunk_size):
            if len(accepted_by_difficulty[difficulty_name]) >= need:
                break
            chunk = candidates[chunk_start : chunk_start + chunk_size]
            results = client.batch_directions(chunk)
            for local_index, payload in enumerate(results):
                if len(accepted_by_difficulty[difficulty_name]) >= need:
                    break
                processed_count += 1
                if not _is_valid_route_geojson_payload(payload):
                    rejected_reasons["ors_error"] += 1
                    continue
                route_index = chunk_start + local_index
                route_dir = stage_city_dir / difficulty_name / f"candidate_{route_index}"
                _write_route_folder_payload(payload, route_dir)
                example = load_route_example(
                    route_dir,
                    corpus="36kroutes",
                    city=city_name,
                    difficulty=difficulty_name,
                )
                record = _call_audit_example(
                    audit_example,
                    example,
                    pb_check=require_pb_recoverable,
                    builder=city_builder,
                    executor=pb_executor,
                )
                paper_valid_and_matched = record.paper_valid and record.difficulty_v2 == difficulty_name
                if paper_valid_and_matched:
                    paper_valid_count += 1
                if record.pb_recoverable is True:
                    pb_recoverable_count += 1
                accepted = paper_valid_and_matched
                if accepted and require_pb_recoverable:
                    accepted = record.pb_recoverable is True
                if accepted:
                    accepted_by_difficulty[difficulty_name].append((route_dir, record))
                else:
                    for reason in (record.invalid_reasons or ["audit_rejected"]):
                        rejected_reasons[reason] += 1
                    if require_pb_recoverable:
                        for reason in (record.recoverability_reasons or ["pb_unrecoverable"]):
                            rejected_reasons[reason] += 1
                    shutil.rmtree(route_dir, ignore_errors=True)
    accepted_counts = {name: len(accepted_by_difficulty[name]) for name in ("easy", "medium", "hard")}
    quotas_met = all(
        accepted_counts[name] >= targets[name] for name in ("easy", "medium", "hard") if targets[name] > 0
    )
    paper_valid_rate = paper_valid_count / processed_count if processed_count else 0.0
    pb_recoverable_rate = pb_recoverable_count / processed_count if processed_count else 0.0
    quality_rate = pb_recoverable_rate if require_pb_recoverable else paper_valid_rate
    gate_met = quality_rate >= paper_valid_gate if processed_count else False
    attempt_summary.update(
        {
            "processed_count": processed_count,
            "paper_valid_count": paper_valid_count,
            "paper_valid_rate": paper_valid_rate,
            "pb_recoverable_count": pb_recoverable_count,
            "pb_recoverable_rate": pb_recoverable_rate,
            "accepted_counts": accepted_counts,
            "rejected_reasons": dict(sorted(rejected_reasons.items())),
            "quotas_met": quotas_met,
            "gate_met": gate_met,
            "success": quotas_met and gate_met,
            "failure_reason": None if quotas_met and gate_met else "quota_or_gate_not_met",
        }
    )
    return attempt_summary, accepted_by_difficulty


def generate_routes_pipeline(
    cities: list[str],
    *,
    num_easy: int,
    num_medium: int,
    num_hard: int,
    output_root: str | Path,
    ors_api_key: str,
    network_type: str = "walk",
    seed: int = 42,
    paper_valid_gate: float = 0.90,
    max_graph_repulls: int = 3,
    oversample_factor: int = 4,
    max_endpoints_per_start: int = 8,
    max_start_attempts: int = 20_000,
    probe_sample_size: int = 8,
    require_pb_recoverable: bool = True,
    pb_executor: str = "hybrid",
    progress: bool = False,
    ors_client_factory: Any = None,
) -> dict[str, Any]:
    from .paper import write_route_audit_manifest

    if not cities:
        raise ValueError("generate_routes_pipeline requires at least one city.")
    if not ors_api_key:
        raise ValueError("generate_routes_pipeline requires an ORS API key.")
    requested_total = max(0, int(num_easy)) + max(0, int(num_medium)) + max(0, int(num_hard))
    if requested_total <= 0:
        raise ValueError("At least one of num_easy/num_medium/num_hard must be > 0.")
    output_root_path = Path(output_root)
    output_root_path.mkdir(parents=True, exist_ok=True)
    stage_root = output_root_path / ".generation_staging"
    stage_root.mkdir(parents=True, exist_ok=True)

    city_reports: list[dict[str, Any]] = []
    generated_records: list[Any] = []
    total_accepted = 0
    for city_index, city_name in enumerate(cities):
        city_folder = _safe_city_dirname(city_name)
        requested_counts = {
            "easy": max(0, int(num_easy)),
            "medium": max(0, int(num_medium)),
            "hard": max(0, int(num_hard)),
        }
        attempts: list[dict[str, Any]] = []
        city_success = False
        generated_examples: list[dict[str, Any]] = []
        final_accepted_counts = {"easy": 0, "medium": 0, "hard": 0}
        city_stage = stage_root / city_folder
        city_stage.mkdir(parents=True, exist_ok=True)

        for attempt_index in range(max_graph_repulls + 1):
            attempt_seed = int(seed) + city_index * 1000 + attempt_index * 37
            attempt_stage = city_stage / f"attempt_{attempt_index}"
            if attempt_stage.exists():
                shutil.rmtree(attempt_stage, ignore_errors=True)
            attempt_stage.mkdir(parents=True, exist_ok=True)
            if progress:
                logger.info(
                    "generate-routes city=%s attempt=%s/%s",
                    city_name,
                    attempt_index + 1,
                    max_graph_repulls + 1,
                )
            attempt_summary, accepted_map = _run_city_attempt(
                city_name,
                requested_counts,
                stage_city_dir=attempt_stage,
                ors_api_key=ors_api_key,
                network_type=network_type,
                seed=attempt_seed,
                oversample_factor=max(1, int(oversample_factor)),
                max_endpoints_per_start=max(1, int(max_endpoints_per_start)),
                max_start_attempts=max(1, int(max_start_attempts)),
                paper_valid_gate=float(paper_valid_gate),
                probe_sample_size=max(1, int(probe_sample_size)),
                require_pb_recoverable=bool(require_pb_recoverable),
                pb_executor=pb_executor,
                ors_client_factory=ors_client_factory,
            )
            attempt_summary["attempt_index"] = attempt_index
            attempt_summary["seed"] = attempt_seed
            attempts.append(attempt_summary)
            if not attempt_summary.get("success", False):
                shutil.rmtree(attempt_stage, ignore_errors=True)
                continue

            city_success = True
            for difficulty_name in ("easy", "medium", "hard"):
                target_bucket = output_root_path / city_folder / difficulty_name
                target_bucket.mkdir(parents=True, exist_ok=True)
                next_id = _next_route_id(target_bucket)
                for route_dir, record in accepted_map[difficulty_name]:
                    target_dir = target_bucket / str(next_id)
                    shutil.move(str(route_dir), target_dir)
                    generated_records.append(record)
                    record_payload = asdict(record)
                    record_payload["output_dir"] = str(target_dir.relative_to(output_root_path))
                    generated_examples.append(record_payload)
                    next_id += 1
                final_accepted_counts[difficulty_name] = len(accepted_map[difficulty_name])
            total_accepted += sum(final_accepted_counts.values())
            shutil.rmtree(attempt_stage, ignore_errors=True)
            break

        shutil.rmtree(city_stage, ignore_errors=True)
        city_reports.append(
            {
                "city": city_name,
                "city_dir": city_folder,
                "success": city_success,
                "requested_counts": requested_counts,
                "accepted_counts": final_accepted_counts,
                "attempts": attempts,
                "generated_examples": generated_examples,
            }
        )

    shutil.rmtree(stage_root, ignore_errors=True)
    all_success = all(report["success"] for report in city_reports)
    payload = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "cities": cities,
            "num_easy": int(num_easy),
            "num_medium": int(num_medium),
            "num_hard": int(num_hard),
            "network_type": network_type,
            "seed": int(seed),
            "paper_valid_gate": float(paper_valid_gate),
            "max_graph_repulls": int(max_graph_repulls),
            "oversample_factor": int(oversample_factor),
            "max_endpoints_per_start": int(max_endpoints_per_start),
            "max_start_attempts": int(max_start_attempts),
            "probe_sample_size": int(probe_sample_size),
            "require_pb_recoverable": bool(require_pb_recoverable),
            "pb_executor": pb_executor,
        },
        "cities": city_reports,
        "overall": {
            "all_cities_success": all_success,
            "requested_total": requested_total * len(cities),
            "accepted_total": total_accepted,
        },
    }
    manifest_path = output_root_path / "generation_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    audit_manifest_path = output_root_path / "route_audit_manifest.json"
    write_route_audit_manifest(generated_records, audit_manifest_path)
    payload["manifest_path"] = str(manifest_path)
    payload["audit_manifest_path"] = str(audit_manifest_path)
    return payload

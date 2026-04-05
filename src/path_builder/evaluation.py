from __future__ import annotations

import csv
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
from pathlib import Path
from statistics import mean, median
from typing import Iterable, Sequence

import networkx as nx

from .datasets import (
    get_start_end_points,
    iter_corpus_examples,
    list_example_ids,
    load_example,
    load_parsed_instructions,
    load_reference_route,
)
from .execution import PathBuilder, recommended_graph_dist
from .graphs import GraphSnapshotStore, SharedGraphCache
from .io import load_geojson
from .models import CorpusEvaluationRow, CorpusEvaluationSummary, DatasetExample, ExecutionState, SimilarityThresholds, SimilarityWeights
from .paper import build_success_summary, filter_examples_by_manifest, load_route_audit_manifest
from .similarity import score_geojson_routes
from .visualization import plot_route_pair

EvaluationRow = CorpusEvaluationRow


def _basic_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "mean_similarity": mean(values) if values else 0.0,
        "median_similarity": median(values) if values else 0.0,
        "min_similarity": min(values) if values else 0.0,
        "max_similarity": max(values) if values else 0.0,
    }


def dataset_bounds(
    root: str | Path = "data_set",
    example_ids: Sequence[str] | None = None,
) -> tuple[float, float, float, float]:
    west, south = 999.0, 999.0
    east, north = -999.0, -999.0
    selected_ids = example_ids or list_example_ids(root)
    for example_id in selected_ids:
        route_geojson = load_geojson(Path(root) / example_id / "route.geojson")
        start, end = get_start_end_points(route_geojson)
        for point in (start, end):
            if point is None:
                continue
            lon, lat = point
            west = min(west, lon)
            south = min(south, lat)
            east = max(east, lon)
            north = max(north, lat)
    return west, south, east, north


def corpus_bounds(examples: Sequence[DatasetExample]) -> tuple[float, float, float, float]:
    west, south = 999.0, 999.0
    east, north = -999.0, -999.0
    for example in examples:
        route_geojson = load_reference_route(example)
        start, end = get_start_end_points(route_geojson)
        for point in (start, end):
            if point is None:
                continue
            lon, lat = point
            west = min(west, lon)
            south = min(south, lat)
            east = max(east, lon)
            north = max(north, lat)
    return west, south, east, north


def build_shared_graph(
    root: str | Path = "data_set",
    example_ids: Sequence[str] | None = None,
    padding_degrees: float = 0.01,
    network_type: str = "walk",
) -> PathBuilder:
    examples = [load_example(example_id, root=root) for example_id in (example_ids or list_example_ids(root))]
    return build_shared_graph_for_examples(examples, padding_degrees=padding_degrees, network_type=network_type)


def build_shared_graph_for_examples(
    examples: Sequence[DatasetExample],
    padding_degrees: float = 0.01,
    network_type: str = "walk",
) -> PathBuilder:
    import osmnx as ox
    from shapely.geometry import box

    ox.settings.use_cache = True
    ox.settings.log_console = False
    west, south, east, north = corpus_bounds(examples)
    polygon = box(west - padding_degrees, south - padding_degrees, east + padding_degrees, north + padding_degrees)
    graph = ox.graph_from_polygon(polygon, network_type=network_type, simplify=True)
    return PathBuilder(graph)


def _difficulty_scope_token(difficulties: Iterable[str] | None) -> str:
    values = sorted({str(item) for item in difficulties or [] if item})
    return "+".join(values) if values else "__all__"


def _shared_graph_cache_key(
    corpus: str,
    *,
    city: str | None,
    difficulties: Iterable[str] | None,
    network_type: str,
) -> str:
    city_token = city or "__global__"
    difficulty_token = _difficulty_scope_token(difficulties)
    return f"{corpus}/{city_token}/{difficulty_token}/{network_type}"


def _selection_graph_cache_key(
    examples: Sequence[DatasetExample],
    *,
    network_type: str,
) -> str:
    labels = "|".join(sorted(example.label for example in examples))
    digest = hashlib.sha1(labels.encode("utf-8")).hexdigest()[:12]
    return f"{examples[0].corpus}/__selection__/{digest}/{network_type}"


def shared_graph_cache_keys_for_examples(
    corpus: str,
    *,
    selected_examples: Sequence[DatasetExample],
    difficulties: Iterable[str] | None = None,
    network_type: str = "walk",
) -> dict[str, str]:
    if not selected_examples:
        return {}
    grouped_cities = sorted({example.city for example in selected_examples if example.city})
    if grouped_cities:
        return {
            city: _shared_graph_cache_key(
                corpus,
                city=city,
                difficulties=difficulties,
                network_type=network_type,
            )
            for city in grouped_cities
        }
    return {"__global__": _selection_graph_cache_key(selected_examples, network_type=network_type)}


def _annotate_shared_builder(builder: PathBuilder, *, cache_key: str | None, graph_source: str) -> PathBuilder:
    builder.graph.graph["shared_graph_cache_key"] = cache_key
    builder.graph.graph["shared_graph_source"] = graph_source
    return builder


def build_or_load_shared_graph_for_examples(
    examples: Sequence[DatasetExample],
    *,
    cache_dir: str | Path | None = None,
    cache_key: str | None = None,
    padding_degrees: float = 0.01,
    network_type: str = "walk",
    progress: bool = False,
) -> PathBuilder:
    if not examples:
        raise ValueError("build_or_load_shared_graph_for_examples requires at least one example.")
    cache = SharedGraphCache(cache_dir) if cache_dir and cache_key else None
    if cache is not None:
        cached_builder = cache.load_builder(cache_key)
        if cached_builder is not None:
            if progress:
                print(f"Loaded shared graph cache {cache_key}", flush=True)
            return _annotate_shared_builder(
                cached_builder,
                cache_key=cache_key,
                graph_source=str(cached_builder.graph.graph.get("shared_graph_source", "shared-cache")),
            )
    if cache_dir:
        snapshot_store = GraphSnapshotStore(cache_dir)
        snapshot_graphs: list[nx.Graph] = []
        missing_snapshot = False
        for example in examples:
            snapshot_builder = snapshot_store.load_builder(example)
            if snapshot_builder is None:
                missing_snapshot = True
                break
            snapshot_graphs.append(snapshot_builder.graph)
        if snapshot_graphs and not missing_snapshot:
            if progress:
                print(f"Building shared graph {cache_key or 'transient'} from {len(snapshot_graphs)} frozen route snapshots...", flush=True)
            merged = nx.compose_all(snapshot_graphs)
            builder = _annotate_shared_builder(PathBuilder(merged), cache_key=cache_key, graph_source="frozen-merged")
            if cache is not None:
                cache.store_graph(
                    cache_key,
                    builder.graph,
                    corpus=examples[0].corpus,
                    graph_source="frozen-merged",
                    city=examples[0].city if len({example.city for example in examples}) == 1 else None,
                    difficulties=sorted({example.difficulty for example in examples if example.difficulty}),
                    network_type=network_type,
                    example_count=len(examples),
                    padding_degrees=padding_degrees,
                )
            return builder
    if progress:
        print(f"Building shared graph {cache_key or 'transient'} from {len(examples)} routes...", flush=True)
    builder = _annotate_shared_builder(
        build_shared_graph_for_examples(examples, padding_degrees=padding_degrees, network_type=network_type),
        cache_key=cache_key,
        graph_source="live-osm",
    )
    if cache is not None:
        cache.store_graph(
            cache_key,
            builder.graph,
            corpus=examples[0].corpus,
            graph_source="live-osm",
            city=examples[0].city if len({example.city for example in examples}) == 1 else None,
            difficulties=sorted({example.difficulty for example in examples if example.difficulty}),
            network_type=network_type,
            example_count=len(examples),
            padding_degrees=padding_degrees,
        )
    return builder


def build_shared_graph_bundle(
    corpus: str,
    *,
    root: str | Path,
    selected_examples: Sequence[DatasetExample],
    cities: Iterable[str] | None = None,
    difficulties: Iterable[str] | None = None,
    cache_dir: str | Path | None = None,
    padding_degrees: float = 0.01,
    network_type: str = "walk",
    progress: bool = False,
) -> PathBuilder | dict[str, PathBuilder] | None:
    if not selected_examples:
        return None

    cache_keys = shared_graph_cache_keys_for_examples(
        corpus,
        selected_examples=selected_examples,
        difficulties=difficulties,
        network_type=network_type,
    )
    grouped_cities = sorted({example.city for example in selected_examples if example.city})
    if grouped_cities:
        builders: dict[str, PathBuilder] = {}
        for city in grouped_cities:
            scope_examples = iter_corpus_examples(corpus, root=root, cities=[city], difficulties=difficulties)
            builders[city] = build_or_load_shared_graph_for_examples(
                scope_examples,
                cache_dir=cache_dir,
                cache_key=cache_keys[city],
                padding_degrees=padding_degrees,
                network_type=network_type,
                progress=progress,
            )
        return builders

    scope_examples = list(selected_examples)
    return build_or_load_shared_graph_for_examples(
        scope_examples,
        cache_dir=cache_dir,
        cache_key=cache_keys["__global__"],
        padding_degrees=padding_degrees,
        network_type=network_type,
        progress=progress,
    )


def load_shared_graph_cache_metadata(
    cache_dir: str | Path | None,
    cache_keys: dict[str, str],
) -> dict[str, dict[str, str]]:
    if not cache_dir or not cache_keys:
        return {}
    cache = SharedGraphCache(cache_dir)
    metadata: dict[str, dict[str, str]] = {}
    for scope, cache_key in cache_keys.items():
        manifest = cache.load_manifest(cache_key) or {}
        metadata[scope] = {
            "cache_key": cache_key,
            "graph_source": str(manifest.get("graph_source", "shared-cache")),
        }
    return metadata


def _builder_for_example(
    builder: PathBuilder | dict[str, PathBuilder] | None,
    example: DatasetExample,
) -> PathBuilder | None:
    if isinstance(builder, dict):
        if example.city and example.city in builder:
            return builder[example.city]
        return builder.get("__global__")
    return builder


def _summary_for_rows(rows: list[CorpusEvaluationRow], *, success_threshold: float = 85.0) -> dict[str, float | int]:
    summary = _basic_summary([row.similarity for row in rows])
    summary.update(build_success_summary(rows, success_threshold=success_threshold))
    return summary


def build_corpus_summary(rows: list[CorpusEvaluationRow], *, success_threshold: float = 85.0) -> CorpusEvaluationSummary:
    by_city: dict[str, list[CorpusEvaluationRow]] = {}
    by_difficulty: dict[str, list[CorpusEvaluationRow]] = {}
    by_city_difficulty: dict[str, list[CorpusEvaluationRow]] = {}
    for row in rows:
        if row.city:
            by_city.setdefault(row.city, []).append(row)
        if row.difficulty:
            by_difficulty.setdefault(row.difficulty, []).append(row)
        if row.city and row.difficulty:
            by_city_difficulty.setdefault(f"{row.city}/{row.difficulty}", []).append(row)
    return CorpusEvaluationSummary(
        overall=_summary_for_rows(rows, success_threshold=success_threshold),
        by_city={key: _summary_for_rows(value, success_threshold=success_threshold) for key, value in sorted(by_city.items())},
        by_difficulty={key: _summary_for_rows(value, success_threshold=success_threshold) for key, value in sorted(by_difficulty.items())},
        by_city_difficulty={key: _summary_for_rows(value, success_threshold=success_threshold) for key, value in sorted(by_city_difficulty.items())},
    )


def summarize_rows(rows: list[CorpusEvaluationRow], *, success_threshold: float = 85.0) -> dict[str, float | int]:
    return _summary_for_rows(rows, success_threshold=success_threshold)


def _artifact_name(example: DatasetExample) -> str:
    if example.corpus == "36kroutes":
        return f"{example.city}__{example.difficulty}__{example.example_id}"
    return example.example_id


def _shared_cache_key_for_example(shared_cache_keys: dict[str, str] | None, example: DatasetExample) -> str | None:
    if not shared_cache_keys:
        return None
    if example.city and example.city in shared_cache_keys:
        return shared_cache_keys[example.city]
    return shared_cache_keys.get("__global__")


def _evaluate_example_worker(payload: dict[str, object]) -> CorpusEvaluationRow:
    example = payload["example"]
    if not isinstance(example, DatasetExample):
        raise TypeError("evaluate worker requires a DatasetExample payload.")
    if example.start is None:
        raise ValueError(f"Example {example.label} does not contain route start metadata.")

    dist = int(payload["dist"])
    network_type = str(payload["network_type"])
    executor = str(payload["executor"])
    weights = payload["weights"]
    thresholds = payload["thresholds"]
    overlay_dir = payload.get("overlay_dir")
    overlay_threshold = payload.get("overlay_threshold")
    refresh_snapshots = bool(payload.get("refresh_snapshots", False))
    snapshot_dir = payload.get("snapshot_dir")
    shared_cache_key = payload.get("shared_cache_key")

    start = (example.start[1], example.start[0])
    commands = load_parsed_instructions(example)
    target_dist = max(dist, recommended_graph_dist(commands))
    graph_source = "live"
    if shared_cache_key and snapshot_dir:
        cache = SharedGraphCache(snapshot_dir)
        active_builder = cache.load_builder(str(shared_cache_key))
        if active_builder is None:
            raise FileNotFoundError(f"Shared graph cache {shared_cache_key} is missing under {snapshot_dir}.")
        graph_source = "shared"
    elif snapshot_dir:
        active_builder, graph_source = GraphSnapshotStore(snapshot_dir).load_or_create_builder(
            example,
            center=start,
            dist=target_dist,
            network_type=network_type,
            refresh=refresh_snapshots,
        )
    else:
        active_builder = PathBuilder.from_osm(start, dist=target_dist, network_type=network_type)
    active_builder = active_builder.local_view(start, target_dist)
    trace = active_builder.execute(commands, ExecutionState(current_coordinates=start, current_heading=0.0), executor=executor)
    predicted = active_builder.trace_to_geojson(trace)
    reference = load_reference_route(example)
    result = score_geojson_routes(predicted, reference, weights=weights, thresholds=thresholds)
    row = CorpusEvaluationRow(
        corpus=example.corpus,
        example_id=str(example.example_id),
        similarity=result.similarity,
        length_ratio=result.scores["length_ratio"],
        hausdorff=result.scores["hausdorff"],
        iou=result.scores["iou"],
        angle=result.scores["angle"],
        endpoints_shift=result.scores["endpoints_shift"],
        edr=result.scores["edr"],
        waypoint_count=len(trace.waypoints),
        segment_count=len(trace.segment_coordinates),
        graph_source=graph_source,
        executor=executor,
        city=example.city,
        difficulty=example.difficulty,
    )
    if overlay_dir and overlay_threshold is not None and row.similarity < float(overlay_threshold):
        plot_route_pair(
            reference,
            predicted,
            Path(str(overlay_dir)) / f"{_artifact_name(example)}.png",
            title=f"{example.label} ({row.similarity:.2f})",
        )
    return row


def evaluate_route_examples(
    examples: Iterable[DatasetExample],
    *,
    builder: PathBuilder | dict[str, PathBuilder] | None = None,
    dist: int = 1200,
    weights: SimilarityWeights | None = None,
    thresholds: SimilarityThresholds | None = None,
    overlay_dir: str | Path | None = None,
    overlay_threshold: float | None = None,
    progress: bool = False,
    snapshot_store: GraphSnapshotStore | None = None,
    snapshot_dir: str | Path | None = None,
    refresh_snapshots: bool = False,
    network_type: str = "walk",
    executor: str = "greedy",
    jobs: int = 1,
    shared_cache_keys: dict[str, str] | None = None,
) -> list[CorpusEvaluationRow]:
    rows: list[CorpusEvaluationRow] = []
    weights = weights or SimilarityWeights()
    thresholds = thresholds or SimilarityThresholds()
    overlay_base = Path(overlay_dir) if overlay_dir else None
    if overlay_base:
        overlay_base.mkdir(parents=True, exist_ok=True)

    example_list = list(examples)
    total = len(example_list)
    if snapshot_store is None and snapshot_dir:
        snapshot_store = GraphSnapshotStore(snapshot_dir)
    effective_jobs = max(1, int(jobs))
    can_parallelize = effective_jobs > 1 and builder is None
    if can_parallelize and overlay_base is not None:
        overlay_base.mkdir(parents=True, exist_ok=True)
    if can_parallelize:
        payloads = [
            {
                "example": example,
                "dist": dist,
                "weights": weights,
                "thresholds": thresholds,
                "overlay_dir": str(overlay_base) if overlay_base else None,
                "overlay_threshold": overlay_threshold,
                "snapshot_dir": str(snapshot_dir) if snapshot_dir else None,
                "refresh_snapshots": refresh_snapshots,
                "network_type": network_type,
                "executor": executor,
                "shared_cache_key": _shared_cache_key_for_example(shared_cache_keys, example),
            }
            for example in example_list
        ]
        with ProcessPoolExecutor(max_workers=effective_jobs) as pool:
            for index, row in enumerate(pool.map(_evaluate_example_worker, payloads), start=1):
                rows.append(row)
                if progress:
                    label = "/".join(
                        part
                        for part in [row.corpus, row.city, row.difficulty, row.example_id]
                        if part
                    )
                    print(
                        f"[{index}/{total}] example={label} similarity={row.similarity:.4f} graph={row.graph_source}",
                        flush=True,
                    )
        return rows

    for index, example in enumerate(example_list, start=1):
        if example.start is None:
            continue
        start = (example.start[1], example.start[0])
        commands = load_parsed_instructions(example)
        target_dist = max(dist, recommended_graph_dist(commands))
        shared_builder = _builder_for_example(builder, example)
        if shared_builder is not None:
            active_builder = shared_builder
            graph_source = "shared"
        elif snapshot_store is not None:
            active_builder, graph_source = snapshot_store.load_or_create_builder(
                example,
                center=start,
                dist=target_dist,
                network_type=network_type,
                refresh=refresh_snapshots,
            )
        else:
            active_builder = PathBuilder.from_osm(start, dist=target_dist, network_type=network_type)
            graph_source = "live"
        active_builder = active_builder.local_view(start, target_dist)
        trace = active_builder.execute(commands, ExecutionState(current_coordinates=start, current_heading=0.0), executor=executor)
        predicted = active_builder.trace_to_geojson(trace)
        reference = load_reference_route(example)
        result = score_geojson_routes(predicted, reference, weights=weights, thresholds=thresholds)
        row = CorpusEvaluationRow(
            corpus=example.corpus,
            example_id=str(example.example_id),
            similarity=result.similarity,
            length_ratio=result.scores["length_ratio"],
            hausdorff=result.scores["hausdorff"],
            iou=result.scores["iou"],
            angle=result.scores["angle"],
            endpoints_shift=result.scores["endpoints_shift"],
            edr=result.scores["edr"],
            waypoint_count=len(trace.waypoints),
            segment_count=len(trace.segment_coordinates),
            graph_source=graph_source,
            executor=executor,
            city=example.city,
            difficulty=example.difficulty,
        )
        rows.append(row)
        if overlay_base and overlay_threshold is not None and row.similarity < overlay_threshold:
            plot_route_pair(reference, predicted, overlay_base / f"{_artifact_name(example)}.png", title=f"{example.label} ({row.similarity:.2f})")
        if progress:
            print(f"[{index}/{total}] example={example.label} similarity={row.similarity:.4f} graph={graph_source}", flush=True)
    return rows


def evaluate_examples(
    example_ids: Iterable[str],
    root: str | Path = "data_set",
    builder: PathBuilder | dict[str, PathBuilder] | None = None,
    dist: int = 1200,
    weights: SimilarityWeights | None = None,
    thresholds: SimilarityThresholds | None = None,
    overlay_dir: str | Path | None = None,
    overlay_threshold: float | None = None,
    progress: bool = False,
    snapshot_dir: str | Path | None = None,
    refresh_snapshots: bool = False,
    network_type: str = "walk",
    executor: str = "greedy",
    jobs: int = 1,
    shared_cache_keys: dict[str, str] | None = None,
) -> list[CorpusEvaluationRow]:
    examples = [load_example(example_id, root=root) for example_id in example_ids]
    snapshot_store = GraphSnapshotStore(snapshot_dir) if snapshot_dir else None
    return evaluate_route_examples(
        examples,
        builder=builder,
        dist=dist,
        weights=weights,
        thresholds=thresholds,
        overlay_dir=overlay_dir,
        overlay_threshold=overlay_threshold,
        progress=progress,
        snapshot_store=snapshot_store,
        snapshot_dir=snapshot_dir,
        refresh_snapshots=refresh_snapshots,
        network_type=network_type,
        executor=executor,
        jobs=jobs,
        shared_cache_keys=shared_cache_keys,
    )


def evaluate_corpus(
    corpus: str,
    *,
    root: str | Path | None = None,
    builder: PathBuilder | dict[str, PathBuilder] | None = None,
    dist: int = 1200,
    weights: SimilarityWeights | None = None,
    thresholds: SimilarityThresholds | None = None,
    overlay_dir: str | Path | None = None,
    overlay_threshold: float | None = None,
    progress: bool = False,
    snapshot_dir: str | Path | None = None,
    refresh_snapshots: bool = False,
    network_type: str = "walk",
    cities: Iterable[str] | None = None,
    difficulties: Iterable[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    manifest_path: str | Path | None = None,
    paper_valid_only: bool = True,
    pb_recoverable_only: bool = False,
    executor: str = "greedy",
    jobs: int = 1,
    shared_cache_keys: dict[str, str] | None = None,
) -> list[CorpusEvaluationRow]:
    examples = iter_corpus_examples(corpus, root=root, cities=cities, difficulties=difficulties)
    if manifest_path:
        manifest_records = load_route_audit_manifest(manifest_path)
        examples = filter_examples_by_manifest(
            examples,
            manifest_records,
            paper_valid_only=paper_valid_only,
            pb_recoverable_only=pb_recoverable_only,
        )
    selected = examples[offset : offset + limit] if limit is not None else examples[offset:]
    snapshot_store = GraphSnapshotStore(snapshot_dir) if snapshot_dir else None
    return evaluate_route_examples(
        selected,
        builder=builder,
        dist=dist,
        weights=weights,
        thresholds=thresholds,
        overlay_dir=overlay_dir,
        overlay_threshold=overlay_threshold,
        progress=progress,
        snapshot_store=snapshot_store,
        snapshot_dir=snapshot_dir,
        refresh_snapshots=refresh_snapshots,
        network_type=network_type,
        executor=executor,
        jobs=jobs,
        shared_cache_keys=shared_cache_keys,
    )


def freeze_graph_snapshots(
    corpus: str,
    *,
    snapshot_dir: str | Path,
    root: str | Path | None = None,
    dist: int = 1200,
    refresh_snapshots: bool = False,
    network_type: str = "walk",
    cities: Iterable[str] | None = None,
    difficulties: Iterable[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    progress: bool = False,
    manifest_path: str | Path | None = None,
    paper_valid_only: bool = True,
    pb_recoverable_only: bool = False,
) -> dict[str, int]:
    examples = iter_corpus_examples(corpus, root=root or corpus, cities=cities, difficulties=difficulties)
    if manifest_path:
        manifest_records = load_route_audit_manifest(manifest_path)
        examples = filter_examples_by_manifest(
            examples,
            manifest_records,
            paper_valid_only=paper_valid_only,
            pb_recoverable_only=pb_recoverable_only,
        )
    selected = examples[offset : offset + limit] if limit is not None else examples[offset:]
    snapshot_store = GraphSnapshotStore(snapshot_dir)
    created = 0
    reused = 0
    skipped = 0
    total = len(selected)
    for index, example in enumerate(selected, start=1):
        if example.start is None:
            skipped += 1
            continue
        commands = load_parsed_instructions(example)
        target_dist = max(dist, recommended_graph_dist(commands))
        _, graph_source = snapshot_store.load_or_create_builder(
            example,
            center=(example.start[1], example.start[0]),
            dist=target_dist,
            network_type=network_type,
            refresh=refresh_snapshots,
        )
        if graph_source == "frozen":
            reused += 1
        else:
            created += 1
        if progress:
            print(f"[{index}/{total}] example={example.label} graph={graph_source}", flush=True)
    return {"count": total, "created": created, "reused": reused, "skipped": skipped}


def write_rows_csv(rows: list[CorpusEvaluationRow], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()) if rows else list(CorpusEvaluationRow.__annotations__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

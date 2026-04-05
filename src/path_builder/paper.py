from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence

from .datasets import iter_corpus_examples, load_parsed_instructions, load_reference_route
from .difficulty import DIFFICULTY_DISTANCE_RANGES, PUBLIC_DIFFICULTY_BANDS, classify_difficulty_v2
from .geo import path_length_meters
from .models import CorpusEvaluationRow, DatasetExample, NavigationCommand, RouteAuditRecord, RouteComplexityProfile
from .similarity import extract_linestring_coordinates

PAPER_CITIES = ("Toronto_Canada", "Tokyo_23_wards", "Munich_Germany")


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _route_polyline_length(route_geojson: dict) -> float:
    lines = extract_linestring_coordinates(route_geojson)
    if not lines:
        return 0.0
    return path_length_meters([(lat, lon) for lon, lat in lines[0]])


def _commands_without_arrival(commands: Sequence[NavigationCommand]) -> list[NavigationCommand]:
    return [command for command in commands if command.primary_action != "arrive"]


def profile_commands(commands: Sequence[NavigationCommand], *, route_length_m: float) -> RouteComplexityProfile:
    effective_commands = _commands_without_arrival(commands)
    step_count = len(effective_commands)
    turn_commands = [command for command in effective_commands if command.primary_action == "turn"]
    turn_count = len(turn_commands)
    named_steps = [command for command in effective_commands if command.all_street_targets]
    anonymous_turns = [command for command in turn_commands if not command.all_street_targets]
    roundabout_count = sum(1 for command in effective_commands if command.instruction_kind == "roundabout_exit")
    keep_count = sum(1 for command in effective_commands if command.turn_strength == "keep")
    short_turn_count = sum(1 for command in turn_commands if 0.0 < command.primary_distance <= 15.0)
    longest_anonymous_chain = 0
    current_chain = 0
    for command in effective_commands:
        if command.primary_action in {"turn", "continue"} and not command.all_street_targets:
            current_chain += 1
            longest_anonymous_chain = max(longest_anonymous_chain, current_chain)
        else:
            current_chain = 0
    turn_density_per_km = _safe_ratio(turn_count, max(route_length_m, 1.0) / 1000.0)
    complexity_score = 0.0
    complexity_score += min(turn_density_per_km / 4.0, 2.5)
    complexity_score += min(longest_anonymous_chain / 2.0, 2.5)
    complexity_score += _safe_ratio(len(anonymous_turns), max(turn_count, 1)) * 2.0
    complexity_score += min(roundabout_count, 3) * 0.75
    complexity_score += min(short_turn_count, 4) * 0.3
    return RouteComplexityProfile(
        route_length_m=route_length_m,
        step_count=step_count,
        turn_count=turn_count,
        named_step_ratio=_safe_ratio(len(named_steps), step_count),
        anonymous_turn_ratio=_safe_ratio(len(anonymous_turns), turn_count),
        longest_anonymous_chain=longest_anonymous_chain,
        roundabout_count=roundabout_count,
        keep_count=keep_count,
        short_turn_count=short_turn_count,
        turn_density_per_km=turn_density_per_km,
        complexity_score=complexity_score,
    )


def _paper_invalid_reasons(profile: RouteComplexityProfile, commands: Sequence[NavigationCommand]) -> list[str]:
    reasons: list[str] = []
    if not commands:
        reasons.append("no_commands")
    if profile.route_length_m < DIFFICULTY_DISTANCE_RANGES["easy"][0] or profile.route_length_m > DIFFICULTY_DISTANCE_RANGES["hard"][1]:
        reasons.append("distance_out_of_range")
    if profile.step_count < 2:
        reasons.append("too_few_steps")
    if profile.turn_count == 0:
        reasons.append("no_turns")
    if any(command.instruction_kind == "roundabout_exit" and command.roundabout_exit_index is None for command in commands):
        reasons.append("roundabout_exit_missing")
    return reasons


def _audit_pb_recoverability(
    example: DatasetExample,
    *,
    commands: Sequence[NavigationCommand],
    route_geojson: dict,
    builder: object | None,
    snapshot_dir: str | Path | None,
    dist: int,
    network_type: str,
    executor: str,
) -> dict[str, object]:
    from .ceiling import summarize_execution_ceiling
    from .execution import PathBuilder, _is_placeholder_street_name, graph_contains_named_street, recommended_graph_dist
    from .graphs import GraphSnapshotStore
    from .models import ExecutionState
    from .similarity import score_geojson_routes

    if example.start is None:
        return {
            "pb_recoverable": False,
            "recoverability_reasons": ["missing_start"],
            "pb_similarity": None,
            "pb_executor": executor,
            "pb_hard_constraints": [],
            "pb_soft_constraints": [],
        }

    commands_list = list(commands)
    start = (example.start[1], example.start[0])
    target_dist = max(dist, recommended_graph_dist(commands_list))
    active_builder = builder
    if active_builder is None and snapshot_dir is not None:
        active_builder, _ = GraphSnapshotStore(snapshot_dir).load_or_create_builder(
            example,
            center=start,
            dist=target_dist,
            network_type=network_type,
            refresh=False,
        )
    if active_builder is None:
        active_builder = PathBuilder.from_osm(start, dist=target_dist, network_type=network_type)
    elif hasattr(active_builder, "local_view"):
        active_builder = active_builder.local_view(start, target_dist)  # type: ignore[assignment]

    has_missing_named_street = False
    for command in commands_list:
        preferred_streets = [
            street
            for street in command.end_streets + command.start_streets
            if street and not _is_placeholder_street_name(street)
        ]
        if preferred_streets and not graph_contains_named_street(active_builder.graph, preferred_streets):  # type: ignore[union-attr]
            has_missing_named_street = True
            break
    if has_missing_named_street:
        return {
            "pb_recoverable": False,
            "recoverability_reasons": ["named-street-oov"],
            "pb_similarity": None,
            "pb_executor": "greedy",
            "pb_hard_constraints": ["named-street-oov"],
            "pb_soft_constraints": [],
        }

    def _run_pb_executor(run_executor: str) -> dict[str, object]:
        trace = active_builder.execute(  # type: ignore[union-attr]
            commands_list,
            ExecutionState(current_coordinates=start, current_heading=0.0),
            executor=run_executor,
        )
        pb_similarity = score_geojson_routes(
            active_builder.trace_to_geojson(trace),  # type: ignore[union-attr]
            route_geojson,
        ).similarity
        ceiling_report = summarize_execution_ceiling(
            example,
            builder=active_builder,  # type: ignore[arg-type]
            commands=commands_list,
            trace=trace,
            similarity=pb_similarity,
            graph_source="audit",
        )
        summary = ceiling_report["summary"]
        hard_constraints = list(summary["hard_constraints"])
        soft_constraints = list(summary["soft_constraints"])
        return {
            "pb_recoverable": not hard_constraints,
            "recoverability_reasons": list(dict.fromkeys(hard_constraints)),
            "pb_similarity": pb_similarity,
            "pb_executor": run_executor,
            "pb_hard_constraints": hard_constraints,
            "pb_soft_constraints": soft_constraints,
        }

    baseline_payload = _run_pb_executor("greedy" if executor != "greedy" else executor)
    if executor == "greedy" or baseline_payload["pb_recoverable"]:
        return baseline_payload
    if "named-street-oov" in baseline_payload["pb_hard_constraints"]:
        return baseline_payload

    requested_payload = _run_pb_executor(executor)
    baseline_hard = len(baseline_payload["pb_hard_constraints"])
    requested_hard = len(requested_payload["pb_hard_constraints"])
    if requested_hard < baseline_hard:
        return requested_payload
    if requested_hard == baseline_hard and float(requested_payload["pb_similarity"]) > float(baseline_payload["pb_similarity"]):
        return requested_payload
    return baseline_payload


def _audit_example_worker(payload: dict[str, object]) -> RouteAuditRecord:
    example = payload["example"]
    if not isinstance(example, DatasetExample):
        raise TypeError("audit worker requires a DatasetExample payload.")

    builder = None
    shared_cache_key = payload.get("shared_cache_key")
    snapshot_dir = payload.get("snapshot_dir")
    if shared_cache_key and snapshot_dir:
        from .graphs import SharedGraphCache

        builder = SharedGraphCache(snapshot_dir).load_builder(str(shared_cache_key))
        if builder is None:
            raise FileNotFoundError(f"Shared graph cache {shared_cache_key} is missing under {snapshot_dir}.")

    return audit_example(
        example,
        pb_check=bool(payload.get("pb_check", False)),
        builder=builder,
        snapshot_dir=snapshot_dir,
        dist=int(payload.get("dist", 1200)),
        network_type=str(payload.get("network_type", "walk")),
        executor=str(payload.get("executor", "hybrid")),
    )


def audit_example(
    example: DatasetExample,
    *,
    pb_check: bool = False,
    builder: object | None = None,
    snapshot_dir: str | Path | None = None,
    dist: int = 1200,
    network_type: str = "walk",
    executor: str = "hybrid",
) -> RouteAuditRecord:
    route_geojson = load_reference_route(example)
    commands = load_parsed_instructions(example)
    route_length_m = _route_polyline_length(route_geojson)
    profile = profile_commands(commands, route_length_m=route_length_m)
    difficulty_v2 = classify_difficulty_v2(
        route_length_m=profile.route_length_m,
        complexity_score=profile.complexity_score,
        longest_anonymous_chain=profile.longest_anonymous_chain,
        turn_count=profile.turn_count,
    )
    invalid_reasons = _paper_invalid_reasons(profile, commands)
    if difficulty_v2 is None:
        invalid_reasons.append("difficulty_unclassified")
        length_bin = None
        for label, (lower, upper) in DIFFICULTY_DISTANCE_RANGES.items():
            if lower <= profile.route_length_m <= upper:
                length_bin = label
                break
        if length_bin is not None:
            band = PUBLIC_DIFFICULTY_BANDS[length_bin]
            max_chain = int(float(band["max_anonymous_chain"] or 0.0))
            complexity_min = band["complexity_min"]
            complexity_max = band["complexity_max"]
            if complexity_min is not None and profile.complexity_score < float(complexity_min):
                invalid_reasons.append("complexity_too_low_for_difficulty")
            if complexity_max is not None and profile.complexity_score > float(complexity_max):
                invalid_reasons.append("complexity_too_high_for_difficulty")
            if profile.longest_anonymous_chain > max_chain:
                invalid_reasons.append("anonymous_chain_too_long_for_difficulty")
    elif example.difficulty and difficulty_v2 != example.difficulty:
        invalid_reasons.append("difficulty_mismatch")

    pb_recoverable: bool | None = None
    recoverability_reasons: list[str] = []
    pb_similarity: float | None = None
    pb_executor: str | None = None
    pb_hard_constraints: list[str] = []
    pb_soft_constraints: list[str] = []
    if pb_check:
        if invalid_reasons:
            pb_recoverable = False
            recoverability_reasons = ["paper_invalid"]
            pb_executor = executor
        else:
            pb_payload = _audit_pb_recoverability(
                example,
                commands=commands,
                route_geojson=route_geojson,
                builder=builder,
                snapshot_dir=snapshot_dir,
                dist=dist,
                network_type=network_type,
                executor=executor,
            )
            pb_recoverable = bool(pb_payload["pb_recoverable"])
            recoverability_reasons = [str(item) for item in pb_payload["recoverability_reasons"]]
            pb_similarity = float(pb_payload["pb_similarity"]) if pb_payload["pb_similarity"] is not None else None
            pb_executor = str(pb_payload["pb_executor"]) if pb_payload["pb_executor"] is not None else None
            pb_hard_constraints = [str(item) for item in pb_payload["pb_hard_constraints"]]
            pb_soft_constraints = [str(item) for item in pb_payload["pb_soft_constraints"]]

    return RouteAuditRecord(
        corpus=example.corpus,
        example_id=str(example.example_id),
        source_difficulty=example.difficulty,
        difficulty_v2=difficulty_v2,
        paper_valid=not invalid_reasons and (example.difficulty is None or difficulty_v2 == example.difficulty),
        invalid_reasons=invalid_reasons,
        route_length_m=profile.route_length_m,
        step_count=profile.step_count,
        turn_count=profile.turn_count,
        named_step_ratio=profile.named_step_ratio,
        anonymous_turn_ratio=profile.anonymous_turn_ratio,
        longest_anonymous_chain=profile.longest_anonymous_chain,
        roundabout_count=profile.roundabout_count,
        keep_count=profile.keep_count,
        short_turn_count=profile.short_turn_count,
        turn_density_per_km=profile.turn_density_per_km,
        complexity_score=profile.complexity_score,
        city=example.city,
        pb_recoverable=pb_recoverable,
        recoverability_reasons=recoverability_reasons,
        pb_similarity=pb_similarity,
        pb_executor=pb_executor,
        pb_hard_constraints=pb_hard_constraints,
        pb_soft_constraints=pb_soft_constraints,
    )


def audit_corpus(
    corpus: str,
    *,
    root: str | Path | None = None,
    cities: Iterable[str] | None = None,
    difficulties: Iterable[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    pb_check: bool = False,
    snapshot_dir: str | Path | None = None,
    dist: int = 1200,
    network_type: str = "walk",
    executor: str = "hybrid",
    shared_graph: bool = False,
    progress: bool = False,
    jobs: int = 1,
) -> list[RouteAuditRecord]:
    examples = iter_corpus_examples(corpus, root=root or corpus, cities=cities, difficulties=difficulties)
    selected = examples[offset : offset + limit] if limit is not None else examples[offset:]
    shared_builder: object | dict[str, object] | None = None
    shared_cache_keys: dict[str, str] | None = None
    effective_jobs = max(1, int(jobs))
    if shared_graph and selected:
        from .evaluation import build_shared_graph_bundle, shared_graph_cache_keys_for_examples

        if progress:
            print(f"Preparing shared graph cache for {len(selected)} routes...", flush=True)
        shared_builder = build_shared_graph_bundle(
            corpus,
            root=root or corpus,
            selected_examples=selected,
            cities=cities,
            difficulties=difficulties,
            cache_dir=snapshot_dir,
            network_type=network_type,
            progress=progress,
        )
        if snapshot_dir:
            shared_cache_keys = shared_graph_cache_keys_for_examples(
                corpus,
                selected_examples=selected,
                difficulties=difficulties,
                network_type=network_type,
            )
        if effective_jobs > 1 and snapshot_dir is None:
            if progress:
                print("shared-graph parallel audit requires --snapshot-dir; falling back to serial execution.", flush=True)
            effective_jobs = 1

    records: list[RouteAuditRecord] = []
    total = len(selected)
    if effective_jobs > 1:
        payloads = [
            {
                "example": example,
                "pb_check": pb_check,
                "snapshot_dir": str(snapshot_dir) if snapshot_dir else None,
                "dist": dist,
                "network_type": network_type,
                "executor": executor,
                "shared_cache_key": (shared_cache_keys or {}).get(example.city or "__global__", (shared_cache_keys or {}).get("__global__")),
            }
            for example in selected
        ]
        with ProcessPoolExecutor(max_workers=effective_jobs) as pool:
            for index, record in enumerate(pool.map(_audit_example_worker, payloads), start=1):
                records.append(record)
                if progress:
                    label = "/".join(
                        part
                        for part in [record.corpus, record.city, record.source_difficulty, record.example_id]
                        if part
                    )
                    print(
                        f"[{index}/{total}] route={label} paper_valid={record.paper_valid} "
                        f"pb_recoverable={record.pb_recoverable}",
                        flush=True,
                    )
        return records

    for index, example in enumerate(selected, start=1):
        example_builder = shared_builder
        if isinstance(shared_builder, dict):
            example_builder = shared_builder.get(example.city or "", None)
        record = audit_example(
            example,
            pb_check=pb_check,
            builder=example_builder,
            snapshot_dir=snapshot_dir,
            dist=dist,
            network_type=network_type,
            executor=executor,
        )
        records.append(record)
        if progress:
            print(
                f"[{index}/{total}] route={example.label} paper_valid={record.paper_valid} pb_recoverable={record.pb_recoverable}",
                flush=True,
            )
    return records


def summarize_route_audit(records: Sequence[RouteAuditRecord]) -> dict[str, object]:
    total = len(records)
    valid_records = [record for record in records if record.paper_valid]
    recoverable_records = [record for record in records if record.pb_recoverable is True]
    by_city: dict[str, list[RouteAuditRecord]] = {}
    by_difficulty_v2: dict[str, list[RouteAuditRecord]] = {}
    invalid_reason_counts: dict[str, int] = {}
    recoverability_reason_counts: dict[str, int] = {}
    for record in records:
        if record.city:
            by_city.setdefault(record.city, []).append(record)
        if record.difficulty_v2:
            by_difficulty_v2.setdefault(record.difficulty_v2, []).append(record)
        for reason in record.invalid_reasons:
            invalid_reason_counts[reason] = invalid_reason_counts.get(reason, 0) + 1
        for reason in record.recoverability_reasons:
            recoverability_reason_counts[reason] = recoverability_reason_counts.get(reason, 0) + 1
    return {
        "count": total,
        "paper_valid_count": len(valid_records),
        "paper_valid_rate": _safe_ratio(len(valid_records), total),
        "pb_recoverable_count": len(recoverable_records),
        "pb_recoverable_rate": _safe_ratio(len(recoverable_records), total),
        "mean_route_length_m": mean([record.route_length_m for record in records]) if records else 0.0,
        "mean_complexity_score": mean([record.complexity_score for record in records]) if records else 0.0,
        "by_city": {
            key: {
                "count": len(value),
                "paper_valid_rate": _safe_ratio(sum(1 for record in value if record.paper_valid), len(value)),
                "pb_recoverable_rate": _safe_ratio(sum(1 for record in value if record.pb_recoverable is True), len(value)),
            }
            for key, value in sorted(by_city.items())
        },
        "by_difficulty_v2": {
            key: {
                "count": len(value),
                "paper_valid_rate": _safe_ratio(sum(1 for record in value if record.paper_valid), len(value)),
                "pb_recoverable_rate": _safe_ratio(sum(1 for record in value if record.pb_recoverable is True), len(value)),
            }
            for key, value in sorted(by_difficulty_v2.items())
        },
        "invalid_reasons": dict(sorted(invalid_reason_counts.items())),
        "recoverability_reasons": dict(sorted(recoverability_reason_counts.items())),
    }


def manifest_key(corpus: str, example_id: str, city: str | None = None, difficulty: str | None = None) -> str:
    if corpus == "36kroutes":
        return f"{city}/{difficulty}/{example_id}"
    return str(example_id)


def record_manifest_key(record: RouteAuditRecord) -> str:
    return manifest_key(record.corpus, record.example_id, city=record.city, difficulty=record.source_difficulty)


def example_manifest_key(example: DatasetExample) -> str:
    return manifest_key(example.corpus, example.example_id, city=example.city, difficulty=example.difficulty)


def write_route_audit_manifest(records: Sequence[RouteAuditRecord], path: str | Path) -> None:
    payload = {
        "version": 1,
        "records": [asdict(record) for record in records],
    }
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_route_audit_manifest(path: str | Path) -> list[RouteAuditRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records", payload)
    loaded: list[RouteAuditRecord] = []
    for record in records:
        loaded.append(
            RouteAuditRecord(
                corpus=record["corpus"],
                example_id=str(record["example_id"]),
                source_difficulty=record.get("source_difficulty"),
                difficulty_v2=record.get("difficulty_v2"),
                paper_valid=bool(record.get("paper_valid", False)),
                invalid_reasons=[str(item) for item in record.get("invalid_reasons", [])],
                route_length_m=float(record.get("route_length_m", 0.0)),
                step_count=int(record.get("step_count", 0)),
                turn_count=int(record.get("turn_count", 0)),
                named_step_ratio=float(record.get("named_step_ratio", 0.0)),
                anonymous_turn_ratio=float(record.get("anonymous_turn_ratio", 0.0)),
                longest_anonymous_chain=int(record.get("longest_anonymous_chain", 0)),
                roundabout_count=int(record.get("roundabout_count", 0)),
                keep_count=int(record.get("keep_count", 0)),
                short_turn_count=int(record.get("short_turn_count", 0)),
                turn_density_per_km=float(record.get("turn_density_per_km", 0.0)),
                complexity_score=float(record.get("complexity_score", 0.0)),
                city=record.get("city"),
                pb_recoverable=record.get("pb_recoverable"),
                recoverability_reasons=[str(item) for item in record.get("recoverability_reasons", [])],
                pb_similarity=float(record["pb_similarity"]) if record.get("pb_similarity") is not None else None,
                pb_executor=record.get("pb_executor"),
                pb_hard_constraints=[str(item) for item in record.get("pb_hard_constraints", [])],
                pb_soft_constraints=[str(item) for item in record.get("pb_soft_constraints", [])],
            )
        )
    return loaded


def filter_examples_by_manifest(
    examples: Sequence[DatasetExample],
    manifest_records: Sequence[RouteAuditRecord],
    *,
    paper_valid_only: bool = True,
    pb_recoverable_only: bool = False,
) -> list[DatasetExample]:
    allowed = {
        record_manifest_key(record)
        for record in manifest_records
        if (record.paper_valid or not paper_valid_only)
        and (record.pb_recoverable is True or not pb_recoverable_only)
    }
    return [example for example in examples if example_manifest_key(example) in allowed]


def build_guardrail_records(
    records: Sequence[RouteAuditRecord],
    *,
    cities: Sequence[str] | None = None,
    source_difficulties: Sequence[str] = ("easy", "medium", "hard"),
    per_city_difficulty: int = 10,
    pb_recoverable_only: bool = False,
) -> list[RouteAuditRecord]:
    selected: list[RouteAuditRecord] = []
    city_filter = set(cities or [])
    for city in sorted({record.city for record in records if record.city and (not city_filter or record.city in city_filter)}):
        for difficulty in source_difficulties:
            bucket = [
                record
                for record in records
                if record.paper_valid
                and record.city == city
                and record.source_difficulty == difficulty
                and (record.pb_recoverable is True or not pb_recoverable_only)
            ]
            if not bucket:
                continue
            bucket.sort(key=lambda record: (record.complexity_score, record.example_id))
            if len(bucket) <= per_city_difficulty:
                selected.extend(bucket)
                continue
            for index in range(per_city_difficulty):
                position = round(index * (len(bucket) - 1) / max(per_city_difficulty - 1, 1))
                selected.append(bucket[position])
    return selected


def build_success_summary(rows: Sequence[CorpusEvaluationRow], *, success_threshold: float = 85.0) -> dict[str, float | int]:
    count = len(rows)
    success_count = sum(1 for row in rows if row.similarity >= success_threshold)
    values = [row.similarity for row in rows]
    return {
        "count": count,
        "success_count": success_count,
        "success_rate": _safe_ratio(success_count, count),
        "mean_similarity": mean(values) if values else 0.0,
        "min_similarity": min(values) if values else 0.0,
        "max_similarity": max(values) if values else 0.0,
    }

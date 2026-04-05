from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median

from .models import CorpusEvaluationRow

DEFAULT_FAILURE_CLUSTER_IDS = ("4", "5", "6", "7", "10", "11")
DEFAULT_PROTECTED_EXAMPLE_IDS = ("1", "2", "9")


@dataclass(slots=True)
class ReproductionGate:
    min_mean_similarity: float = 72.0
    min_min_similarity: float = 50.0
    min_failure_cluster_mean_similarity: float = 60.0
    max_protected_regression: float = 2.0


@dataclass(slots=True)
class ReproductionConfig:
    name: str
    baseline_csv: Path
    snapshot_dir: Path
    dataset_root: Path
    corpus: str = "data_set"
    limit: int = 12
    offset: int = 0
    overlay_threshold: float = 60.0
    failure_cluster_ids: tuple[str, ...] = field(default_factory=lambda: DEFAULT_FAILURE_CLUSTER_IDS)
    protected_example_ids: tuple[str, ...] = field(default_factory=lambda: DEFAULT_PROTECTED_EXAMPLE_IDS)
    gates: ReproductionGate = field(default_factory=ReproductionGate)


def _resolve_config_path(config_path: Path, value: str | None, default: str) -> Path:
    resolved = value or default
    return (config_path.parent / resolved).resolve()


def load_reproduction_config(path: str | Path) -> ReproductionConfig:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    gate_payload = payload.get("gates", {})
    return ReproductionConfig(
        name=payload["name"],
        baseline_csv=_resolve_config_path(config_path, payload.get("baseline_csv"), "../benchmark_assets/reproduction/baseline/data_set_first12_frozen.csv"),
        snapshot_dir=_resolve_config_path(config_path, payload.get("snapshot_dir"), "../cache/graph_snapshots"),
        dataset_root=_resolve_config_path(config_path, payload.get("dataset_root"), "../data_set"),
        corpus=payload.get("corpus", "data_set"),
        limit=int(payload.get("limit", 12)),
        offset=int(payload.get("offset", 0)),
        overlay_threshold=float(payload.get("overlay_threshold", 60.0)),
        failure_cluster_ids=tuple(str(item) for item in payload.get("failure_cluster_ids", DEFAULT_FAILURE_CLUSTER_IDS)),
        protected_example_ids=tuple(str(item) for item in payload.get("protected_example_ids", DEFAULT_PROTECTED_EXAMPLE_IDS)),
        gates=ReproductionGate(
            min_mean_similarity=float(gate_payload.get("min_mean_similarity", 72.0)),
            min_min_similarity=float(gate_payload.get("min_min_similarity", 50.0)),
            min_failure_cluster_mean_similarity=float(gate_payload.get("min_failure_cluster_mean_similarity", 60.0)),
            max_protected_regression=float(gate_payload.get("max_protected_regression", 2.0)),
        ),
    )


def _example_sort_key(example_id: str) -> tuple[int, int | str]:
    return (0, int(example_id)) if example_id.isdigit() else (1, example_id)


def load_evaluation_rows_csv(path: str | Path) -> list[CorpusEvaluationRow]:
    rows: list[CorpusEvaluationRow] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for record in reader:
            rows.append(
                CorpusEvaluationRow(
                    corpus=record.get("corpus") or "data_set",
                    example_id=str(record["example_id"]),
                    similarity=float(record["similarity"]),
                    length_ratio=float(record["length_ratio"]),
                    hausdorff=float(record["hausdorff"]),
                    iou=float(record["iou"]),
                    angle=float(record["angle"]),
                    endpoints_shift=float(record["endpoints_shift"]),
                    edr=float(record["edr"]),
                    waypoint_count=int(float(record["waypoint_count"])),
                    segment_count=int(float(record["segment_count"])),
                    graph_source=record.get("graph_source") or "unknown",
                    executor=record.get("executor") or "greedy",
                    city=record.get("city") or None,
                    difficulty=record.get("difficulty") or None,
                )
            )
    return rows


def _basic_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "mean_similarity": mean(values) if values else 0.0,
        "median_similarity": median(values) if values else 0.0,
        "min_similarity": min(values) if values else 0.0,
        "max_similarity": max(values) if values else 0.0,
    }


def _rows_by_example_id(rows: list[CorpusEvaluationRow]) -> dict[str, CorpusEvaluationRow]:
    return {row.example_id: row for row in rows}


def _select_rows(rows_by_id: dict[str, CorpusEvaluationRow], example_ids: tuple[str, ...]) -> list[CorpusEvaluationRow]:
    return [rows_by_id[example_id] for example_id in example_ids if example_id in rows_by_id]


def build_reproduction_summary(
    rows: list[CorpusEvaluationRow],
    *,
    failure_cluster_ids: tuple[str, ...] = DEFAULT_FAILURE_CLUSTER_IDS,
    protected_example_ids: tuple[str, ...] = DEFAULT_PROTECTED_EXAMPLE_IDS,
) -> dict[str, object]:
    by_id = _rows_by_example_id(rows)
    failure_rows = _select_rows(by_id, failure_cluster_ids)
    protected_scores = {
        example_id: by_id[example_id].similarity
        for example_id in protected_example_ids
        if example_id in by_id
    }
    example_scores = {
        example_id: by_id[example_id].similarity
        for example_id in sorted(by_id, key=_example_sort_key)
    }
    return {
        "overall": _basic_summary([row.similarity for row in rows]),
        "failure_cluster": {
            "ids": [row.example_id for row in failure_rows],
            **_basic_summary([row.similarity for row in failure_rows]),
        },
        "protected_examples": protected_scores,
        "example_scores": example_scores,
    }


def compare_reproduction_runs(
    baseline_rows: list[CorpusEvaluationRow],
    candidate_rows: list[CorpusEvaluationRow],
    config: ReproductionConfig,
) -> dict[str, object]:
    baseline_by_id = _rows_by_example_id(baseline_rows)
    candidate_by_id = _rows_by_example_id(candidate_rows)
    baseline_ids = tuple(sorted(baseline_by_id, key=_example_sort_key))
    candidate_ids = tuple(sorted(candidate_by_id, key=_example_sort_key))

    shared_ids = tuple(example_id for example_id in baseline_ids if example_id in candidate_by_id)
    baseline_shared = [baseline_by_id[example_id] for example_id in shared_ids]
    candidate_shared = [candidate_by_id[example_id] for example_id in shared_ids]
    baseline_summary = build_reproduction_summary(
        baseline_shared,
        failure_cluster_ids=config.failure_cluster_ids,
        protected_example_ids=config.protected_example_ids,
    )
    candidate_summary = build_reproduction_summary(
        candidate_shared,
        failure_cluster_ids=config.failure_cluster_ids,
        protected_example_ids=config.protected_example_ids,
    )

    protected_regressions: dict[str, float] = {}
    for example_id in config.protected_example_ids:
        if example_id not in baseline_by_id or example_id not in candidate_by_id:
            continue
        protected_regressions[example_id] = baseline_by_id[example_id].similarity - candidate_by_id[example_id].similarity

    example_set_match = baseline_ids == candidate_ids
    missing_from_candidate = [example_id for example_id in baseline_ids if example_id not in candidate_by_id]
    extra_in_candidate = [example_id for example_id in candidate_ids if example_id not in baseline_by_id]

    candidate_overall = candidate_summary["overall"]
    candidate_failure = candidate_summary["failure_cluster"]
    gate_results = {
        "example_set_match": {
            "passed": example_set_match,
            "missing_from_candidate": missing_from_candidate,
            "extra_in_candidate": extra_in_candidate,
        },
        "mean_similarity": {
            "passed": candidate_overall["mean_similarity"] >= config.gates.min_mean_similarity,
            "actual": candidate_overall["mean_similarity"],
            "threshold": config.gates.min_mean_similarity,
        },
        "min_similarity": {
            "passed": candidate_overall["min_similarity"] >= config.gates.min_min_similarity,
            "actual": candidate_overall["min_similarity"],
            "threshold": config.gates.min_min_similarity,
        },
        "failure_cluster_mean_similarity": {
            "passed": candidate_failure["mean_similarity"] >= config.gates.min_failure_cluster_mean_similarity,
            "actual": candidate_failure["mean_similarity"],
            "threshold": config.gates.min_failure_cluster_mean_similarity,
        },
        "protected_regressions": {
            "passed": all(delta <= config.gates.max_protected_regression for delta in protected_regressions.values()),
            "actual": protected_regressions,
            "threshold": config.gates.max_protected_regression,
        },
    }
    return {
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "gate_results": gate_results,
        "passed": all(result["passed"] for result in gate_results.values()),
    }

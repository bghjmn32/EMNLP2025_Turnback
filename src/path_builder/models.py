from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LatLon = tuple[float, float]
LonLat = tuple[float, float]


@dataclass(slots=True)
class NavigationCommand:
    actions: list[str] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)
    start_streets: list[str] = field(default_factory=list)
    end_streets: list[str] = field(default_factory=list)
    street_targets: list[str] = field(default_factory=list)
    distances: list[float] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    instruction_kind: str = "normal"
    roundabout_exit_index: int | None = None
    turn_strength: str | None = None
    raw_text: str | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "NavigationCommand":
        start_streets = [str(item) for item in payload.get("start_streets", [])]
        end_streets = [str(item) for item in payload.get("end_streets", [])]
        street_targets = [str(item) for item in payload.get("street_targets", [])]
        return cls(
            actions=[str(item).lower() for item in payload.get("actions", [])],
            directions=[str(item).lower() for item in payload.get("directions", [])],
            start_streets=start_streets,
            end_streets=end_streets,
            street_targets=street_targets or [*start_streets, *end_streets],
            distances=[float(item) for item in payload.get("distances", [])],
            durations=[float(item) for item in payload.get("durations", [])],
            instruction_kind=str(payload.get("instruction_kind", "normal") or "normal"),
            roundabout_exit_index=int(payload["roundabout_exit_index"]) if payload.get("roundabout_exit_index") is not None else None,
            turn_strength=str(payload["turn_strength"]).lower() if payload.get("turn_strength") else None,
            raw_text=payload.get("raw_text"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": self.actions,
            "directions": self.directions,
            "start_streets": self.start_streets,
            "end_streets": self.end_streets,
            "street_targets": self.street_targets,
            "distances": self.distances,
            "durations": self.durations,
            "instruction_kind": self.instruction_kind,
            "roundabout_exit_index": self.roundabout_exit_index,
            "turn_strength": self.turn_strength,
            "raw_text": self.raw_text,
        }

    @property
    def primary_action(self) -> str | None:
        return self.actions[0] if self.actions else None

    @property
    def primary_direction(self) -> str | None:
        return self.directions[0] if self.directions else None

    @property
    def primary_distance(self) -> float:
        return self.distances[0] if self.distances else 0.0

    @property
    def primary_duration(self) -> float:
        return self.durations[0] if self.durations else 0.0

    @property
    def all_street_targets(self) -> list[str]:
        if self.street_targets:
            return [street for street in self.street_targets if street]
        merged: list[str] = []
        for street in [*self.end_streets, *self.start_streets]:
            if street and street not in merged:
                merged.append(street)
        return merged


@dataclass(slots=True)
class DatasetExample:
    corpus: str
    example_id: str
    root: Path
    route_geojson_path: Path
    instructions_path: Path | None
    natural_instructions_path: Path | None
    parsed_instructions_path: Path | None
    reverse_route_path: Path | None
    start: LonLat | None
    end: LonLat | None
    city: str | None = None
    difficulty: str | None = None

    @property
    def label(self) -> str:
        parts = [self.corpus]
        if self.city:
            parts.append(self.city)
        if self.difficulty:
            parts.append(self.difficulty)
        parts.append(self.example_id)
        return "/".join(parts)


@dataclass(slots=True)
class ExecutionState:
    current_coordinates: LatLon
    current_heading: float = 0.0
    current_street: str | None = None


@dataclass(slots=True)
class ExecutionCandidateDiagnostic:
    node: str
    street: str | None
    bearing: float
    street_penalty: float
    turn_penalty: float
    continuity_penalty: float
    projection_distance_m: float
    node_distance_m: float
    preview_penalty: float
    total_score: float


@dataclass(slots=True)
class ExecutionStepDiagnostic:
    index: int
    step_kind: str
    action: str | None
    direction: str | None
    raw_text: str | None
    desired_heading: float
    start_coordinates: LatLon
    end_coordinates: LatLon
    selected_street: str | None = None
    selected_bearing: float | None = None
    selected_score: float | None = None
    segment_indexes: list[int] = field(default_factory=list)
    candidate_diagnostics: list[ExecutionCandidateDiagnostic] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionTrace:
    initial_state: ExecutionState
    final_state: ExecutionState
    waypoints: list[LatLon]
    traversed_edges: list[tuple[Any, Any, Any | None]] = field(default_factory=list)
    segment_coordinates: list[list[tuple[float, float]]] = field(default_factory=list)
    step_segments: list[list[int]] = field(default_factory=list)
    step_diagnostics: list[ExecutionStepDiagnostic] = field(default_factory=list)


@dataclass(slots=True)
class SimilarityWeights:
    angle: float = 0.0142
    edr: float = 0.0401
    endpoints_shift: float = 0.018
    hausdorff: float = 0.0374
    iou: float = 0.4737
    length_ratio: float = 0.4166

    def as_dict(self) -> dict[str, float]:
        return {
            "angle": self.angle,
            "edr": self.edr,
            "endpoints_shift": self.endpoints_shift,
            "hausdorff": self.hausdorff,
            "iou": self.iou,
            "length_ratio": self.length_ratio,
        }


@dataclass(slots=True)
class SimilarityThresholds:
    nearest_junction_meters: float = 100.0
    confidence_percentage: float = 0.90
    buffer_meters: float = 20.0
    hausdorff_scale_m: float = 50.0
    endpoints_scale_m: float = 20.0
    edr_resample_points: int = 64
    edr_bearing_bins: int = 16
    hausdorff_densify_points: int = 128

    def as_dict(self) -> dict[str, float | int]:
        return {
            "nearest_junction_meters": self.nearest_junction_meters,
            "confidence_percentage": self.confidence_percentage,
            "buffer_meters": self.buffer_meters,
            "hausdorff_scale_m": self.hausdorff_scale_m,
            "endpoints_scale_m": self.endpoints_scale_m,
            "edr_resample_points": self.edr_resample_points,
            "edr_bearing_bins": self.edr_bearing_bins,
            "hausdorff_densify_points": self.hausdorff_densify_points,
        }


@dataclass(slots=True)
class SimilarityResult:
    similarity: float
    scores: dict[str, float]
    weights: dict[str, float]
    params: dict[str, float | int]


@dataclass(slots=True)
class GraphSnapshotManifest:
    corpus: str
    example_id: str
    graph_source: str
    network_type: str
    dist: int
    created_at: str
    city: str | None = None
    difficulty: str | None = None
    graph_path: str = "graph.graphml"


@dataclass(slots=True)
class CorpusEvaluationRow:
    corpus: str
    example_id: str
    similarity: float
    length_ratio: float
    hausdorff: float
    iou: float
    angle: float
    endpoints_shift: float
    edr: float
    waypoint_count: int
    segment_count: int
    graph_source: str
    executor: str = "greedy"
    city: str | None = None
    difficulty: str | None = None


@dataclass(slots=True)
class CorpusEvaluationSummary:
    overall: dict[str, float | int]
    by_city: dict[str, dict[str, float | int]] = field(default_factory=dict)
    by_difficulty: dict[str, dict[str, float | int]] = field(default_factory=dict)
    by_city_difficulty: dict[str, dict[str, float | int]] = field(default_factory=dict)


@dataclass(slots=True)
class RouteComplexityProfile:
    route_length_m: float
    step_count: int
    turn_count: int
    named_step_ratio: float
    anonymous_turn_ratio: float
    longest_anonymous_chain: int
    roundabout_count: int
    keep_count: int
    short_turn_count: int
    turn_density_per_km: float
    complexity_score: float


@dataclass(slots=True)
class RouteAuditRecord:
    corpus: str
    example_id: str
    source_difficulty: str | None
    difficulty_v2: str | None
    paper_valid: bool
    invalid_reasons: list[str]
    route_length_m: float
    step_count: int
    turn_count: int
    named_step_ratio: float
    anonymous_turn_ratio: float
    longest_anonymous_chain: int
    roundabout_count: int
    keep_count: int
    short_turn_count: int
    turn_density_per_km: float
    complexity_score: float
    city: str | None = None
    pb_recoverable: bool | None = None
    recoverability_reasons: list[str] = field(default_factory=list)
    pb_similarity: float | None = None
    pb_executor: str | None = None
    pb_hard_constraints: list[str] = field(default_factory=list)
    pb_soft_constraints: list[str] = field(default_factory=list)

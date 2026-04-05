from __future__ import annotations

DIFFICULTY_DISTANCE_RANGES: dict[str, tuple[float, float]] = {
    "easy": (500.0, 1200.0),
    "medium": (1200.0, 1800.0),
    "hard": (1800.0, 2500.0),
}

PUBLIC_DIFFICULTY_BANDS: dict[str, dict[str, float | None]] = {
    "easy": {
        "complexity_min": None,
        "complexity_max": 7.95,
        "max_anonymous_chain": 12.0,
    },
    "medium": {
        "complexity_min": 5.0,
        "complexity_max": 8.05,
        "max_anonymous_chain": 16.0,
    },
    "hard": {
        "complexity_min": 5.0,
        "complexity_max": None,
        "max_anonymous_chain": 24.0,
    },
}


def distance_bin(route_length_m: float) -> str | None:
    for label, (lower, upper) in DIFFICULTY_DISTANCE_RANGES.items():
        if lower <= route_length_m <= upper:
            return label
    return None


def classify_difficulty_v2(
    route_length_m: float,
    complexity_score: float,
    longest_anonymous_chain: int,
    turn_count: int,
) -> str | None:
    if turn_count < 1:
        return None
    label = distance_bin(route_length_m)
    if label is None:
        return None
    band = PUBLIC_DIFFICULTY_BANDS[label]
    complexity_min = band["complexity_min"]
    complexity_max = band["complexity_max"]
    max_anonymous_chain = band["max_anonymous_chain"]
    if complexity_min is not None and complexity_score < complexity_min:
        return None
    if complexity_max is not None and complexity_score > complexity_max:
        return None
    if longest_anonymous_chain > max_anonymous_chain:
        return None
    return label


def claimed_difficulty_matches(
    claimed_difficulty: str | None,
    route_length_m: float,
    complexity_score: float,
    longest_anonymous_chain: int,
    turn_count: int,
) -> bool:
    if not claimed_difficulty:
        return False
    observed = classify_difficulty_v2(
        route_length_m=route_length_m,
        complexity_score=complexity_score,
        longest_anonymous_chain=longest_anonymous_chain,
        turn_count=turn_count,
    )
    return observed == claimed_difficulty

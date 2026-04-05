from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .models import NavigationCommand

ORS_LINE_PATTERN = re.compile(
    r"Name: (?P<name>.*?), Instruction: (?P<instruction>.*?), Distance: (?P<distance>.*? meters), Time: (?P<duration>.*? seconds)"
)
DISTANCE_PATTERN = re.compile(r"(\d+\.\d+|\d+)\s+meters", re.IGNORECASE)
DURATION_PATTERN = re.compile(r"(\d+\.\d+|\d+)\s+seconds", re.IGNORECASE)
DIRECTION_PATTERN = re.compile(
    r"\b("
    r"north|south|east|west|northeast|northwest|southeast|southwest|"
    r"keep left|keep right|slight left|slight right|sharp left|sharp right|left|right|straight"
    r")\b",
    re.IGNORECASE,
)
ROUNDABOUT_EXIT_PATTERN = re.compile(r"take the\s+(\d+)(?:st|nd|rd|th)\s+exit", re.IGNORECASE)


def _clean_street_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" ,.;")).strip()


def _extract_streets(text: str, keyword: str) -> list[str]:
    pattern = re.compile(
        rf"\b{keyword}\s+(.+?)(?=\s+(?:on|continue|for|and)\b|[,.]|$)",
        re.IGNORECASE,
    )
    return [_clean_street_name(match.group(1)) for match in pattern.finditer(text)]


def instruction_to_natural_line(line: str) -> str | None:
    match = ORS_LINE_PATTERN.match(line.strip())
    if not match:
        return None
    name = match.group("name").strip()
    instruction = match.group("instruction").strip()
    distance = match.group("distance").strip()
    duration = match.group("duration").strip()
    if name == "-" or name.upper() == "N/A":
        return f"{instruction}, continue for {distance} and taking about {duration}."
    return f"{instruction} on {name}, continue for {distance} and taking about {duration}."


def normalize_instruction_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"\s+", " ", line)
    if line and not line.endswith("."):
        line += "."
    return line


def _instruction_kind(lower: str) -> str:
    if "roundabout" in lower:
        return "roundabout_exit"
    return "normal"


def _turn_strength(directions: list[str], instruction_kind: str) -> str | None:
    if instruction_kind == "roundabout_exit":
        return "roundabout"
    if not directions:
        return None
    direction = directions[0]
    if direction.startswith("keep"):
        return "keep"
    if direction.startswith("slight"):
        return "slight"
    if direction.startswith("sharp"):
        return "sharp"
    if direction in {"left", "right"}:
        return "turn"
    if direction in {"straight", "continue straight"}:
        return "straight"
    return None


def parse_instruction(text: str) -> NavigationCommand:
    normalized = normalize_instruction_line(text)
    lower = normalized.lower()
    instruction_kind = _instruction_kind(lower)
    actions: list[str] = []
    if "arrive" in lower:
        actions.append("arrive")
    elif instruction_kind == "roundabout_exit":
        actions.append("turn")
    elif "head" in lower:
        actions.append("head")
    elif "turn" in lower:
        actions.append("turn")
    elif "keep" in lower or "continue" in lower:
        actions.append("continue")
    elif "walk" in lower:
        actions.append("head")
    if "continue" in lower and "continue" not in actions:
        actions.append("continue")
    directions = [" ".join(match.group(1).lower().split()) for match in DIRECTION_PATTERN.finditer(normalized)]
    start_streets = _extract_streets(normalized, "on")
    end_streets = _extract_streets(normalized, "onto") + _extract_streets(normalized, "to") + _extract_streets(normalized, "at")
    street_targets: list[str] = []
    for street in [*end_streets, *start_streets]:
        if street and street not in street_targets:
            street_targets.append(street)
    distances = [float(item) for item in DISTANCE_PATTERN.findall(normalized)]
    durations = [float(item) for item in DURATION_PATTERN.findall(normalized)]
    roundabout_match = ROUNDABOUT_EXIT_PATTERN.search(normalized)
    roundabout_exit_index = int(roundabout_match.group(1)) if roundabout_match else None
    return NavigationCommand(
        actions=actions,
        directions=directions,
        start_streets=start_streets,
        end_streets=end_streets,
        street_targets=street_targets,
        distances=distances,
        durations=durations,
        instruction_kind=instruction_kind,
        roundabout_exit_index=roundabout_exit_index,
        turn_strength=_turn_strength(directions, instruction_kind),
        raw_text=normalized,
    )


def parse_instruction_lines(lines: Iterable[str]) -> list[NavigationCommand]:
    return [parse_instruction(line) for line in lines if line.strip()]


def parse_instruction_file(path: str | Path) -> list[NavigationCommand]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return parse_instruction_lines(lines)


def load_legacy_parsed_instructions(path: str | Path) -> list[NavigationCommand]:
    content = Path(path).read_text(encoding="utf-8").strip()
    if not content:
        return []
    wrapped = "[" + content.replace("}\n{", "},\n{").rstrip(",") + "]"
    parsed = json.loads(wrapped)
    return [NavigationCommand.from_mapping(item) for item in parsed]


def write_parsed_instructions(path: str | Path, commands: Iterable[NavigationCommand]) -> None:
    lines = [json.dumps(command.to_dict(), ensure_ascii=False) for command in commands]
    Path(path).write_text(",\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def extract_ors_steps(route_geojson: dict) -> list[dict]:
    records: list[dict] = []
    for feature in route_geojson.get("features", []):
        props = feature.get("properties", {}) or {}
        for segment in props.get("segments", []) or []:
            for step in segment.get("steps", []) or []:
                records.append(
                    {
                        "name": step.get("name") or "N/A",
                        "instruction": step.get("instruction") or "No instruction provided",
                        "distance": float(step.get("distance", 0.0)),
                        "duration": float(step.get("duration", 0.0)),
                    }
                )
    return records


def format_ors_steps_as_instruction_lines(route_geojson: dict) -> list[str]:
    lines = []
    for step in extract_ors_steps(route_geojson):
        lines.append(
            f"Name: {step['name']}, Instruction: {step['instruction']}, "
            f"Distance: {step['distance']} meters, Time: {step['duration']} seconds"
        )
    return lines


def format_ors_steps_as_natural_lines(route_geojson: dict) -> list[str]:
    natural_lines: list[str] = []
    for raw_line in format_ors_steps_as_instruction_lines(route_geojson):
        natural = instruction_to_natural_line(raw_line)
        if natural:
            natural_lines.append(natural)
    return natural_lines

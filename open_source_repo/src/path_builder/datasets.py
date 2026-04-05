from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from .instructions import (
    format_ors_steps_as_instruction_lines,
    format_ors_steps_as_natural_lines,
    load_legacy_parsed_instructions,
    parse_instruction_file,
    parse_instruction_lines,
)
from .io import load_geojson
from .models import DatasetExample, NavigationCommand

ROUTE_FILE_NAMES = ("route.geojson", "instructions.txt", "natural_instructions.txt", "instructions_parse.txt", "reverse_route_Gemini.txt")


def dataset_root(path: str | Path = "data_set") -> Path:
    return Path(path)


def list_example_ids(root: str | Path = "data_set") -> list[str]:
    base = dataset_root(root)
    return sorted([item.name for item in base.iterdir() if item.is_dir()], key=lambda value: int(value))


def list_36k_examples(
    root: str | Path = "36kroutes",
    cities: Iterable[str] | None = None,
    difficulties: Iterable[str] | None = None,
) -> list[tuple[str, str, str]]:
    base = Path(root)
    city_filter = set(cities or [])
    difficulty_filter = set(difficulties or [])
    records: list[tuple[str, str, str]] = []
    for city_dir in sorted([item for item in base.iterdir() if item.is_dir()]):
        if city_filter and city_dir.name not in city_filter:
            continue
        for difficulty_dir in sorted([item for item in city_dir.iterdir() if item.is_dir()]):
            if difficulty_filter and difficulty_dir.name not in difficulty_filter:
                continue
            for example_dir in sorted([item for item in difficulty_dir.iterdir() if item.is_dir()], key=lambda value: int(value.name)):
                records.append((city_dir.name, difficulty_dir.name, example_dir.name))
    return records


def get_start_end_points(route_geojson: dict) -> tuple[tuple[float, float], tuple[float, float]] | tuple[None, None]:
    coordinates = route_geojson.get("metadata", {}).get("query", {}).get("coordinates", [])
    if len(coordinates) < 2:
        return None, None
    return tuple(coordinates[0]), tuple(coordinates[1])  # type: ignore[return-value]


def _build_example(
    *,
    corpus: str,
    example_id: str,
    root: Path,
    city: str | None = None,
    difficulty: str | None = None,
) -> DatasetExample:
    route_geojson_path = root / "route.geojson"
    route_geojson = load_geojson(route_geojson_path) if route_geojson_path.exists() else {}
    start, end = get_start_end_points(route_geojson)
    reverse_route_path = root / "reverse_route_Gemini.txt"
    if not reverse_route_path.exists():
        reverse_route_path = None
    instructions_path = root / "instructions.txt"
    natural_path = root / "natural_instructions.txt"
    parsed_path = root / "instructions_parse.txt"
    return DatasetExample(
        corpus=corpus,
        example_id=str(example_id),
        root=root,
        route_geojson_path=route_geojson_path,
        instructions_path=instructions_path if instructions_path.exists() else None,
        natural_instructions_path=natural_path if natural_path.exists() else None,
        parsed_instructions_path=parsed_path if parsed_path.exists() else None,
        reverse_route_path=reverse_route_path,
        start=start,
        end=end,
        city=city,
        difficulty=difficulty,
    )


def load_example(example_id: str | int, root: str | Path = "data_set") -> DatasetExample:
    example_id = str(example_id)
    base = dataset_root(root) / example_id
    return _build_example(corpus="data_set", example_id=example_id, root=base)


def load_36k_example(city: str, difficulty: str, example_id: str | int, root: str | Path = "36kroutes") -> DatasetExample:
    example_id = str(example_id)
    base = Path(root) / city / difficulty / example_id
    return _build_example(corpus="36kroutes", example_id=example_id, root=base, city=city, difficulty=difficulty)


def load_route_example(path: str | Path, *, corpus: str = "custom", city: str | None = None, difficulty: str | None = None) -> DatasetExample:
    root = Path(path)
    return _build_example(corpus=corpus, example_id=root.name, root=root, city=city, difficulty=difficulty)


def iter_corpus_examples(
    corpus: str,
    *,
    root: str | Path | None = None,
    cities: Iterable[str] | None = None,
    difficulties: Iterable[str] | None = None,
) -> list[DatasetExample]:
    if corpus == "data_set":
        base = root or "data_set"
        return [load_example(example_id, root=base) for example_id in list_example_ids(base)]
    if corpus == "36kroutes":
        base = root or "36kroutes"
        return [load_36k_example(city, difficulty, example_id, root=base) for city, difficulty, example_id in list_36k_examples(base, cities=cities, difficulties=difficulties)]
    raise ValueError(f"Unsupported corpus: {corpus}")


def load_reference_route(example: DatasetExample) -> dict:
    return load_geojson(example.route_geojson_path)


def load_instruction_lines(example: DatasetExample) -> list[str]:
    if example.instructions_path and example.instructions_path.exists():
        return [line.strip() for line in example.instructions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    route_geojson = load_reference_route(example)
    return format_ors_steps_as_instruction_lines(route_geojson)


def load_natural_instructions(example: DatasetExample) -> list[str]:
    if example.natural_instructions_path and example.natural_instructions_path.exists():
        return [line.strip() for line in example.natural_instructions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    route_geojson = load_reference_route(example)
    natural = format_ors_steps_as_natural_lines(route_geojson)
    if natural:
        return natural
    raw = load_instruction_lines(example)
    return raw


def load_parsed_instructions(example: DatasetExample) -> list[NavigationCommand]:
    natural = load_natural_instructions(example)
    if natural:
        return parse_instruction_lines(natural)
    if example.parsed_instructions_path and example.parsed_instructions_path.exists():
        return load_legacy_parsed_instructions(example.parsed_instructions_path)
    if example.instructions_path and example.instructions_path.exists():
        return parse_instruction_file(example.instructions_path)
    return []


def load_reverse_route_text(example: DatasetExample) -> str | None:
    if not example.reverse_route_path:
        return None
    return example.reverse_route_path.read_text(encoding="utf-8")


def load_reverse_route_commands(example: DatasetExample) -> list[NavigationCommand]:
    raw = load_reverse_route_text(example)
    if not raw:
        return []
    from .prompting import extract_instruction_lines_from_response

    cleaned_lines = extract_instruction_lines_from_response(raw)
    if cleaned_lines:
        return parse_instruction_lines(cleaned_lines)
    if not example.reverse_route_path:
        return []
    return parse_instruction_file(example.reverse_route_path)


def dataset_summary(root: str | Path = "data_set") -> dict[str, int]:
    counts: Counter[str] = Counter()
    folders = 0
    for example_id in list_example_ids(root):
        folders += 1
        folder = dataset_root(root) / example_id
        for name in ROUTE_FILE_NAMES:
            if (folder / name).exists():
                counts[name] += 1
    counts["examples"] = folders
    return dict(counts)


def corpus_summary(corpus: str, root: str | Path | None = None) -> dict[str, int]:
    if corpus == "data_set":
        return dataset_summary(root or "data_set")
    if corpus != "36kroutes":
        raise ValueError(f"Unsupported corpus: {corpus}")
    base = Path(root or "36kroutes")
    counts: Counter[str] = Counter()
    cities = 0
    route_folders = 0
    for city_dir in sorted([item for item in base.iterdir() if item.is_dir()]):
        cities += 1
        counts["cities"] = cities
        for difficulty_dir in sorted([item for item in city_dir.iterdir() if item.is_dir()]):
            counts[f"difficulty:{difficulty_dir.name}"] += 1
            for route_dir in sorted([item for item in difficulty_dir.iterdir() if item.is_dir()]):
                route_folders += 1
                for name in ("route.geojson", "instructions.txt"):
                    if (route_dir / name).exists():
                        counts[name] += 1
    counts["examples"] = route_folders
    return dict(counts)


def iter_36k_route_sets(root: str | Path = "36kroutes") -> Iterable[tuple[str, str, Path]]:
    base = Path(root)
    for city_dir in sorted([item for item in base.iterdir() if item.is_dir()]):
        for difficulty_dir in sorted([item for item in city_dir.iterdir() if item.is_dir()]):
            yield city_dir.name, difficulty_dir.name, difficulty_dir

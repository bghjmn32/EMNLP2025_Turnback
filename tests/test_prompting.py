import json
from pathlib import Path

from path_builder.datasets import load_reverse_route_commands, load_route_example
from path_builder.prompting import extract_instruction_lines_from_response


def test_extract_instruction_lines_from_response_stops_at_confidence():
    response = """
    Here's the reverse walk.

    Head east for 50 meters
    Turn right for 20 meters
    Arrive at your destination
    Confidence: 82%
    Explanation: inferred from the geometry.
    """.strip()

    lines = extract_instruction_lines_from_response(response)

    assert lines == [
        "Head east for 50 meters.",
        "Turn right for 20 meters.",
        "Arrive at your destination.",
    ]


def test_load_reverse_route_commands_cleans_provider_response(tmp_path: Path):
    route_dir = tmp_path / "example"
    route_dir.mkdir()
    route_geojson = {
        "type": "FeatureCollection",
        "metadata": {"query": {"coordinates": [[12.0, 41.0], [12.001, 41.001]]}},
        "features": [],
    }
    (route_dir / "route.geojson").write_text(json.dumps(route_geojson), encoding="utf-8")
    (route_dir / "reverse_route_Gemini.txt").write_text(
        "\n".join(
            [
                "Reverse route:",
                "Head east for 50 meters",
                "Turn right for 20 meters",
                "Arrive at your destination",
                "Confidence: 82%",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    example = load_route_example(route_dir)
    commands = load_reverse_route_commands(example)

    assert [command.primary_action for command in commands] == ["head", "turn", "arrive"]

from pathlib import Path

from path_builder.instructions import instruction_to_natural_line, load_legacy_parsed_instructions, parse_instruction


def test_instruction_to_natural_line_preserves_legacy_format():
    raw = "Name: Weddigenstraße, Instruction: Turn right onto Weddigenstraße, Distance: 11.6 meters, Time: 8.3 seconds"
    assert instruction_to_natural_line(raw) == "Turn right onto Weddigenstraße on Weddigenstraße, continue for 11.6 meters and taking about 8.3 seconds."


def test_parse_instruction_extracts_direction_and_streets():
    command = parse_instruction("Turn slight left onto Gleißnerstraße on Gleißnerstraße, continue for 13.4 meters and taking about 9.7 seconds.")
    assert command.primary_action == "turn"
    assert command.primary_direction == "slight left"
    assert command.start_streets == ["Gleißnerstraße"]
    assert "Gleißnerstraße" in command.end_streets
    assert command.primary_distance == 13.4


def test_parse_instruction_preserves_keep_direction():
    command = parse_instruction("Keep right, continue for 334.2 meters and taking about 240.6 seconds.")
    assert command.primary_action == "continue"
    assert command.primary_direction == "keep right"
    assert command.turn_strength == "keep"


def test_parse_instruction_extracts_roundabout_exit_and_street_targets():
    command = parse_instruction("Enter the roundabout and take the 2nd exit onto Tunnelweg, continue for 183.4 meters and taking about 132.1 seconds.")
    assert command.primary_action == "turn"
    assert command.instruction_kind == "roundabout_exit"
    assert command.roundabout_exit_index == 2
    assert command.turn_strength == "roundabout"
    assert command.street_targets == ["Tunnelweg"]


def test_load_legacy_parsed_instructions(tmp_path: Path):
    payload = (
        '{"actions": ["Head", "continue"], "directions": ["north"], "start_streets": [], "end_streets": [], "distances": [12.0], "durations": [8.0]},\n'
        '{"actions": ["Arrive"], "directions": [], "start_streets": [], "end_streets": [], "distances": [0.0], "durations": [0.0]}\n'
    )
    path = tmp_path / "instructions_parse.txt"
    path.write_text(payload, encoding="utf-8")
    commands = load_legacy_parsed_instructions(path)
    assert len(commands) == 2
    assert commands[0].primary_action == "head"
    assert commands[1].primary_action == "arrive"

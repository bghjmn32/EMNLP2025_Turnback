import json

import pytest

from path_builder.cli import build_parser, main
def test_execute_parser_accepts_hybrid_executor():
    parser = build_parser()
    args = parser.parse_args(
        [
            "execute",
            "0",
            "--city",
            "Toronto_Canada",
            "--difficulty",
            "easy",
            "--instructions",
            "reverse.txt",
            "--executor",
            "hybrid",
        ]
    )
    assert args.command == "execute"
    assert args.executor == "hybrid"
    assert args.root == "36kroutes"


def test_removed_auxiliary_commands_are_not_exposed():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["audit-corpus"])
    with pytest.raises(SystemExit):
        parser.parse_args(["corpus-summary"])
    with pytest.raises(SystemExit):
        parser.parse_args(["plot-routes"])


def test_generate_routes_parser_accepts_expected_arguments():
    parser = build_parser()
    args = parser.parse_args(
        [
            "generate-routes",
            "--city",
            "Toronto_Canada",
            "--city",
            "Tokyo_23_wards",
            "--easy",
            "20",
            "--medium",
            "20",
            "--hard",
            "20",
            "--output-root",
            "tmp/routes",
            "--paper-valid-gate",
            "0.88",
            "--max-graph-repulls",
            "2",
            "--oversample-factor",
            "5",
            "--network-type",
            "walk",
            "--max-endpoints-per-start",
            "12",
            "--max-start-attempts",
            "50000",
            "--probe-sample-size",
            "16",
            "--pb-executor",
            "search",
            "--disable-pb-recoverable-filter",
            "--progress",
        ]
    )
    assert args.command == "generate-routes"
    assert args.cities == ["Toronto_Canada", "Tokyo_23_wards"]
    assert args.easy == 20
    assert args.medium == 20
    assert args.hard == 20
    assert args.output_root == "tmp/routes"
    assert args.paper_valid_gate == 0.88
    assert args.max_graph_repulls == 2
    assert args.oversample_factor == 5
    assert args.max_endpoints_per_start == 12
    assert args.max_start_attempts == 50_000
    assert args.probe_sample_size == 16
    assert args.pb_executor == "search"
    assert args.disable_pb_recoverable_filter is True
    assert args.progress is True


def test_generate_routes_main_returns_nonzero_when_city_generation_fails(monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    monkeypatch.setattr(
        "path_builder.cli.generate_routes_pipeline",
        lambda *_args, **_kwargs: {"overall": {"all_cities_success": False}},
    )
    exit_code = main(["generate-routes", "--city", "Toronto_Canada", "--easy", "1"])
    assert exit_code == 1


def test_generate_reverse_main_reports_cleaned_lines(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "input.txt"
    input_path.write_text("Walk north.", encoding="utf-8")

    class _FakeProvider:
        def generate(self, city, instructions):
            assert city == "Toronto, Canada"
            assert instructions == "Walk north."
            return "Head south for 20 meters.\nArrive at the destination.\nConfidence: 90%"

    monkeypatch.setattr("path_builder.cli.create_reverse_route_provider", lambda *_args, **_kwargs: _FakeProvider())
    exit_code = main(
        [
            "generate-reverse",
            "--provider",
            "openai",
            "--city",
            "Toronto, Canada",
            "--input-file",
            str(input_path),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "openai"
    assert payload["cleaned_lines"] >= 1

import json

from path_builder.models import CorpusEvaluationSummary
from path_builder.cli import build_parser, main


def test_evaluate_dataset_parser_accepts_snapshot_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "evaluate-dataset",
            "--root",
            "data_set",
            "--snapshot-dir",
            "graph_snapshots",
            "--refresh-snapshots",
            "--jobs",
            "2",
            "--executor",
            "search",
        ]
    )
    assert args.command == "evaluate-dataset"
    assert args.snapshot_dir == "graph_snapshots"
    assert args.refresh_snapshots is True
    assert args.jobs == 2
    assert args.executor == "search"


def test_execute_parser_accepts_hybrid_executor():
    parser = build_parser()
    args = parser.parse_args(
        [
            "execute",
            "0",
            "--instructions",
            "parsed.jsonl",
            "--executor",
            "hybrid",
        ]
    )
    assert args.command == "execute"
    assert args.executor == "hybrid"


def test_freeze_graphs_parser_accepts_corpus_snapshot_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "freeze-graphs",
            "--corpus",
            "data_set",
            "--snapshot-dir",
            "graph_snapshots",
            "--limit",
            "10",
        ]
    )
    assert args.command == "freeze-graphs"
    assert args.corpus == "data_set"
    assert args.snapshot_dir == "graph_snapshots"
    assert args.limit == 10


def test_repro_summary_parser_uses_default_config():
    parser = build_parser()
    args = parser.parse_args(
        [
            "repro-summary",
            "benchmark_assets/reproduction/baseline/data_set_first12_frozen.csv",
        ]
    )
    assert args.command == "repro-summary"
    assert args.config == "configs/reproduction.first12.json"


def test_repro_check_parser_accepts_strict_and_baseline_override():
    parser = build_parser()
    args = parser.parse_args(
        [
            "repro-check",
            "candidate.csv",
            "--baseline",
            "baseline.csv",
            "--strict",
        ]
    )
    assert args.command == "repro-check"
    assert args.candidate == "candidate.csv"
    assert args.baseline == "baseline.csv"
    assert args.strict is True


def test_evaluate_corpus_parser_accepts_manifest_and_executor():
    parser = build_parser()
    args = parser.parse_args(
        [
            "evaluate-corpus",
            "--corpus",
            "36kroutes",
            "--city",
            "Toronto_Canada",
            "--manifest",
            "paper_valid.json",
            "--pb-recoverable-only",
            "--jobs",
            "4",
            "--executor",
            "search",
        ]
    )
    assert args.command == "evaluate-corpus"
    assert args.manifest == "paper_valid.json"
    assert args.pb_recoverable_only is True
    assert args.jobs == 4
    assert args.executor == "search"


def test_audit_and_calibrate_parsers_accept_expected_arguments():
    parser = build_parser()
    audit_args = parser.parse_args(
        [
            "audit-corpus",
            "--corpus",
            "36kroutes",
            "--pb-check",
            "--snapshot-dir",
            "cache/graph_snapshots",
            "--pb-executor",
            "hybrid",
            "--shared-graph",
            "--progress",
            "--jobs",
            "3",
            "--output",
            "audit.json",
        ]
    )
    assert audit_args.command == "audit-corpus"
    assert audit_args.pb_check is True
    assert audit_args.snapshot_dir == "cache/graph_snapshots"
    assert audit_args.pb_executor == "hybrid"
    assert audit_args.shared_graph is True
    assert audit_args.progress is True
    assert audit_args.jobs == 3
    assert audit_args.output == "audit.json"

    calibrate_args = parser.parse_args(
        [
            "calibrate-similarity",
            "--corpus",
            "36kroutes",
            "--manifest",
            "paper_valid.json",
            "--pb-recoverable-only",
            "--executor",
            "search",
            "--shared-graph",
            "--jobs",
            "2",
            "--config",
            "configs/similarity.paper.json",
            "--config",
            "configs/similarity.loose.json",
        ]
    )
    assert calibrate_args.command == "calibrate-similarity"
    assert calibrate_args.manifest == "paper_valid.json"
    assert calibrate_args.pb_recoverable_only is True
    assert calibrate_args.executor == "search"
    assert calibrate_args.shared_graph is True
    assert calibrate_args.jobs == 2
    assert calibrate_args.configs == ["configs/similarity.paper.json", "configs/similarity.loose.json"]


def test_select_audit_subset_parser_accepts_balancing_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "select-audit-subset",
            "--manifest",
            "paper_valid.json",
            "--output",
            "subset.json",
            "--city",
            "Toronto_Canada",
            "--difficulty",
            "easy",
            "--pb-recoverable-only",
            "--per-city-difficulty",
            "12",
        ]
    )
    assert args.command == "select-audit-subset"
    assert args.manifest == "paper_valid.json"
    assert args.output == "subset.json"
    assert args.cities == ["Toronto_Canada"]
    assert args.difficulties == ["easy"]
    assert args.pb_recoverable_only is True
    assert args.per_city_difficulty == 12


def test_diagnose_ceiling_parser_accepts_snapshot_dir():
    parser = build_parser()
    args = parser.parse_args(
        [
            "diagnose-ceiling",
            "5",
            "--root",
            "data_set",
            "--snapshot-dir",
            "cache/graph_snapshots",
        ]
    )
    assert args.command == "diagnose-ceiling"
    assert args.example_id == "5"
    assert args.snapshot_dir == "cache/graph_snapshots"


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


def test_select_audit_subset_main_writes_filtered_manifest(tmp_path):
    manifest_path = tmp_path / "audit.json"
    output_path = tmp_path / "subset.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "records": [
                    {
                        "corpus": "36kroutes",
                        "example_id": "1",
                        "source_difficulty": "easy",
                        "difficulty_v2": "easy",
                        "paper_valid": True,
                        "invalid_reasons": [],
                        "route_length_m": 800.0,
                        "step_count": 4,
                        "turn_count": 2,
                        "named_step_ratio": 0.75,
                        "anonymous_turn_ratio": 0.25,
                        "longest_anonymous_chain": 1,
                        "roundabout_count": 0,
                        "keep_count": 0,
                        "short_turn_count": 0,
                        "turn_density_per_km": 2.0,
                        "complexity_score": 6.0,
                        "city": "Toronto_Canada",
                        "pb_recoverable": True,
                    },
                    {
                        "corpus": "36kroutes",
                        "example_id": "2",
                        "source_difficulty": "easy",
                        "difficulty_v2": "easy",
                        "paper_valid": True,
                        "invalid_reasons": [],
                        "route_length_m": 820.0,
                        "step_count": 4,
                        "turn_count": 2,
                        "named_step_ratio": 0.75,
                        "anonymous_turn_ratio": 0.25,
                        "longest_anonymous_chain": 1,
                        "roundabout_count": 0,
                        "keep_count": 0,
                        "short_turn_count": 0,
                        "turn_density_per_km": 2.0,
                        "complexity_score": 6.5,
                        "city": "Toronto_Canada",
                        "pb_recoverable": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "select-audit-subset",
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--city",
            "Toronto_Canada",
            "--difficulty",
            "easy",
            "--pb-recoverable-only",
        ]
    )
    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [record["example_id"] for record in payload["records"]] == ["1"]


def test_evaluate_corpus_main_reports_metrics_and_forwards_jobs(monkeypatch, capsys, tmp_path):
    observed: dict[str, object] = {}

    monkeypatch.setattr("path_builder.cli.iter_corpus_examples", lambda *args, **kwargs: [])
    def _fake_evaluate_corpus(*args, **kwargs):
        observed["jobs"] = kwargs["jobs"]
        return []

    monkeypatch.setattr("path_builder.cli.evaluate_corpus", _fake_evaluate_corpus)
    monkeypatch.setattr("path_builder.cli.write_rows_csv", lambda rows, path: observed.setdefault("output", path))
    monkeypatch.setattr(
        "path_builder.cli.build_corpus_summary",
        lambda rows, success_threshold=85.0: CorpusEvaluationSummary(overall={"count": len(rows)}),
    )

    exit_code = main(
        [
            "evaluate-corpus",
            "--corpus",
            "data_set",
            "--output",
            str(tmp_path / "rows.csv"),
            "--jobs",
            "3",
        ]
    )

    assert exit_code == 0
    assert observed["jobs"] == 3
    payload = json.loads(capsys.readouterr().out)
    assert "wall_time_s" in payload
    assert "examples_per_second" in payload


def test_audit_corpus_main_reports_metrics_and_forwards_jobs(monkeypatch, capsys, tmp_path):
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        "path_builder.cli.iter_corpus_examples",
        lambda *args, **kwargs: [],
    )
    def _fake_audit_corpus(*args, **kwargs):
        observed["jobs"] = kwargs["jobs"]
        return []

    monkeypatch.setattr("path_builder.cli.audit_corpus", _fake_audit_corpus)
    monkeypatch.setattr("path_builder.cli.summarize_route_audit", lambda records: {"count": len(records)})
    monkeypatch.setattr("path_builder.cli.write_route_audit_manifest", lambda records, path: observed.setdefault("output", path))

    exit_code = main(
        [
            "audit-corpus",
            "--corpus",
            "data_set",
            "--jobs",
            "4",
            "--output",
            str(tmp_path / "audit.json"),
        ]
    )

    assert exit_code == 0
    assert observed["jobs"] == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["count"] == 0
    assert "wall_time_s" in payload
    assert "examples_per_second" in payload

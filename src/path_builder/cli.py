from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
import time

from .benchmark import plot_benchmark_grid
from .ceiling import analyze_execution_ceiling
from .datasets import corpus_summary, iter_corpus_examples, list_example_ids, load_example, load_parsed_instructions, load_route_example
from .evaluation import (
    build_corpus_summary,
    build_shared_graph_bundle,
    evaluate_corpus,
    evaluate_examples,
    freeze_graph_snapshots,
    load_shared_graph_cache_metadata,
    shared_graph_cache_keys_for_examples,
    write_rows_csv,
)
from .execution import PathBuilder, recommended_graph_dist
from .generation import generate_routes_pipeline
from .instructions import parse_instruction_file, write_parsed_instructions
from .io import load_geojson
from .models import ExecutionState, SimilarityThresholds, SimilarityWeights
from .paper import (
    audit_corpus,
    build_guardrail_records,
    filter_examples_by_manifest,
    load_route_audit_manifest,
    summarize_route_audit,
    write_route_audit_manifest,
)
from .prompting import (
    build_dataset_query,
    build_reverse_route_prompt,
    create_reverse_route_provider,
    write_reverse_route_outputs,
)
from .reproduction import (
    build_reproduction_summary,
    compare_reproduction_runs,
    load_evaluation_rows_csv,
    load_reproduction_config,
)
from .similarity import score_geojson_routes
from .visualization import plot_route_pair


def _load_weights(path: str | Path | None) -> tuple[SimilarityWeights, SimilarityThresholds]:
    if path is None:
        return SimilarityWeights(), SimilarityThresholds()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    weights = SimilarityWeights(**payload.get("weights", {}))
    thresholds = SimilarityThresholds(**payload.get("thresholds", {}))
    return weights, thresholds


def _shared_graph_metrics(metadata: dict[str, dict[str, str]]) -> dict[str, object]:
    if not metadata:
        return {}
    if len(metadata) == 1:
        entry = next(iter(metadata.values()))
        return {
            "shared_graph_cache_key": entry["cache_key"],
            "shared_graph_source": entry["graph_source"],
        }
    return {
        "shared_graph_cache_keys": {scope: entry["cache_key"] for scope, entry in sorted(metadata.items())},
        "shared_graph_sources": {scope: entry["graph_source"] for scope, entry in sorted(metadata.items())},
    }


def _run_metrics(start_time: float, *, count: int) -> dict[str, float]:
    wall_time_s = time.perf_counter() - start_time
    return {
        "wall_time_s": round(wall_time_s, 6),
        "examples_per_second": round(count / wall_time_s, 6) if wall_time_s > 0 else 0.0,
    }


def _prepare_shared_graph_context(
    *,
    corpus: str,
    root: str | Path,
    selected_examples: list[object],
    cities: list[str] | None,
    difficulties: list[str] | None,
    snapshot_dir: str | Path | None,
    network_type: str,
    progress: bool,
    jobs: int,
) -> tuple[object | None, dict[str, str] | None, dict[str, dict[str, str]], int]:
    effective_jobs = max(1, int(jobs))
    if not selected_examples:
        return None, None, {}, effective_jobs
    if effective_jobs > 1 and snapshot_dir is None:
        if progress:
            print("parallel shared-graph execution requires --snapshot-dir; falling back to serial execution.", flush=True)
        effective_jobs = 1
    builder = build_shared_graph_bundle(
        corpus,
        root=root,
        selected_examples=selected_examples,
        cities=cities,
        difficulties=difficulties,
        cache_dir=snapshot_dir,
        network_type=network_type,
        progress=progress,
    )
    cache_keys = (
        shared_graph_cache_keys_for_examples(
            corpus,
            selected_examples=selected_examples,
            difficulties=difficulties,
            network_type=network_type,
        )
        if snapshot_dir
        else None
    )
    metadata = load_shared_graph_cache_metadata(snapshot_dir, cache_keys or {})
    if effective_jobs > 1:
        return None, cache_keys, metadata, effective_jobs
    return builder, cache_keys, metadata, effective_jobs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="path-builder", description="Path Builder toolkit for TurnBack reproduction.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dataset_cmd = subparsers.add_parser("dataset-summary", help="Summarize the evaluation dataset.")
    dataset_cmd.add_argument("--root", default="data_set")

    corpus_cmd = subparsers.add_parser("corpus-summary", help="Summarize data_set or 36kroutes.")
    corpus_cmd.add_argument("--corpus", choices=["data_set", "36kroutes"], required=True)
    corpus_cmd.add_argument("--root")

    parse_cmd = subparsers.add_parser("parse-instructions", help="Parse a natural instruction file into legacy JSONL format.")
    parse_cmd.add_argument("input")
    parse_cmd.add_argument("output")

    prompt_cmd = subparsers.add_parser("build-prompt", help="Build a reverse-route prompt for one dataset example.")
    prompt_cmd.add_argument("example_id")
    prompt_cmd.add_argument("--root", default="data_set")
    prompt_cmd.add_argument("--city", required=True)

    reverse_cmd = subparsers.add_parser("generate-reverse", help="Call a configured provider and write raw + cleaned reverse-route outputs.")
    reverse_cmd.add_argument("--provider", choices=["openai", "gemini"], required=True)
    reverse_cmd.add_argument("--model")
    reverse_cmd.add_argument("--api-key")
    reverse_cmd.add_argument("--city", required=True)
    reverse_cmd.add_argument("--input-file")
    reverse_cmd.add_argument("--example-id")
    reverse_cmd.add_argument("--root", default="data_set")
    reverse_cmd.add_argument("--raw-output")
    reverse_cmd.add_argument("--clean-output")

    score_cmd = subparsers.add_parser("score", help="Score two GeoJSON routes with the public similarity implementation.")
    score_cmd.add_argument("prediction")
    score_cmd.add_argument("reference")
    score_cmd.add_argument("--config")

    visualize_cmd = subparsers.add_parser("plot-routes", help="Plot an overlay of a predicted route and a reference route.")
    visualize_cmd.add_argument("prediction")
    visualize_cmd.add_argument("reference")
    visualize_cmd.add_argument("output")
    visualize_cmd.add_argument("--title", default="Route Comparison")

    evaluate_cmd = subparsers.add_parser("evaluate-dataset", help="Compatibility wrapper around evaluate-corpus --corpus data_set.")
    evaluate_cmd.add_argument("--root", default="data_set")
    evaluate_cmd.add_argument("--limit", type=int, default=25)
    evaluate_cmd.add_argument("--offset", type=int, default=0)
    evaluate_cmd.add_argument("--output", default="benchmark_assets/path_builder_eval.csv")
    evaluate_cmd.add_argument("--overlay-dir")
    evaluate_cmd.add_argument("--overlay-threshold", type=float, default=75.0)
    evaluate_cmd.add_argument("--shared-graph", action="store_true")
    evaluate_cmd.add_argument("--snapshot-dir")
    evaluate_cmd.add_argument("--refresh-snapshots", action="store_true")
    evaluate_cmd.add_argument("--dist", type=int, default=1200)
    evaluate_cmd.add_argument("--progress", action="store_true")
    evaluate_cmd.add_argument("--jobs", type=int, default=1)
    evaluate_cmd.add_argument("--config")
    evaluate_cmd.add_argument("--executor", choices=["greedy", "search", "hybrid"], default="greedy")
    evaluate_cmd.add_argument("--success-threshold", type=float, default=85.0)

    corpus_eval_cmd = subparsers.add_parser("evaluate-corpus", help="Batch-execute Path Builder over data_set or 36kroutes.")
    corpus_eval_cmd.add_argument("--corpus", choices=["data_set", "36kroutes"], required=True)
    corpus_eval_cmd.add_argument("--root")
    corpus_eval_cmd.add_argument("--city", action="append", dest="cities")
    corpus_eval_cmd.add_argument("--difficulty", action="append", dest="difficulties")
    corpus_eval_cmd.add_argument("--limit", type=int)
    corpus_eval_cmd.add_argument("--offset", type=int, default=0)
    corpus_eval_cmd.add_argument("--output", default="benchmark_assets/path_builder_eval.csv")
    corpus_eval_cmd.add_argument("--overlay-dir")
    corpus_eval_cmd.add_argument("--overlay-threshold", type=float, default=75.0)
    corpus_eval_cmd.add_argument("--shared-graph", action="store_true")
    corpus_eval_cmd.add_argument("--snapshot-dir")
    corpus_eval_cmd.add_argument("--refresh-snapshots", action="store_true")
    corpus_eval_cmd.add_argument("--dist", type=int, default=1200)
    corpus_eval_cmd.add_argument("--progress", action="store_true")
    corpus_eval_cmd.add_argument("--jobs", type=int, default=1)
    corpus_eval_cmd.add_argument("--config")
    corpus_eval_cmd.add_argument("--executor", choices=["greedy", "search", "hybrid"], default="greedy")
    corpus_eval_cmd.add_argument("--manifest")
    corpus_eval_cmd.add_argument("--all-manifest-records", action="store_true")
    corpus_eval_cmd.add_argument("--pb-recoverable-only", action="store_true")
    corpus_eval_cmd.add_argument("--success-threshold", type=float, default=85.0)

    freeze_cmd = subparsers.add_parser("freeze-graphs", help="Precompute and store frozen OSM graph snapshots for a corpus.")
    freeze_cmd.add_argument("--corpus", choices=["data_set", "36kroutes"], required=True)
    freeze_cmd.add_argument("--root")
    freeze_cmd.add_argument("--city", action="append", dest="cities")
    freeze_cmd.add_argument("--difficulty", action="append", dest="difficulties")
    freeze_cmd.add_argument("--limit", type=int)
    freeze_cmd.add_argument("--offset", type=int, default=0)
    freeze_cmd.add_argument("--snapshot-dir", required=True)
    freeze_cmd.add_argument("--refresh-snapshots", action="store_true")
    freeze_cmd.add_argument("--dist", type=int, default=1200)
    freeze_cmd.add_argument("--progress", action="store_true")
    freeze_cmd.add_argument("--manifest")
    freeze_cmd.add_argument("--all-manifest-records", action="store_true")
    freeze_cmd.add_argument("--pb-recoverable-only", action="store_true")

    execute_cmd = subparsers.add_parser("execute", help="Execute parsed instructions against an OSM street graph.")
    execute_cmd.add_argument("example_id", nargs="?")
    execute_cmd.add_argument("--corpus", choices=["data_set", "36kroutes"], default="data_set")
    execute_cmd.add_argument("--root")
    execute_cmd.add_argument("--route-dir")
    execute_cmd.add_argument("--city")
    execute_cmd.add_argument("--difficulty")
    execute_cmd.add_argument("--instructions", default="instructions_parse.txt")
    execute_cmd.add_argument("--start", choices=["start", "end"], default="start")
    execute_cmd.add_argument("--output", default="answer_path_builder.geojson")
    execute_cmd.add_argument("--dist", type=int, default=1000)
    execute_cmd.add_argument("--executor", choices=["greedy", "search", "hybrid"], default="greedy")

    ceiling_cmd = subparsers.add_parser("diagnose-ceiling", help="Inspect structural ceiling signals for one execution example.")
    ceiling_cmd.add_argument("example_id")
    ceiling_cmd.add_argument("--root", default="data_set")
    ceiling_cmd.add_argument("--snapshot-dir")
    ceiling_cmd.add_argument("--dist", type=int, default=1200)

    benchmark_cmd = subparsers.add_parser("plot-benchmark", help="Plot the paper benchmark grid from CSV histograms.")
    benchmark_cmd.add_argument("--root", default=".")
    benchmark_cmd.add_argument("--output", default="benchmark_grid.png")

    repro_summary_cmd = subparsers.add_parser("repro-summary", help="Summarize a benchmark CSV under the public reproduction contract.")
    repro_summary_cmd.add_argument("input")
    repro_summary_cmd.add_argument("--config", default="configs/reproduction.first12.json")

    repro_check_cmd = subparsers.add_parser("repro-check", help="Compare a candidate benchmark CSV against the public reproduction baseline.")
    repro_check_cmd.add_argument("candidate")
    repro_check_cmd.add_argument("--config", default="configs/reproduction.first12.json")
    repro_check_cmd.add_argument("--baseline")
    repro_check_cmd.add_argument("--strict", action="store_true")

    audit_cmd = subparsers.add_parser("audit-corpus", help="Audit a corpus into paper-valid route records and difficulty-v2 labels.")
    audit_cmd.add_argument("--corpus", choices=["data_set", "36kroutes"], required=True)
    audit_cmd.add_argument("--root")
    audit_cmd.add_argument("--city", action="append", dest="cities")
    audit_cmd.add_argument("--difficulty", action="append", dest="difficulties")
    audit_cmd.add_argument("--limit", type=int)
    audit_cmd.add_argument("--offset", type=int, default=0)
    audit_cmd.add_argument("--pb-check", action="store_true")
    audit_cmd.add_argument("--snapshot-dir")
    audit_cmd.add_argument("--dist", type=int, default=1200)
    audit_cmd.add_argument("--network-type", default="walk")
    audit_cmd.add_argument("--pb-executor", choices=["greedy", "search", "hybrid"], default="hybrid")
    audit_cmd.add_argument("--shared-graph", action="store_true")
    audit_cmd.add_argument("--progress", action="store_true")
    audit_cmd.add_argument("--jobs", type=int, default=1)
    audit_cmd.add_argument("--output")

    select_audit_cmd = subparsers.add_parser(
        "select-audit-subset",
        help="Filter or balance an audit manifest into a paper-facing subset manifest.",
    )
    select_audit_cmd.add_argument("--manifest", required=True)
    select_audit_cmd.add_argument("--output", required=True)
    select_audit_cmd.add_argument("--city", action="append", dest="cities")
    select_audit_cmd.add_argument("--difficulty", action="append", dest="difficulties")
    select_audit_cmd.add_argument("--all-records", action="store_true")
    select_audit_cmd.add_argument("--pb-recoverable-only", action="store_true")
    select_audit_cmd.add_argument("--per-city-difficulty", type=int)

    calibrate_cmd = subparsers.add_parser("calibrate-similarity", help="Evaluate multiple public similarity configs and select the best frozen candidate.")
    calibrate_cmd.add_argument("--corpus", choices=["data_set", "36kroutes"], required=True)
    calibrate_cmd.add_argument("--root")
    calibrate_cmd.add_argument("--city", action="append", dest="cities")
    calibrate_cmd.add_argument("--difficulty", action="append", dest="difficulties")
    calibrate_cmd.add_argument("--limit", type=int)
    calibrate_cmd.add_argument("--offset", type=int, default=0)
    calibrate_cmd.add_argument("--snapshot-dir")
    calibrate_cmd.add_argument("--refresh-snapshots", action="store_true")
    calibrate_cmd.add_argument("--dist", type=int, default=1200)
    calibrate_cmd.add_argument("--progress", action="store_true")
    calibrate_cmd.add_argument("--jobs", type=int, default=1)
    calibrate_cmd.add_argument("--shared-graph", action="store_true")
    calibrate_cmd.add_argument("--manifest")
    calibrate_cmd.add_argument("--all-manifest-records", action="store_true")
    calibrate_cmd.add_argument("--pb-recoverable-only", action="store_true")
    calibrate_cmd.add_argument("--executor", choices=["greedy", "search", "hybrid"], default="greedy")
    calibrate_cmd.add_argument("--success-threshold", type=float, default=85.0)
    calibrate_cmd.add_argument("--config", action="append", dest="configs", required=True)
    calibrate_cmd.add_argument("--output")

    generate_cmd = subparsers.add_parser(
        "generate-routes",
        help="Generate paper-valid 36k-style routes with probing, repulls, and manifest output.",
    )
    generate_cmd.add_argument("--city", action="append", dest="cities", required=True)
    generate_cmd.add_argument("--easy", type=int, default=0)
    generate_cmd.add_argument("--medium", type=int, default=0)
    generate_cmd.add_argument("--hard", type=int, default=0)
    generate_cmd.add_argument("--output-root", default="36kroutes")
    generate_cmd.add_argument("--seed", type=int, default=42)
    generate_cmd.add_argument("--paper-valid-gate", type=float, default=0.90)
    generate_cmd.add_argument("--max-graph-repulls", type=int, default=3)
    generate_cmd.add_argument("--oversample-factor", type=int, default=4)
    generate_cmd.add_argument("--network-type", default="walk")
    generate_cmd.add_argument("--max-endpoints-per-start", type=int, default=8)
    generate_cmd.add_argument("--max-start-attempts", type=int, default=20_000)
    generate_cmd.add_argument("--probe-sample-size", type=int, default=8)
    generate_cmd.add_argument("--disable-pb-recoverable-filter", action="store_true")
    generate_cmd.add_argument("--pb-executor", choices=["greedy", "search", "hybrid"], default="hybrid")
    generate_cmd.add_argument("--progress", action="store_true")
    generate_cmd.add_argument("--ors-api-key")
    return parser


def _load_execute_example(args) -> object:
    if args.route_dir:
        return load_route_example(args.route_dir, corpus=args.corpus, city=args.city, difficulty=args.difficulty)
    if args.example_id is None:
        raise ValueError("execute requires either an example_id or --route-dir.")
    if args.corpus == "36kroutes":
        if not args.city or not args.difficulty:
            raise ValueError("--city and --difficulty are required for --corpus 36kroutes.")
        from .datasets import load_36k_example

        return load_36k_example(args.city, args.difficulty, args.example_id, root=args.root or "36kroutes")
    return load_example(args.example_id, root=args.root or "data_set")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "dataset-summary":
        print(json.dumps(corpus_summary("data_set", root=args.root), indent=2, ensure_ascii=False))
        return 0

    if args.command == "corpus-summary":
        print(json.dumps(corpus_summary(args.corpus, root=args.root), indent=2, ensure_ascii=False))
        return 0

    if args.command == "parse-instructions":
        commands = parse_instruction_file(args.input)
        write_parsed_instructions(args.output, commands)
        print(f"Parsed {len(commands)} instructions into {args.output}")
        return 0

    if args.command == "build-prompt":
        print(build_reverse_route_prompt(args.city, build_dataset_query(args.example_id, root=args.root)))
        return 0

    if args.command == "generate-reverse":
        if not args.input_file and not args.example_id:
            raise ValueError("generate-reverse requires either --input-file or --example-id.")
        if args.input_file:
            instructions_text = Path(args.input_file).read_text(encoding="utf-8")
        else:
            instructions_text = build_dataset_query(args.example_id, root=args.root)
        provider = create_reverse_route_provider(args.provider, api_key=args.api_key, model_name=args.model)
        response_text = provider.generate(args.city, instructions_text)
        _, cleaned = write_reverse_route_outputs(response_text, raw_output_path=args.raw_output, clean_output_path=args.clean_output)
        print(json.dumps({"provider": args.provider, "cleaned_lines": len(cleaned.splitlines()) if cleaned else 0}, indent=2))
        return 0

    if args.command == "score":
        weights, thresholds = _load_weights(args.config)
        result = score_geojson_routes(load_geojson(args.prediction), load_geojson(args.reference), weights=weights, thresholds=thresholds)
        print(json.dumps({"similarity": result.similarity, "scores": result.scores, "weights": result.weights, "params": result.params}, indent=2))
        return 0

    if args.command == "plot-routes":
        plot_route_pair(load_geojson(args.reference), load_geojson(args.prediction), output_path=args.output, title=args.title)
        print(f"Wrote route overlay to {args.output}")
        return 0

    if args.command == "evaluate-dataset":
        start_time = time.perf_counter()
        weights, thresholds = _load_weights(args.config)
        available_ids = list_example_ids(args.root)
        selected = available_ids[args.offset : args.offset + args.limit]
        builder = None
        shared_cache_keys = None
        shared_metadata: dict[str, dict[str, str]] = {}
        effective_jobs = max(1, int(args.jobs))
        if args.shared_graph and selected:
            examples = [load_example(example_id, root=args.root) for example_id in selected]
            builder, shared_cache_keys, shared_metadata, effective_jobs = _prepare_shared_graph_context(
                corpus="data_set",
                root=args.root,
                selected_examples=examples,
                cities=None,
                difficulties=None,
                snapshot_dir=args.snapshot_dir,
                network_type="walk",
                progress=args.progress,
                jobs=args.jobs,
            )
        rows = evaluate_examples(
            selected,
            root=args.root,
            builder=builder,
            dist=args.dist,
            overlay_dir=args.overlay_dir,
            overlay_threshold=args.overlay_threshold,
            progress=args.progress,
            snapshot_dir=args.snapshot_dir,
            refresh_snapshots=args.refresh_snapshots,
            weights=weights,
            thresholds=thresholds,
            executor=args.executor,
            jobs=effective_jobs,
            shared_cache_keys=shared_cache_keys,
        )
        write_rows_csv(rows, args.output)
        print(
            json.dumps(
                {
                    **asdict(build_corpus_summary(rows, success_threshold=args.success_threshold)),
                    **_run_metrics(start_time, count=len(rows)),
                    **_shared_graph_metrics(shared_metadata),
                },
                indent=2,
            )
        )
        return 0

    if args.command == "evaluate-corpus":
        start_time = time.perf_counter()
        weights, thresholds = _load_weights(args.config)
        examples = iter_corpus_examples(args.corpus, root=args.root or args.corpus, cities=args.cities, difficulties=args.difficulties)
        if args.manifest:
            examples = filter_examples_by_manifest(
                examples,
                load_route_audit_manifest(args.manifest),
                paper_valid_only=not args.all_manifest_records,
                pb_recoverable_only=args.pb_recoverable_only,
            )
        selected_examples = examples[args.offset : args.offset + args.limit] if args.limit is not None else examples[args.offset:]
        builder = None
        shared_cache_keys = None
        shared_metadata: dict[str, dict[str, str]] = {}
        effective_jobs = max(1, int(args.jobs))
        if args.shared_graph and selected_examples:
            builder, shared_cache_keys, shared_metadata, effective_jobs = _prepare_shared_graph_context(
                corpus=args.corpus,
                root=args.root or args.corpus,
                selected_examples=selected_examples,
                cities=args.cities,
                difficulties=args.difficulties,
                snapshot_dir=args.snapshot_dir,
                network_type="walk",
                progress=args.progress,
                jobs=args.jobs,
            )
        rows = evaluate_corpus(
            args.corpus,
            root=args.root or args.corpus,
            builder=builder,
            dist=args.dist,
            weights=weights,
            thresholds=thresholds,
            overlay_dir=args.overlay_dir,
            overlay_threshold=args.overlay_threshold,
            progress=args.progress,
            snapshot_dir=args.snapshot_dir,
            refresh_snapshots=args.refresh_snapshots,
            cities=args.cities,
            difficulties=args.difficulties,
            limit=args.limit,
            offset=args.offset,
            manifest_path=args.manifest,
            paper_valid_only=not args.all_manifest_records,
            pb_recoverable_only=args.pb_recoverable_only,
            executor=args.executor,
            jobs=effective_jobs,
            shared_cache_keys=shared_cache_keys,
        )
        write_rows_csv(rows, args.output)
        print(
            json.dumps(
                {
                    **asdict(build_corpus_summary(rows, success_threshold=args.success_threshold)),
                    **_run_metrics(start_time, count=len(rows)),
                    **_shared_graph_metrics(shared_metadata),
                },
                indent=2,
            )
        )
        return 0

    if args.command == "freeze-graphs":
        summary = freeze_graph_snapshots(
            args.corpus,
            snapshot_dir=args.snapshot_dir,
            root=args.root or args.corpus,
            dist=args.dist,
            refresh_snapshots=args.refresh_snapshots,
            cities=args.cities,
            difficulties=args.difficulties,
            limit=args.limit,
            offset=args.offset,
            progress=args.progress,
            manifest_path=args.manifest,
            paper_valid_only=not args.all_manifest_records,
            pb_recoverable_only=args.pb_recoverable_only,
        )
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "execute":
        example = _load_execute_example(args)
        candidate = Path(args.instructions)
        if candidate.is_absolute():
            instruction_path = candidate
        elif candidate.exists():
            instruction_path = candidate
        else:
            instruction_path = example.root / args.instructions
        if example.parsed_instructions_path and instruction_path == example.parsed_instructions_path:
            commands = load_parsed_instructions(example)
        else:
            commands = parse_instruction_file(instruction_path)
        start = example.start if args.start == "start" else example.end
        if start is None:
            raise ValueError("Example does not contain route start/end metadata.")
        builder = PathBuilder.from_osm((start[1], start[0]), dist=max(args.dist, recommended_graph_dist(commands)))
        trace = builder.execute(commands, ExecutionState(current_coordinates=(start[1], start[0]), current_heading=0.0), executor=args.executor)
        output_path = example.root / args.output if not Path(args.output).is_absolute() else Path(args.output)
        builder.write_trace_geojson(trace, output_path)
        print(f"Wrote execution trace to {output_path}")
        return 0

    if args.command == "diagnose-ceiling":
        example = load_example(args.example_id, root=args.root)
        report = analyze_execution_ceiling(
            example,
            snapshot_dir=args.snapshot_dir,
            dist=args.dist,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if args.command == "plot-benchmark":
        plot_benchmark_grid(args.root, output_path=args.output)
        print(f"Wrote benchmark figure to {args.output}")
        return 0

    if args.command == "repro-summary":
        config = load_reproduction_config(args.config)
        rows = load_evaluation_rows_csv(args.input)
        summary = build_reproduction_summary(
            rows,
            failure_cluster_ids=config.failure_cluster_ids,
            protected_example_ids=config.protected_example_ids,
        )
        print(json.dumps({"config": config.name, "input": args.input, **summary}, indent=2))
        return 0

    if args.command == "repro-check":
        config = load_reproduction_config(args.config)
        baseline_path = Path(args.baseline) if args.baseline else config.baseline_csv
        report = compare_reproduction_runs(
            load_evaluation_rows_csv(baseline_path),
            load_evaluation_rows_csv(args.candidate),
            config,
        )
        print(
            json.dumps(
                {
                    "config": config.name,
                    "baseline_input": str(baseline_path),
                    "candidate_input": args.candidate,
                    **report,
                },
                indent=2,
            )
        )
        return 1 if args.strict and not report["passed"] else 0

    if args.command == "audit-corpus":
        start_time = time.perf_counter()
        selected_examples = iter_corpus_examples(
            args.corpus,
            root=args.root or args.corpus,
            cities=args.cities,
            difficulties=args.difficulties,
        )
        selected_examples = (
            selected_examples[args.offset : args.offset + args.limit]
            if args.limit is not None
            else selected_examples[args.offset:]
        )
        records = audit_corpus(
            args.corpus,
            root=args.root or args.corpus,
            cities=args.cities,
            difficulties=args.difficulties,
            limit=args.limit,
            offset=args.offset,
            pb_check=args.pb_check,
            snapshot_dir=args.snapshot_dir,
            dist=args.dist,
            network_type=args.network_type,
            executor=args.pb_executor,
            shared_graph=args.shared_graph,
            progress=args.progress,
            jobs=args.jobs,
        )
        shared_metadata: dict[str, dict[str, str]] = {}
        if args.shared_graph and selected_examples and args.snapshot_dir:
            shared_metadata = load_shared_graph_cache_metadata(
                args.snapshot_dir,
                shared_graph_cache_keys_for_examples(
                    args.corpus,
                    selected_examples=selected_examples,
                    difficulties=args.difficulties,
                    network_type=args.network_type,
                ),
            )
        if args.output:
            write_route_audit_manifest(records, args.output)
        print(
            json.dumps(
                {
                    "corpus": args.corpus,
                    "output": args.output,
                    "summary": summarize_route_audit(records),
                    **_run_metrics(start_time, count=len(records)),
                    **_shared_graph_metrics(shared_metadata),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "select-audit-subset":
        records = load_route_audit_manifest(args.manifest)
        if not args.all_records:
            records = [record for record in records if record.paper_valid]
        if args.cities:
            allowed_cities = set(args.cities)
            records = [record for record in records if record.city in allowed_cities]
        if args.difficulties:
            allowed_difficulties = set(args.difficulties)
            records = [record for record in records if record.source_difficulty in allowed_difficulties]
        if args.pb_recoverable_only:
            records = [record for record in records if record.pb_recoverable is True]
        if args.per_city_difficulty is not None:
            records = build_guardrail_records(
                records,
                cities=args.cities,
                source_difficulties=args.difficulties or ("easy", "medium", "hard"),
                per_city_difficulty=args.per_city_difficulty,
                pb_recoverable_only=args.pb_recoverable_only,
            )
        write_route_audit_manifest(records, args.output)
        print(
            json.dumps(
                {
                    "input": args.manifest,
                    "output": args.output,
                    "summary": summarize_route_audit(records),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "generate-routes":
        api_key = args.ors_api_key or os.getenv("ORS_API_KEY")
        if not api_key:
            raise ValueError("generate-routes requires --ors-api-key or ORS_API_KEY in the environment.")
        payload = generate_routes_pipeline(
            args.cities,
            num_easy=args.easy,
            num_medium=args.medium,
            num_hard=args.hard,
            output_root=args.output_root,
            ors_api_key=api_key,
            network_type=args.network_type,
            seed=args.seed,
            paper_valid_gate=args.paper_valid_gate,
            max_graph_repulls=args.max_graph_repulls,
            oversample_factor=args.oversample_factor,
            max_endpoints_per_start=args.max_endpoints_per_start,
            max_start_attempts=args.max_start_attempts,
            probe_sample_size=args.probe_sample_size,
            require_pb_recoverable=not args.disable_pb_recoverable_filter,
            pb_executor=args.pb_executor,
            progress=args.progress,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["overall"]["all_cities_success"] else 1

    if args.command == "calibrate-similarity":
        start_time = time.perf_counter()
        selected_examples = iter_corpus_examples(args.corpus, root=args.root or args.corpus, cities=args.cities, difficulties=args.difficulties)
        if args.manifest:
            selected_examples = filter_examples_by_manifest(
                selected_examples,
                load_route_audit_manifest(args.manifest),
                paper_valid_only=not args.all_manifest_records,
                pb_recoverable_only=args.pb_recoverable_only,
            )
        selected_examples = selected_examples[args.offset : args.offset + args.limit] if args.limit is not None else selected_examples[args.offset:]
        builder = None
        shared_cache_keys = None
        shared_metadata: dict[str, dict[str, str]] = {}
        effective_jobs = max(1, int(args.jobs))
        if args.shared_graph and selected_examples:
            builder, shared_cache_keys, shared_metadata, effective_jobs = _prepare_shared_graph_context(
                corpus=args.corpus,
                root=args.root or args.corpus,
                selected_examples=selected_examples,
                cities=args.cities,
                difficulties=args.difficulties,
                snapshot_dir=args.snapshot_dir,
                network_type="walk",
                progress=args.progress,
                jobs=args.jobs,
            )
        reports: list[dict[str, object]] = []
        best_report: dict[str, object] | None = None
        best_key: tuple[float, float, float] | None = None
        for config_path in args.configs:
            weights, thresholds = _load_weights(config_path)
            rows = evaluate_corpus(
                args.corpus,
                root=args.root or args.corpus,
                builder=builder,
                dist=args.dist,
                weights=weights,
                thresholds=thresholds,
                progress=args.progress,
                snapshot_dir=args.snapshot_dir,
                refresh_snapshots=args.refresh_snapshots,
                cities=args.cities,
                difficulties=args.difficulties,
                limit=args.limit,
                offset=args.offset,
                manifest_path=args.manifest,
                paper_valid_only=not args.all_manifest_records,
                pb_recoverable_only=args.pb_recoverable_only,
                executor=args.executor,
                jobs=effective_jobs,
                shared_cache_keys=shared_cache_keys,
            )
            summary = asdict(build_corpus_summary(rows, success_threshold=args.success_threshold))
            report = {
                "config": config_path,
                "summary": summary,
            }
            reports.append(report)
            overall = summary["overall"]
            score_key = (
                float(overall["success_rate"]),
                float(overall["mean_similarity"]),
                -float(overall["min_similarity"]),
            )
            if best_key is None or score_key > best_key:
                best_key = score_key
                best_report = report
        payload = {
            "corpus": args.corpus,
            "executor": args.executor,
            "manifest": args.manifest,
            "best": best_report,
            "reports": reports,
            "example_count": len(selected_examples),
            "config_count": len(args.configs),
            **_run_metrics(start_time, count=len(selected_examples) * len(args.configs)),
            **_shared_graph_metrics(shared_metadata),
        }
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

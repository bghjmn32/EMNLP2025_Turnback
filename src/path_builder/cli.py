from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .datasets import load_36k_example, load_route_example
from .execution import PathBuilder, recommended_graph_dist
from .generation import generate_routes_pipeline
from .instructions import parse_instruction_file
from .io import load_geojson
from .models import ExecutionState, SimilarityThresholds, SimilarityWeights
from .prompting import create_reverse_route_provider, write_reverse_route_outputs
from .similarity import score_geojson_routes


def _load_weights(path: str | Path | None) -> tuple[SimilarityWeights, SimilarityThresholds]:
    if path is None:
        return SimilarityWeights(), SimilarityThresholds()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    weights = SimilarityWeights(**payload.get("weights", {}))
    thresholds = SimilarityThresholds(**payload.get("thresholds", {}))
    return weights, thresholds


def _load_execute_example(args) -> object:
    if args.route_dir:
        return load_route_example(args.route_dir, corpus="36kroutes", city=args.city, difficulty=args.difficulty)
    if args.example_id is None:
        raise ValueError("execute requires an example id or --route-dir.")
    if not args.city or not args.difficulty:
        raise ValueError("execute requires --city and --difficulty when --route-dir is not used.")
    return load_36k_example(args.city, args.difficulty, args.example_id, root=args.root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="path-builder",
        description="TurnBack public toolkit: route generation, reverse prompting, execution, and scoring.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reverse_cmd = subparsers.add_parser(
        "generate-reverse",
        help="Call an external LLM provider and write raw + cleaned reverse-route instructions.",
    )
    reverse_cmd.add_argument("--provider", choices=["openai", "gemini"], required=True)
    reverse_cmd.add_argument("--model")
    reverse_cmd.add_argument("--api-key")
    reverse_cmd.add_argument("--city", required=True)
    reverse_cmd.add_argument("--input-file", required=True)
    reverse_cmd.add_argument("--raw-output")
    reverse_cmd.add_argument("--clean-output")

    score_cmd = subparsers.add_parser("score", help="Score two GeoJSON routes with the public similarity implementation.")
    score_cmd.add_argument("prediction")
    score_cmd.add_argument("reference")
    score_cmd.add_argument("--config")

    execute_cmd = subparsers.add_parser("execute", help="Execute reverse instructions against a street graph with Path Builder.")
    execute_cmd.add_argument("example_id", nargs="?")
    execute_cmd.add_argument("--root", default="36kroutes")
    execute_cmd.add_argument("--route-dir")
    execute_cmd.add_argument("--city")
    execute_cmd.add_argument("--difficulty")
    execute_cmd.add_argument("--instructions", required=True)
    execute_cmd.add_argument("--start", choices=["start", "end"], default="start")
    execute_cmd.add_argument("--output", default="answer_path_builder.geojson")
    execute_cmd.add_argument("--dist", type=int, default=1000)
    execute_cmd.add_argument("--executor", choices=["greedy", "search", "hybrid"], default="hybrid")

    generate_cmd = subparsers.add_parser(
        "generate-routes",
        help="Generate easy / medium / hard route folders in the released 36kroutes format.",
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate-reverse":
        instructions_text = Path(args.input_file).read_text(encoding="utf-8")
        provider = create_reverse_route_provider(args.provider, api_key=args.api_key, model_name=args.model)
        response_text = provider.generate(args.city, instructions_text)
        _, cleaned = write_reverse_route_outputs(
            response_text,
            raw_output_path=args.raw_output,
            clean_output_path=args.clean_output,
        )
        print(json.dumps({"provider": args.provider, "cleaned_lines": len(cleaned.splitlines()) if cleaned else 0}, indent=2))
        return 0

    if args.command == "score":
        weights, thresholds = _load_weights(args.config)
        result = score_geojson_routes(
            load_geojson(args.prediction),
            load_geojson(args.reference),
            weights=weights,
            thresholds=thresholds,
        )
        print(
            json.dumps(
                {
                    "similarity": result.similarity,
                    "scores": result.scores,
                    "weights": result.weights,
                    "params": result.params,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "execute":
        example = _load_execute_example(args)
        commands = parse_instruction_file(args.instructions)
        start = example.start if args.start == "start" else example.end
        if start is None:
            raise ValueError("Route example does not contain start/end metadata.")
        builder = PathBuilder.from_osm((start[1], start[0]), dist=max(args.dist, recommended_graph_dist(commands)))
        trace = builder.execute(
            commands,
            ExecutionState(current_coordinates=(start[1], start[0]), current_heading=0.0),
            executor=args.executor,
        )
        output_path = example.root / args.output if not Path(args.output).is_absolute() else Path(args.output)
        builder.write_trace_geojson(trace, output_path)
        print(f"Wrote execution trace to {output_path}")
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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

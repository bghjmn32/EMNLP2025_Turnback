"""
Command-line interface for the TurnBack benchmark.
"""

import argparse
import sys
import logging
from pathlib import Path
from turnback import TurnBackBenchmark, load_dataset
from turnback.models import LLMModel, HumanBaselineModel

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def cmd_evaluate(args):
    """Handle the evaluate command."""
    setup_logging(args.verbose)
    
    # Load dataset
    logger.info(f"Loading dataset: {args.dataset}")
    dataset = load_dataset(args.dataset)
    
    # Apply filters
    if args.difficulty:
        dataset = dataset.filter_by_difficulty(args.difficulty)
    if args.region:
        dataset = dataset.filter_by_region(args.region)
    
    logger.info(f"Dataset size: {len(dataset)}")
    
    # Initialize model
    if args.model == "human_baseline":
        model = HumanBaselineModel()
    else:
        model = LLMModel(args.model, api_key=args.api_key)
    
    # Run evaluation
    benchmark = TurnBackBenchmark()
    results = benchmark.evaluate(model, dataset)
    
    # Print results
    print(f"\nEvaluation Results for {args.model}")
    print(f"Overall Score: {results['overall_score']:.3f}")
    print(f"Dataset Size: {results['dataset_size']}")
    
    print("\nMetrics:")
    for key, value in results['metrics'].items():
        if key != 'by_difficulty':
            print(f"  {key}: {value}")
    
    # Save results if output specified
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")


def cmd_info(args):
    """Handle the info command."""
    setup_logging(args.verbose)
    
    dataset = load_dataset(args.dataset)
    stats = dataset.get_statistics()
    
    print(f"Dataset: {args.dataset}")
    print(f"Total Routes: {stats['total_routes']}")
    
    print("\nDifficulty Distribution:")
    for difficulty, count in stats['difficulty_distribution'].items():
        print(f"  {difficulty}: {count}")
    
    print("\nRegion Distribution:")
    for region, count in stats['region_distribution'].items():
        print(f"  {region}: {count}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="TurnBack: Geospatial Route Cognition Benchmark"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate a model")
    eval_parser.add_argument("--model", required=True, help="Model name")
    eval_parser.add_argument("--dataset", default="turnback_routes", help="Dataset name")
    eval_parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="Filter by difficulty")
    eval_parser.add_argument("--region", help="Filter by region")
    eval_parser.add_argument("--api-key", help="API key for model")
    eval_parser.add_argument("--output", help="Output file for results")
    eval_parser.set_defaults(func=cmd_evaluate)
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show dataset information")
    info_parser.add_argument("--dataset", default="turnback_routes", help="Dataset name")
    info_parser.set_defaults(func=cmd_info)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
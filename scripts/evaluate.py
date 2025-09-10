#!/usr/bin/env python3
"""
Evaluation script for the TurnBack benchmark.

This script provides a command-line interface for evaluating models
on the TurnBack benchmark with various configuration options.
"""

import argparse
import json
import logging
from pathlib import Path
from turnback import TurnBackBenchmark, load_dataset
from turnback.models import LLMModel, HumanBaselineModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate models on the TurnBack benchmark"
    )
    
    parser.add_argument(
        "--model", 
        type=str, 
        required=True,
        help="Model name (e.g., gpt-4, llama2, human_baseline)"
    )
    
    parser.add_argument(
        "--dataset",
        type=str,
        default="turnback_routes",
        help="Dataset name to load"
    )
    
    parser.add_argument(
        "--difficulty",
        type=str,
        choices=["easy", "medium", "hard"],
        help="Filter by difficulty level"
    )
    
    parser.add_argument(
        "--region",
        type=str,
        help="Filter by geographic region"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="results.json",
        help="Output file for results"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        help="API key for model access"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    if config_path and Path(config_path).exists():
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}


def initialize_model(model_name: str, api_key: str = None) -> object:
    """Initialize the specified model."""
    if model_name == "human_baseline":
        return HumanBaselineModel()
    else:
        return LLMModel(model_name, api_key=api_key)


def main():
    """Main evaluation function."""
    args = parse_arguments()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    config = load_config(args.config)
    
    # Load dataset
    logger.info(f"Loading dataset: {args.dataset}")
    dataset = load_dataset(args.dataset)
    
    # Apply filters if specified
    if args.difficulty:
        logger.info(f"Filtering by difficulty: {args.difficulty}")
        dataset = dataset.filter_by_difficulty(args.difficulty)
    
    if args.region:
        logger.info(f"Filtering by region: {args.region}")
        dataset = dataset.filter_by_region(args.region)
    
    logger.info(f"Dataset size after filtering: {len(dataset)}")
    
    # Initialize model
    logger.info(f"Initializing model: {args.model}")
    model = initialize_model(args.model, args.api_key)
    
    # Initialize benchmark
    benchmark = TurnBackBenchmark(config)
    
    # Run evaluation
    logger.info("Starting evaluation...")
    results = benchmark.evaluate(model, dataset)
    
    # Save results
    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {output_path}")
    
    # Print summary
    print(f"\nEvaluation completed for {args.model}")
    print(f"Overall Score: {results['overall_score']:.3f}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
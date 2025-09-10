#!/usr/bin/env python3
"""
Basic usage example for the TurnBack benchmark.

This script demonstrates how to load a dataset, initialize a model,
and run evaluation on the TurnBack benchmark.
"""

import logging
from turnback import TurnBackBenchmark, load_dataset
from turnback.models import LLMModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Run basic TurnBack evaluation example."""
    
    # Load the benchmark dataset
    logger.info("Loading TurnBack dataset...")
    dataset = load_dataset("turnback_routes")
    
    print(f"Dataset loaded with {len(dataset)} routes")
    print("Dataset statistics:")
    stats = dataset.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Initialize a model (placeholder - replace with actual model)
    logger.info("Initializing model...")
    model = LLMModel("gpt-4", api_key="your-api-key-here")
    
    # Initialize the benchmark
    benchmark = TurnBackBenchmark()
    
    # Run evaluation
    logger.info("Starting evaluation...")
    results = benchmark.evaluate(model, dataset)
    
    # Print results
    print("\nEvaluation Results:")
    print(f"Model: {results['model_name']}")
    print(f"Dataset size: {results['dataset_size']}")
    print(f"Overall score: {results['overall_score']}")
    
    print("\nDetailed Metrics:")
    for metric, value in results['metrics'].items():
        if metric != 'by_difficulty':
            print(f"  {metric}: {value}")
    
    print("\nBy Difficulty:")
    for difficulty, metrics in results['metrics']['by_difficulty'].items():
        print(f"  {difficulty}: accuracy={metrics['accuracy']:.3f}, count={metrics['count']}")


if __name__ == "__main__":
    main()
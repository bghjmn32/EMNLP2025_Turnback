"""
TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models

This package provides tools for evaluating Large Language Models on geospatial 
route cognition tasks through reverse route challenges.
"""

__version__ = "0.1.0"
__author__ = "EMNLP2025 TurnBack Authors"

from .benchmark import TurnBackBenchmark
from .dataset import load_dataset, RouteDataset
from .models import BaseModel, LLMModel
from .evaluation import evaluate_model, RouteEvaluator

__all__ = [
    "TurnBackBenchmark",
    "load_dataset", 
    "RouteDataset",
    "BaseModel",
    "LLMModel", 
    "evaluate_model",
    "RouteEvaluator"
]
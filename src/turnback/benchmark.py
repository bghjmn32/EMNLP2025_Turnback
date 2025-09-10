"""
Main benchmark class for TurnBack evaluation.
"""

from typing import Dict, List, Any, Optional
import logging
from .dataset import RouteDataset
from .models import BaseModel
from .evaluation import RouteEvaluator

logger = logging.getLogger(__name__)


class TurnBackBenchmark:
    """
    Main benchmark class for evaluating models on geospatial route cognition tasks.
    
    This class orchestrates the evaluation of Large Language Models on reverse route
    tasks, providing a standardized interface for loading datasets, running evaluations,
    and collecting results.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the TurnBack benchmark.
        
        Args:
            config: Optional configuration dictionary for customizing evaluation
        """
        self.config = config or {}
        self.evaluator = RouteEvaluator(self.config)
        logger.info("TurnBack benchmark initialized")
    
    def evaluate(self, model: BaseModel, dataset: RouteDataset) -> Dict[str, Any]:
        """
        Evaluate a model on the given dataset.
        
        Args:
            model: The model to evaluate
            dataset: The dataset to evaluate on
            
        Returns:
            Dictionary containing evaluation results
        """
        logger.info(f"Starting evaluation of {model.__class__.__name__} on {len(dataset)} samples")
        
        results = self.evaluator.evaluate(model, dataset)
        
        logger.info(f"Evaluation completed. Overall accuracy: {results.get('accuracy', 0):.3f}")
        return results
    
    def load_config(self, config_path: str) -> None:
        """
        Load configuration from file.
        
        Args:
            config_path: Path to configuration file
        """
        # Implementation to be added
        pass
    
    def save_results(self, results: Dict[str, Any], output_path: str) -> None:
        """
        Save evaluation results to file.
        
        Args:
            results: Evaluation results dictionary
            output_path: Path to save results
        """
        # Implementation to be added
        pass
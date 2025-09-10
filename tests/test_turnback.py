"""
Unit tests for the TurnBack benchmark.
"""

import unittest
from unittest.mock import Mock, patch
from turnback import TurnBackBenchmark, load_dataset
from turnback.models import LLMModel, HumanBaselineModel
from turnback.dataset import Route, RoutePoint, RouteDataset
from turnback.evaluation import RouteEvaluator


class TestRouteDataset(unittest.TestCase):
    """Test cases for RouteDataset class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sample_routes = []
        for i in range(5):
            start_point = RoutePoint(latitude=40.0 + i, longitude=-74.0 + i)
            end_point = RoutePoint(latitude=41.0 + i, longitude=-73.0 + i)
            
            route = Route(
                route_id=f"test_route_{i}",
                points=[start_point, end_point],
                start_point=start_point,
                end_point=end_point,
                difficulty=["easy", "medium", "hard"][i % 3],
                region="Test Region"
            )
            self.sample_routes.append(route)
        
        self.dataset = RouteDataset(self.sample_routes)
    
    def test_dataset_length(self):
        """Test dataset length."""
        self.assertEqual(len(self.dataset), 5)
    
    def test_dataset_indexing(self):
        """Test dataset indexing."""
        route = self.dataset[0]
        self.assertEqual(route.route_id, "test_route_0")
        self.assertEqual(route.difficulty, "easy")
    
    def test_filter_by_difficulty(self):
        """Test filtering by difficulty."""
        easy_dataset = self.dataset.filter_by_difficulty("easy")
        self.assertTrue(len(easy_dataset) > 0)
        
        for route in easy_dataset.routes:
            self.assertEqual(route.difficulty, "easy")
    
    def test_filter_by_region(self):
        """Test filtering by region."""
        region_dataset = self.dataset.filter_by_region("Test Region")
        self.assertEqual(len(region_dataset), 5)
    
    def test_get_statistics(self):
        """Test statistics generation."""
        stats = self.dataset.get_statistics()
        
        self.assertIn("total_routes", stats)
        self.assertIn("difficulty_distribution", stats)
        self.assertIn("region_distribution", stats)
        self.assertEqual(stats["total_routes"], 5)


class TestModels(unittest.TestCase):
    """Test cases for model classes."""
    
    def test_llm_model_initialization(self):
        """Test LLM model initialization."""
        model = LLMModel("test-model")
        self.assertEqual(model.model_name, "test-model")
    
    def test_human_baseline_model(self):
        """Test human baseline model."""
        model = HumanBaselineModel()
        self.assertEqual(model.model_name, "human_baseline")
        
        # Test prediction
        route_data = {"route_id": "test"}
        prediction = model.predict(route_data)
        
        self.assertIn("predicted_route", prediction)
        self.assertIn("confidence", prediction)
    
    def test_model_prediction_format(self):
        """Test that model predictions have correct format."""
        model = LLMModel("test-model")
        route_data = {
            "route_id": "test",
            "start_point": {"latitude": 40.0, "longitude": -74.0},
            "end_point": {"latitude": 41.0, "longitude": -73.0}
        }
        
        prediction = model.predict(route_data)
        
        required_keys = ["predicted_route", "confidence", "reasoning"]
        for key in required_keys:
            self.assertIn(key, prediction)


class TestEvaluator(unittest.TestCase):
    """Test cases for RouteEvaluator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {}
        self.evaluator = RouteEvaluator(self.config)
        
        # Create a small test dataset
        start_point = RoutePoint(latitude=40.0, longitude=-74.0)
        end_point = RoutePoint(latitude=41.0, longitude=-73.0)
        
        route = Route(
            route_id="test_route",
            points=[start_point, end_point],
            start_point=start_point,
            end_point=end_point,
            difficulty="easy",
            region="Test Region"
        )
        
        self.dataset = RouteDataset([route])
        self.model = LLMModel("test-model")
    
    def test_evaluator_initialization(self):
        """Test evaluator initialization."""
        self.assertIsInstance(self.evaluator, RouteEvaluator)
        self.assertEqual(self.evaluator.config, {})
    
    def test_evaluation_result_format(self):
        """Test that evaluation results have correct format."""
        results = self.evaluator.evaluate(self.model, self.dataset)
        
        required_keys = ["model_name", "dataset_size", "metrics", "overall_score"]
        for key in required_keys:
            self.assertIn(key, results)
        
        self.assertEqual(results["model_name"], "test-model")
        self.assertEqual(results["dataset_size"], 1)
        self.assertIsInstance(results["overall_score"], (int, float))


class TestBenchmark(unittest.TestCase):
    """Test cases for TurnBackBenchmark class."""
    
    def test_benchmark_initialization(self):
        """Test benchmark initialization."""
        benchmark = TurnBackBenchmark()
        self.assertIsInstance(benchmark, TurnBackBenchmark)
    
    def test_benchmark_with_config(self):
        """Test benchmark initialization with config."""
        config = {"test_param": "test_value"}
        benchmark = TurnBackBenchmark(config)
        self.assertEqual(benchmark.config, config)


class TestIntegration(unittest.TestCase):
    """Integration tests."""
    
    def test_end_to_end_evaluation(self):
        """Test complete evaluation pipeline."""
        # Load dataset
        dataset = load_dataset("test_dataset")
        
        # Initialize model
        model = HumanBaselineModel()
        
        # Initialize benchmark
        benchmark = TurnBackBenchmark()
        
        # Run evaluation
        results = benchmark.evaluate(model, dataset)
        
        # Verify results
        self.assertIsInstance(results, dict)
        self.assertIn("overall_score", results)
        self.assertIn("metrics", results)


if __name__ == "__main__":
    unittest.main()
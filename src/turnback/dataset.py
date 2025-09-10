"""
Dataset loading and management utilities.
"""

from typing import List, Dict, Any, Optional, Union
import json
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RoutePoint:
    """Represents a single point in a route."""
    latitude: float
    longitude: float
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass 
class Route:
    """Represents a complete route with multiple points."""
    route_id: str
    points: List[RoutePoint]
    start_point: RoutePoint
    end_point: RoutePoint
    difficulty: str  # "easy", "medium", "hard"
    region: str
    metadata: Optional[Dict[str, Any]] = None


class RouteDataset:
    """
    Dataset class for handling route data.
    
    This class provides functionality for loading, managing, and accessing
    route data for the TurnBack benchmark.
    """
    
    def __init__(self, routes: List[Route]):
        """
        Initialize the dataset with a list of routes.
        
        Args:
            routes: List of Route objects
        """
        self.routes = routes
        logger.info(f"Initialized dataset with {len(routes)} routes")
    
    def __len__(self) -> int:
        """Return the number of routes in the dataset."""
        return len(self.routes)
    
    def __getitem__(self, idx: int) -> Route:
        """Get a route by index."""
        return self.routes[idx]
    
    def filter_by_difficulty(self, difficulty: str) -> 'RouteDataset':
        """
        Filter routes by difficulty level.
        
        Args:
            difficulty: Difficulty level to filter by
            
        Returns:
            New RouteDataset with filtered routes
        """
        filtered_routes = [route for route in self.routes if route.difficulty == difficulty]
        return RouteDataset(filtered_routes)
    
    def filter_by_region(self, region: str) -> 'RouteDataset':
        """
        Filter routes by geographic region.
        
        Args:
            region: Region to filter by
            
        Returns:
            New RouteDataset with filtered routes
        """
        filtered_routes = [route for route in self.routes if route.region == region]
        return RouteDataset(filtered_routes)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get dataset statistics.
        
        Returns:
            Dictionary with dataset statistics
        """
        difficulties = [route.difficulty for route in self.routes]
        regions = [route.region for route in self.routes]
        
        return {
            "total_routes": len(self.routes),
            "difficulty_distribution": {
                diff: difficulties.count(diff) for diff in set(difficulties)
            },
            "region_distribution": {
                region: regions.count(region) for region in set(regions)
            }
        }


def load_dataset(dataset_name: str, data_path: Optional[str] = None) -> RouteDataset:
    """
    Load a dataset by name.
    
    Args:
        dataset_name: Name of the dataset to load
        data_path: Optional path to data directory
        
    Returns:
        RouteDataset object
    """
    logger.info(f"Loading dataset: {dataset_name}")
    
    # This is a placeholder implementation
    # In the actual implementation, this would load real data
    sample_routes = []
    
    # Create some sample routes for demonstration
    for i in range(10):
        start_point = RoutePoint(latitude=40.7128 + i*0.01, longitude=-74.0060 + i*0.01)
        end_point = RoutePoint(latitude=40.7228 + i*0.01, longitude=-74.0160 + i*0.01)
        
        route = Route(
            route_id=f"route_{i:03d}",
            points=[start_point, end_point],
            start_point=start_point,
            end_point=end_point,
            difficulty=["easy", "medium", "hard"][i % 3],
            region="New York",
            metadata={"sample": True}
        )
        sample_routes.append(route)
    
    dataset = RouteDataset(sample_routes)
    logger.info(f"Loaded {len(dataset)} routes")
    return dataset
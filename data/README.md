# TurnBack Dataset

This directory contains the datasets used in the TurnBack benchmark.

## Directory Structure

```
data/
├── raw/              # Raw, unprocessed route data
├── processed/        # Cleaned and formatted datasets
├── samples/          # Sample data for testing and examples
└── README.md         # This file
```

## Dataset Files

### Core Datasets

- `turnback_routes.json` - Main benchmark dataset with route data
- `turnback_metadata.json` - Metadata and statistics about the dataset
- `geographic_regions.json` - Information about geographic regions covered

### Sample Data

- `sample_routes.json` - Small sample dataset for testing (10 routes)
- `example_annotations.json` - Example human annotations

## Data Format

Each route in the dataset contains:

- `route_id`: Unique identifier for the route
- `start_point`: Starting location (latitude, longitude)
- `end_point`: Destination location (latitude, longitude)
- `intermediate_points`: List of waypoints along the route
- `difficulty`: Difficulty level (easy, medium, hard)
- `region`: Geographic region
- `metadata`: Additional information about the route

## Usage

```python
from turnback import load_dataset

# Load the main dataset
dataset = load_dataset("turnback_routes")

# Load sample data
sample_dataset = load_dataset("sample_routes")
```

## Data Collection

The TurnBack dataset was collected from various sources including:

- GPS trajectory data from navigation apps
- Crowdsourced route annotations
- Geographic information systems (GIS)
- Public transportation data

All data has been anonymized and aggregated to protect privacy.

## Citation

If you use the TurnBack dataset in your research, please cite our paper:

```bibtex
@inproceedings{turnback2025,
  title={TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models through Reverse Route},
  author={[Authors]},
  booktitle={Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing},
  year={2025}
}
```
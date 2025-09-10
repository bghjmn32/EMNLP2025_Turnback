# TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models

[![EMNLP 2025](https://img.shields.io/badge/EMNLP-2025-blue.svg)](https://2025.emnlp.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

This repository contains the code and data for **TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models through Reverse Route**, accepted at EMNLP 2025.

## Overview

TurnBack is a novel benchmark designed to evaluate the geospatial route cognition capabilities of Large Language Models (LLMs) through reverse route tasks. This benchmark challenges models to understand spatial relationships, navigation patterns, and geographic reasoning by asking them to work backwards from destination to origin.

## Features

- 🗺️ **Comprehensive Geospatial Dataset**: Curated collection of route data across diverse geographic regions
- 🔄 **Reverse Route Tasks**: Novel evaluation paradigm testing backward spatial reasoning
- 🤖 **LLM Evaluation Framework**: Standardized evaluation pipeline for multiple LLM architectures
- 📊 **Detailed Analysis**: In-depth performance analysis and error categorization
- 🛠️ **Easy Integration**: Simple API for evaluating custom models

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/bghjmn32/EMNLP2025_Turnback.git
cd EMNLP2025_Turnback

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### Basic Usage

```python
from turnback import TurnBackBenchmark, load_dataset

# Load the benchmark dataset
dataset = load_dataset("turnback_routes")

# Initialize the benchmark
benchmark = TurnBackBenchmark()

# Evaluate a model
results = benchmark.evaluate(model, dataset)
print(f"Overall Accuracy: {results['accuracy']:.2f}")
```

## Dataset

The TurnBack dataset includes:

- **Route Data**: GPS trajectories with start/end points and intermediate waypoints
- **Geographic Diversity**: Urban, suburban, and rural routes across multiple countries
- **Difficulty Levels**: Easy, medium, and hard reverse route tasks
- **Evaluation Metrics**: Multiple assessment criteria including spatial accuracy and reasoning quality

## Repository Structure

```
EMNLP2025_Turnback/
├── src/turnback/           # Main source code
├── data/                   # Dataset files
├── examples/               # Usage examples
├── tests/                  # Unit tests
├── docs/                   # Documentation
├── requirements.txt        # Python dependencies
├── setup.py               # Package configuration
└── README.md              # This file
```

## Evaluation

Run the evaluation pipeline:

```bash
# Evaluate on the full benchmark
python scripts/evaluate.py --model gpt-4 --dataset turnback_full

# Run specific task types
python scripts/evaluate.py --model llama2 --task reverse_navigation --difficulty hard
```

## Citation

If you use TurnBack in your research, please cite our paper:

```bibtex
@inproceedings{turnback2025,
  title={TurnBack: A Geospatial Route Cognition Benchmark for Large Language Models through Reverse Route},
  author={[Authors]},
  booktitle={Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing},
  year={2025},
  publisher={Association for Computational Linguistics}
}
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

For questions or issues, please:
- Open an issue on GitHub
- Contact the authors at [contact information]

## Acknowledgments

We thank the research community and the anonymous reviewers for their valuable feedback. This work was supported by [funding information].

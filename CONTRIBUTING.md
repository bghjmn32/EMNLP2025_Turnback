# Contributing to TurnBack

We welcome contributions to the TurnBack project! This document provides guidelines for contributing.

## How to Contribute

### Reporting Issues

If you find a bug or have a suggestion for improvement:

1. Check the [GitHub Issues](https://github.com/bghjmn32/EMNLP2025_Turnback/issues) to see if it's already reported
2. If not, create a new issue with:
   - Clear description of the problem or suggestion
   - Steps to reproduce (for bugs)
   - Expected vs actual behavior
   - Your environment details (Python version, OS, etc.)

### Pull Requests

1. Fork the repository
2. Create a new branch for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass:
   ```bash
   python -m pytest tests/
   ```
6. Format your code:
   ```bash
   black src/ tests/
   isort src/ tests/
   ```
7. Submit a pull request

### Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/EMNLP2025_Turnback.git
   cd EMNLP2025_Turnback
   ```

2. Install in development mode:
   ```bash
   pip install -e .[dev]
   ```

3. Install pre-commit hooks:
   ```bash
   pip install pre-commit
   pre-commit install
   ```

### Code Style

- Follow PEP 8 style guidelines
- Use Black for code formatting
- Use isort for import sorting
- Add type hints where appropriate
- Write docstrings for public functions and classes

### Testing

- Write unit tests for new features
- Ensure all tests pass before submitting
- Aim for good test coverage
- Use pytest for testing framework

### Documentation

- Update README.md if needed
- Add docstrings to new functions and classes
- Update any relevant documentation files

## Code of Conduct

Please be respectful and constructive in all interactions. We want to maintain a welcoming environment for all contributors.

## Questions?

If you have questions about contributing, feel free to:
- Open an issue for discussion
- Contact the maintainers

Thank you for contributing to TurnBack!
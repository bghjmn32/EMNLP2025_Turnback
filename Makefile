PYTHON ?= python3

.PHONY: install test lint compile quick-check

install:
	$(PYTHON) -m pip install -e ".[dev,llm]"

test:
	pytest -q

lint:
	ruff check src/path_builder tests --select F,E9

compile:
	$(PYTHON) -m compileall src/path_builder

quick-check:
	./scripts/quick_check.sh

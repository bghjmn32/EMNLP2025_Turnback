PYTHON ?= python3

.PHONY: install test lint compile smoke

install:
	$(PYTHON) -m pip install -e ".[dev,llm]"

test:
	pytest -q

lint:
	ruff check src/path_builder tests --select F,E9

compile:
	$(PYTHON) -m compileall src/path_builder

smoke:
	$(PYTHON) -m path_builder.cli --help >/dev/null
	$(PYTHON) -m path_builder.cli generate-routes --help >/dev/null
	$(PYTHON) -m path_builder.cli generate-reverse --help >/dev/null


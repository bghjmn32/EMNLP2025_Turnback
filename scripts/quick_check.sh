#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}src"

ruff check src/path_builder tests --select F,E9
python -m compileall src/path_builder
pytest -q
python -m path_builder.cli --help >/dev/null
python -m path_builder.cli generate-routes --help >/dev/null
python -m path_builder.cli generate-reverse --help >/dev/null

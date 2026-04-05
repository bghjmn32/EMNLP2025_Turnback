#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$(cd "${ROOT_DIR}/.." && pwd)"

rsync -a --delete "${SOURCE_DIR}/src/" "${ROOT_DIR}/src/"
rsync -a --delete "${SOURCE_DIR}/configs/" "${ROOT_DIR}/configs/"
rsync -a --delete \
  --include='test_ceiling.py' \
  --include='test_cli.py' \
  --include='test_directions.py' \
  --include='test_evaluation.py' \
  --include='test_execution.py' \
  --include='test_generation.py' \
  --include='test_instructions.py' \
  --include='test_paper.py' \
  --include='test_prompting.py' \
  --include='test_similarity.py' \
  --exclude='*' \
  "${SOURCE_DIR}/tests/" "${ROOT_DIR}/tests/"

if [[ "${1:-}" == "--with-36kroutes" ]]; then
  rsync -a --delete "${SOURCE_DIR}/36kroutes/" "${ROOT_DIR}/36kroutes/"
fi


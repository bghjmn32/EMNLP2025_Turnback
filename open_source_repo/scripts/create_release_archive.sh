#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE_NAME="${1:-turnback_open_source_repo.tar.gz}"

TMP_PARENT="$(mktemp -d)"
trap 'rm -rf "${TMP_PARENT}"' EXIT

STAGE_DIR="${TMP_PARENT}/open_source_repo"
mkdir -p "${STAGE_DIR}"

rsync -a \
  --exclude='.git' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='__pycache__' \
  "${ROOT_DIR}/" "${STAGE_DIR}/"

tar -czf "${ROOT_DIR}/${ARCHIVE_NAME}" -C "${TMP_PARENT}" open_source_repo
echo "Wrote ${ROOT_DIR}/${ARCHIVE_NAME}"


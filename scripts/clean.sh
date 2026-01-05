#!/usr/bin/env bash
set -e
echo "Cleaning build artifacts..."
rm -rf build
rm -rf .pytest_cache
rm -rf .mypy_cache
rm -rf .ruff_cache
rm -rf src/*.egg-info
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "Clean complete."

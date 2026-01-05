#!/usr/bin/env bash
set -e

# Ensure we are in a Nix environment
if [ -z "$IN_NIX_SHELL" ]; then
    echo "Not in Nix environment. Re-running inside Nix..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    "$SCRIPT_DIR/dev.sh" "$0" "$@"
    exit $?
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure logs and build directories exist
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/build/coverage"

# Create timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$PROJECT_ROOT/logs/coverage_${TIMESTAMP}.log"

cd "$PROJECT_ROOT"

echo "=== Hermes Code Coverage ===" | tee "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Run pytest with coverage
echo "Running tests with coverage..." | tee -a "$LOG_FILE"
pytest \
    --cov=hermes \
    --cov-report=term-missing \
    --cov-report=xml:build/coverage/coverage.xml \
    --cov-report=html:build/coverage/html \
    2>&1 | tee -a "$LOG_FILE"

# Create symlink to latest
ln -sf "coverage_${TIMESTAMP}.log" "$PROJECT_ROOT/logs/coverage.log"

echo "" | tee -a "$LOG_FILE"
echo "=== Coverage Report Generated ===" | tee -a "$LOG_FILE"
echo "HTML Report: build/coverage/html/index.html" | tee -a "$LOG_FILE"
echo "XML Report:  build/coverage/coverage.xml" | tee -a "$LOG_FILE"
echo "Log file:    logs/coverage_${TIMESTAMP}.log" | tee -a "$LOG_FILE"

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

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Run CI checks for the Hermes project.

Options:
  --skip-lint       Skip linting checks
  --skip-typecheck  Skip type checking
  --skip-tests      Skip tests
  -h, --help        Show this help message

Examples:
  ./scripts/ci.sh                    # Full CI
  ./scripts/ci.sh --skip-typecheck   # Skip mypy
EOF
    exit 0
}

SKIP_LINT=false
SKIP_TYPECHECK=false
SKIP_TESTS=false

for arg in "$@"; do
    case $arg in
        -h|--help)
            show_help
            ;;
        --skip-lint)
            SKIP_LINT=true
            ;;
        --skip-typecheck)
            SKIP_TYPECHECK=true
            ;;
        --skip-tests)
            SKIP_TESTS=true
            ;;
        *)
            echo "Warning: Unknown argument ignored: $arg" >&2
            ;;
    esac
done

# Ensure logs directory exists
mkdir -p "$PROJECT_ROOT/logs"

# Create timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$PROJECT_ROOT/logs/ci_${TIMESTAMP}.log"

cd "$PROJECT_ROOT"

echo "=== Hermes CI ===" | tee "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# 1. Lint
if [ "$SKIP_LINT" = false ]; then
    echo "=== Linting (ruff) ===" | tee -a "$LOG_FILE"
    ruff check src tests 2>&1 | tee -a "$LOG_FILE"
    echo "✓ Lint passed" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
fi

# 2. Type check
if [ "$SKIP_TYPECHECK" = false ]; then
    echo "=== Type Checking (mypy) ===" | tee -a "$LOG_FILE"
    mypy src 2>&1 | tee -a "$LOG_FILE"
    echo "✓ Type check passed" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
fi

# 3. Tests
if [ "$SKIP_TESTS" = false ]; then
    echo "=== Tests (pytest) ===" | tee -a "$LOG_FILE"
    pytest -v 2>&1 | tee -a "$LOG_FILE"
    echo "✓ Tests passed" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
fi

# Create symlink to latest
ln -sf "ci_${TIMESTAMP}.log" "$PROJECT_ROOT/logs/ci.log"

echo "=== CI Complete ===" | tee -a "$LOG_FILE"
echo "Logs available at logs/ci_${TIMESTAMP}.log (symlinked to logs/ci.log)"

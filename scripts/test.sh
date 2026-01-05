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

# Parse arguments
VERBOSE=false
COVERAGE=false
MARKER=""

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Run tests for the Hermes project.

Options:
  -v, --verbose     Verbose test output
  --coverage        Run with coverage reporting
  -m, --marker M    Only run tests matching marker M (e.g., "not slow")
  -h, --help        Show this help message

Examples:
  ./scripts/test.sh                    # Run all tests
  ./scripts/test.sh -v                 # Verbose output
  ./scripts/test.sh --coverage         # With coverage
  ./scripts/test.sh -m "not slow"      # Skip slow tests
EOF
    exit 0
}

for arg in "$@"; do
    case $arg in
        -h|--help)
            show_help
            ;;
        -v|--verbose)
            VERBOSE=true
            ;;
        --coverage)
            COVERAGE=true
            ;;
        -m|--marker)
            shift
            MARKER="$1"
            ;;
        *)
            ;;
    esac
done

# Build pytest command
PYTEST_ARGS=()

if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS+=("-v")
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_ARGS+=("--cov=hermes" "--cov-report=term-missing" "--cov-report=xml:coverage.xml")
fi

if [ -n "$MARKER" ]; then
    PYTEST_ARGS+=("-m" "$MARKER")
fi

# Ensure logs directory exists
mkdir -p "$PROJECT_ROOT/logs"

# Create timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$PROJECT_ROOT/logs/tests_${TIMESTAMP}.log"

echo "=== Hermes Tests ===" | tee "$LOG_FILE"
cd "$PROJECT_ROOT"

# Run pytest
pytest "${PYTEST_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"

# Create symlink to latest
ln -sf "tests_${TIMESTAMP}.log" "$PROJECT_ROOT/logs/tests.log"

echo ""
echo "Tests complete. Logs available at logs/tests_${TIMESTAMP}.log"

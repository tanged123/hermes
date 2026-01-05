#!/bin/bash
set -e

# Ensure we are in a Nix environment
if [ -z "$IN_NIX_SHELL" ]; then
    echo "Not in Nix environment. Re-running inside Nix..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    "$SCRIPT_DIR/dev.sh" "$0" "$@"
    exit $?
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure doxygen is installed
if ! command -v doxygen &> /dev/null; then
    echo "Doxygen could not be found. Please install it."
    exit 1
fi

echo "Generating documentation..."
cd "$PROJECT_ROOT"
mkdir -p build/docs
doxygen Doxyfile

# Copy additional docs if they exist
if [ -d "docs/guides" ]; then
    cp -r docs/guides build/docs/html/guides 2>/dev/null || true
fi

echo "Documentation generated in build/docs/html"

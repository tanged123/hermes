#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK_DIR="$PROJECT_ROOT/.git/hooks"
SOURCE_HOOK="$PROJECT_ROOT/.github/hooks/pre-commit"

# ------------------------------------------------------------------------------
# Pre-commit hook installation
# ------------------------------------------------------------------------------

if [ ! -d "$HOOK_DIR" ]; then
    echo "Error: .git/hooks directory not found. Are you in a git repository?"
    exit 1
fi

if [ ! -f "$SOURCE_HOOK" ]; then
    echo "Error: Pre-commit hook not found at $SOURCE_HOOK"
    exit 1
fi

cp "$SOURCE_HOOK" "$HOOK_DIR/pre-commit"
chmod +x "$HOOK_DIR/pre-commit"

echo "✓ Pre-commit hook installed successfully!"
echo "  Your code will be auto-formatted before each commit."

echo ""
echo "Setup complete!"

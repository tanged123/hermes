#!/usr/bin/env bash
set -e

# Usage: ./scripts/bump_version.sh [major|minor|patch]
# Defaults to patch if no argument provided.

PYPROJECT_FILE="pyproject.toml"

if [ ! -f "$PYPROJECT_FILE" ]; then
    echo "Error: $PYPROJECT_FILE not found in current directory."
    exit 1
fi

# 1. Get current version from pyproject.toml
CURRENT_VERSION=$(grep -oP '^version = "\K[0-9]+\.[0-9]+\.[0-9]+' "$PYPROJECT_FILE")

if [ -z "$CURRENT_VERSION" ]; then
    echo "Error: Could not find version in $PYPROJECT_FILE"
    exit 1
fi

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

echo "Current Version: $MAJOR.$MINOR.$PATCH"

# 2. Increment based on argument
MODE=${1:-patch}

if [ "$MODE" == "major" ]; then
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
elif [ "$MODE" == "minor" ]; then
    MINOR=$((MINOR + 1))
    PATCH=0
elif [ "$MODE" == "patch" ]; then
    PATCH=$((PATCH + 1))
else
    echo "Usage: $0 [major|minor|patch]"
    exit 1
fi

NEW_VERSION="$MAJOR.$MINOR.$PATCH"

# 3. Check if using GNU sed or BSD sed (macOS)
if sed --version 2>/dev/null | grep -q GNU; then
    SED="sed -i"
else
    SED="sed -i ''"
fi

# 4. Update pyproject.toml
$SED "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" "$PYPROJECT_FILE"
echo "Updated $PYPROJECT_FILE"

# 5. Update flake.nix (if exists and has version)
FLAKE_FILE="flake.nix"
if [ -f "$FLAKE_FILE" ] && grep -q 'version = "' "$FLAKE_FILE"; then
    $SED "s/version = \"$CURRENT_VERSION\";/version = \"$NEW_VERSION\";/" "$FLAKE_FILE"
    echo "Updated $FLAKE_FILE"
fi

# 6. Update src/hermes/__init__.py
INIT_FILE="src/hermes/__init__.py"
if [ -f "$INIT_FILE" ]; then
    $SED "s/__version__ = \"$CURRENT_VERSION\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"
    echo "Updated $INIT_FILE"
fi

echo "Bumped to: $NEW_VERSION"

# Optional: Git tag suggestion
echo ""
echo "Don't forget to commit and tag:"
echo "  git add -u"
echo "  git commit -m \"chore: bump version to $NEW_VERSION\""
echo "  git tag v$NEW_VERSION"

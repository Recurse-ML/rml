#! /usr/bin/env bash

# Exit on error, undefined variables, and pipe failures
set -euo pipefail
trap 'echo "Error on line $LINENO"' ERR

# Configuration
VERSION_URL="https://github.com/Recurse-ML/rml/releases/latest/download/version.txt"
ARCHIVE_URL="https://github.com/Recurse-ML/rml/releases/latest/download/rml.tar.gz"

# Default installation directories following XDG Base Directory Specification
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_DIR="${XDG_DATA_HOME}/rml"
BIN_DIR="${XDG_BIN_HOME}"

TEMP_DIR="$(mktemp -d)"
BACKUP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

# Create directories if they don't exist
mkdir -p "$DATA_DIR"
mkdir -p "$BIN_DIR"

# Check Dependencies
declare -a DEPS=("git" "tar" "curl")
for dep in "${DEPS[@]}"; do
    if ! command -v "$dep" >/dev/null 2>&1; then
        echo "Error: $dep is not installed!"
        exit 1
    fi
done

echo "Downloading version information"
if ! curl -fsSL "$VERSION_URL" -o "${TEMP_DIR}/version.txt"; then
    echo "Error: Failed to download version information"
    exit 1
fi

echo "Downloading rml.tar.gz"
if ! curl -fsSL "$ARCHIVE_URL" -o "${TEMP_DIR}/rml.tar.gz"; then
    echo "Error: Download failed"
    exit 1
fi

if [ -d "$DATA_DIR/rml" ]; then
    echo "Backing up existing installation directory to $BACKUP_DIR/rml"
    mv "$DATA_DIR/rml" "$BACKUP_DIR/rml"
fi

# Install RML
echo "Extracting rml.tar.gz to $DATA_DIR/rml"
if ! tar -xzf "${TEMP_DIR}/rml.tar.gz" -C "$DATA_DIR"; then
    echo "Error: Extraction failed"
    exit 1
fi

# Copy version file to installation directory
echo "Installing version file"
if ! cp "${TEMP_DIR}/version.txt" "$DATA_DIR/rml/version.txt"; then
    echo "Error: Failed to copy version file"
    exit 1
fi

echo "Symlinking rml to $BIN_DIR/rml"
if ! ln -sf "$DATA_DIR/rml/rml" "$BIN_DIR/rml"; then
    echo "Error: Failed to create symbolic link"
    exit 1
fi

# Verify installation
echo "Finalizing installation (this might take a minute)"
if ! $BIN_DIR/rml --help &> /dev/null; then
    echo "Error: Installation verification failed"
    exit 1
fi

if ! rml --help &> /dev/null; then
    echo "WARNING: $BIN_DIR is not in your PATH, you should add it!"
fi

VERSION=$(cat "${TEMP_DIR}/version.txt")
echo "Successfully installed rml version $VERSION to $BIN_DIR/rml"
echo "Check files for bugs using \"rml <target filename>\" from within your repo"

#! /usr/bin/env bash

# Exit on error, undefined variables, and pipe failures
set -euo pipefail
trap 'echo "Error on line $LINENO"' ERR

# Configuration
VERSION_URL="https://storage.googleapis.com/squash-public/version.txt"
ARCHIVE_URL="https://storage.googleapis.com/squash-public/rml.tar.gz"
INSTALL_DIR="/usr/local/share"
BIN_DIR="/usr/local/bin"
TEMP_DIR="$(mktemp -d)"
BACKUP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

# Check if running with necessary privileges
if [ ! -w "$INSTALL_DIR" ] || [ ! -w "$BIN_DIR" ]; then
    echo "Error: Installation requires write access to $INSTALL_DIR and $BIN_DIR"
    exit 1
fi

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

if [ -d "$INSTALL_DIR/rml" ]; then
    echo "Backing up existing installation directory to $BACKUP_DIR/rml"
    mv "$INSTALL_DIR/rml" "$BACKUP_DIR/rml"
fi

# Install RML
echo "Extracting rml.tar.gz to $INSTALL_DIR/rml"
if ! tar -xzf "${TEMP_DIR}/rml.tar.gz" -C "$INSTALL_DIR"; then
    echo "Error: Extraction failed"
    exit 1
fi

# Copy version file to installation directory
echo "Installing version file"
if ! cp "${TEMP_DIR}/version.txt" "$INSTALL_DIR/rml/version.txt"; then
    echo "Error: Failed to copy version file"
    exit 1
fi

echo "Symlinking rml to $BIN_DIR/rml"
if ! ln -sf "$INSTALL_DIR/rml/rml" "$BIN_DIR/rml"; then
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

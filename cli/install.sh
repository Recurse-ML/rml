#! /usr/bin/env bash

# Exit on error, undefined variables, and pipe failures
set -euo pipefail
trap 'echo "Error on line $LINENO"' ERR


detect_arch() {
    local arch=$(uname -m | tr '[:upper:]' '[:lower:]')
    if [ "$arch" = "aarch64" ] || [ "$arch" = "arm64" ]; then
        echo "arm64"
    elif [ "$arch" = "x86_64" ] || [ "$arch" = "amd64" ]; then
        echo "amd64"
    fi
}

# Configuration
ARCH=$(detect_arch)
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
PLATFORM="${OS}-${ARCH}"
TARBALL_NAME="rml-${PLATFORM}.tar.gz"
ARCHIVE_URL="https://github.com/Recurse-ML/rml/releases/latest/download/${TARBALL_NAME}"
VERSION_URL="https://github.com/Recurse-ML/rml/releases/latest/download/version.txt"
VERSION=$(curl -fsSL "${VERSION_URL}")

# Installation directories
DATA_DIR="${XDG_DATA_HOME:-$HOME/.rml}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.rml/bin}"

# Create directories if they don't exist
mkdir -p "$DATA_DIR"
mkdir -p "$BIN_DIR"

TEMP_DIR="$(mktemp -d)"
BACKUP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT


# Check Dependencies
declare -a DEPS=("git" "tar" "curl")
for dep in "${DEPS[@]}"; do
    if ! command -v "$dep" >/dev/null 2>&1; then
        echo "Error: $dep is not installed!"
        exit 1
    fi
done

echo "Downloading rml tarball for platform: $PLATFORM"
if ! curl -fsSL "$ARCHIVE_URL" -o "${TEMP_DIR}/${TARBALL_NAME}"; then
    echo "Error: Download failed"
    exit 1
fi


if [ -d "$DATA_DIR/rml" ]; then
    echo "Backing up existing installation directory to $BACKUP_DIR/rml"
    mv "$DATA_DIR/rml" "$BACKUP_DIR/rml"
fi

# Install RML
echo "Extracting ${TARBALL_NAME} to $DATA_DIR/rml"
if ! tar -xzf "${TEMP_DIR}/${TARBALL_NAME}" -C "$DATA_DIR"; then
    echo "Error: Extraction failed"
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

detect_shell_config() {
    local shell_name
    local config_file
    
    # Get the current shell name
    shell_name=$(basename "$SHELL")
    
    case "$shell_name" in
        "bash")
            if [ -f "$HOME/.bash_profile" ]; then
                config_file="$HOME/.bash_profile"
            elif [ -f "$HOME/.bash_login" ]; then
                config_file="$HOME/.bash_login"
            elif [ -f "$HOME/.profile" ]; then
                config_file="$HOME/.profile"
            else
                config_file="$HOME/.bashrc"
            fi
            ;;
        "zsh")
            config_file="$HOME/.zshrc"
            ;;
        "fish")
            if [ -f "$HOME/.config/fish/config.fish" ]; then
                config_file="$HOME/.config/fish/config.fish"
            else
                config_file="$HOME/.fishrc"
            fi
            ;;
        "ksh")
            config_file="$HOME/.kshrc"
            ;;
        "tcsh")
            config_file="$HOME/.tcshrc"
            ;;
        "csh")
            config_file="$HOME/.cshrc"
            ;;
        *)
            # Default to .profile for other shells
            config_file="$HOME/.profile"
            ;;
    esac
    
    echo "$config_file"
}


echo "Successfully installed rml version $VERSION to $BIN_DIR/rml"
echo ""

echo "██████╗ ███╗   ███╗██╗          /\\ /\\ /\\"
echo "██╔══██╗████╗ ████║██║         (  ●  ● )"
echo "██████╔╝██╔████╔██║██║          \\  ∩  /"
echo "██╔══██╗██║╚██╔╝██║██║           \\___/"
echo "██║  ██║██║ ╚═╝ ██║███████╗      |||||"
echo "╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝     /|||||\\  "
echo "                               (_______)"
echo "                                ^  ^  ^"
echo ""
echo "🎉 RML is ready to hunt bugs! Happy coding! 🐛"
echo ""

echo "Quickstart:"
echo "1. 🚀 Go to local project."
echo "2. ✏️  Modify a file"
echo "3. 🐛 Run rml to catch bugs (or rml --help for more options)"
echo ""

if ! rml --help &> /dev/null; then
    echo "⚠️  SETUP REQUIRED:"
    if [ -n "$SHELL" ]; then
        SHELL_CONFIG=$(detect_shell_config)
        echo "To use rml from anywhere, add it to your PATH by running:"
        echo ""
        echo "    echo 'export PATH=\"\$PATH:$BIN_DIR\"' >> $SHELL_CONFIG"
        echo ""
        echo "Then restart your terminal or run: source $SHELL_CONFIG"
    else
        echo "Add $BIN_DIR to your PATH environment variable to use rml from anywhere"
    fi
fi

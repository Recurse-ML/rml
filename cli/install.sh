#!/bin/sh

# Exit on error and undefined variables
set -eu

# Ensure standard locations are in PATH for shells like dash in CI
export PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:$PATH"

# Trap common termination signals (SIGHUP, SIGINT, SIGQUIT, SIGTERM)
trap 'echo "An error occurred"' 1 2 3 15

# Detect architecture
detect_arch() {
    arch=$(uname -m | tr '[:upper:]' '[:lower:]')
    if [ "$arch" = "aarch64" ] || [ "$arch" = "arm64" ]; then
        echo "arm64"
    elif [ "$arch" = "x86_64" ] || [ "$arch" = "amd64" ]; then
        echo "amd64"
    else
        echo "unsupported"
        exit 1
    fi
}

# Configuration
ARCH=$(detect_arch)
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
PLATFORM="${OS}-${ARCH}"
TARBALL_NAME="rml-${PLATFORM}.tar.gz"
ARCHIVE_URL="https://github.com/Recurse-ML/rml/releases/latest/download/${TARBALL_NAME}"
VERSION_URL="https://github.com/Recurse-ML/rml/releases/latest/download/version.txt"
VERSION=$(curl -fsSL "$VERSION_URL" | tr -d '\n')

# Installation directories
DATA_DIR="${XDG_DATA_HOME:-$HOME/.rml}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.rml/bin}"

# Create directories if they don't exist
mkdir -p "$DATA_DIR"
mkdir -p "$BIN_DIR"

# Temporary directories
TEMP_DIR=$(mktemp -d)
BACKUP_DIR=$(mktemp -d)

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# Check dependencies
MISSING_DEPS=""
for dep in git tar curl; do
    if ! command -v "$dep" >/dev/null 2>&1; then
        MISSING_DEPS="$MISSING_DEPS $dep"
    fi
done

if [ -n "$MISSING_DEPS" ]; then
    echo "Error: Missing dependencies:$MISSING_DEPS"
    exit 1
fi

# Download tarball
echo "Downloading rml tarball for platform: $PLATFORM"
if ! curl -fsSL "$ARCHIVE_URL" -o "$TEMP_DIR/$TARBALL_NAME"; then
    echo "Error: Download failed"
    exit 1
fi

# Backup existing install
if [ -d "$DATA_DIR/rml" ]; then
    echo "Backing up existing installation directory to $BACKUP_DIR/rml"
    mv "$DATA_DIR/rml" "$BACKUP_DIR/rml"
fi

# Extract
echo "Extracting $TARBALL_NAME to $DATA_DIR/rml"
if ! tar -xzf "$TEMP_DIR/$TARBALL_NAME" -C "$DATA_DIR"; then
    echo "Error: Extraction failed"
    exit 1
fi

# Symlink
echo "Symlinking rml to $BIN_DIR/rml"
if ! ln -sf "$DATA_DIR/rml/rml" "$BIN_DIR/rml"; then
    echo "Error: Failed to create symbolic link"
    exit 1
fi

# Verify install
echo "Finalizing installation (this might take a minute)"
if ! "$BIN_DIR/rml" --help >/dev/null 2>&1; then
    echo "Error: Installation verification failed"
    exit 1
fi

# Shell config suggestion
detect_shell_config() {
    shell_name=$(basename "$SHELL")
    config_file=""
    if [ "$shell_name" = "bash" ]; then
        if [ -f "$HOME/.bash_profile" ]; then
            config_file="$HOME/.bash_profile"
        elif [ -f "$HOME/.bash_login" ]; then
            config_file="$HOME/.bash_login"
        elif [ -f "$HOME/.profile" ]; then
            config_file="$HOME/.profile"
        else
            config_file="$HOME/.bashrc"
        fi
    elif [ "$shell_name" = "zsh" ]; then
        config_file="$HOME/.zshrc"
    elif [ "$shell_name" = "fish" ]; then
        if [ -f "$HOME/.config/fish/config.fish" ]; then
            config_file="$HOME/.config/fish/config.fish"
        else
            config_file="$HOME/.fishrc"
        fi
    elif [ "$shell_name" = "ksh" ]; then
        config_file="$HOME/.kshrc"
    elif [ "$shell_name" = "tcsh" ]; then
        config_file="$HOME/.tcshrc"
    elif [ "$shell_name" = "csh" ]; then
        config_file="$HOME/.cshrc"
    else
        config_file="$HOME/.profile"
    fi
    echo "$config_file"
}

# Output success
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

if ! command -v rml >/dev/null 2>&1 || ! rml --help >/dev/null 2>&1; then
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

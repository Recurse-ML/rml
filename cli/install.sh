#! /usr/bin/env bash

echo "Installing RML"

# TODO: make repo public and use GH release URL
# https://github.com/Recurse-ML/rml/releases/rml.tar.gz
ARCHIVE_URL="https://storage.googleapis.com/squash-public/rml.tar.gz"
INSTALL_DIR="/usr/local/share/" # TODO: allow configuring INSTALL_DIR
BIN_DIR="/usr/local/bin/" # TODO: allow configuring BIN_DIR

## Check Dependencies (git, tar, curl)

# git
# TODO: display the full list of (missing) dependencies, upon failure
if ! command -v git >/dev/null 2>&1; then
    echo "Git is not installed!"
    exit 1
fi

# tar
if ! command -v tar >/dev/null 2>&1; then
    echo "Tar is not installed!"
    exit 1
fi

# curl
if ! command -v curl >/dev/null 2>&1; then
    echo "Curl is not installed!"
    exit 1
fi

## Install RML
# Download single dir app
curl $ARCHIVE_URL -o /tmp/rml.tar.gz
tar -xzf /tmp/rml.tar.gz -C $INSTALL_DIR


# Ensures `rml` is in the PATH
ln -s $INSTALL_DIR/rml/rml $BIN_DIR/rml

# Execute rml, to avoid cold start on first use
nohup rml --help &> /dev/null &

echo "Installed rml to $INSTALL_DIR/rml"
echo "Now you can execute rml from anywhere in your terminal"
echo "(if you can't, ensure $INSTALL_DIR is in your PATH)"

# TODO: add detailed usage instructions

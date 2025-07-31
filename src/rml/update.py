import sys
from importlib.metadata import version
from os import execv
from pathlib import Path

import click
from httpx import Client
from plumbum import FG, local

from rml.package_config import (
    HOST,
    INSTALL_URL,
    VERSION_CHECK_URL,
)
from rml.package_logger import logger


def get_local_version() -> str:
    return version("rml")


def get_remote_version() -> str:
    client = Client(base_url=HOST)
    response = client.get(VERSION_CHECK_URL, follow_redirects=True)
    response.raise_for_status()
    return response.text.strip()


def update_and_rerun_rml():
    remote_version = get_remote_version()

    try:
        logger.info(f"Updating rml to version {remote_version}...")
        (local["curl"][INSTALL_URL] | local["sh"]) & FG
    except Exception as e:
        logger.error(f"Failed to update rml: {e}")
        click.echo("rml requires latest version to run. Please update manually with:")
        click.echo(f"curl {INSTALL_URL} | sh")
        sys.exit(1)

    logger.info("Update successful!")

    # Automatically invoke the updated script with the full path
    full_path = sys.argv[0]
    original_args = sys.argv[1:]

    local[full_path][original_args] & FG
    executable_name = Path(full_path).name

    logger.info(f"Running updated command: {full_path} {' '.join(original_args)}")
    execv(full_path, [executable_name] + original_args)

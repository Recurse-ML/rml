import sys
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional

import backoff
import click
import pydantic
from httpx import Client, HTTPStatusError, RequestError
from plumbum import FG, ProcessExecutionError, local
from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

from rml.datatypes import APICommentResponse
from rml.package_config import (
    HOST,
    INSTALL_URL,
    PACKAGE_NAME,
    VERSION_CHECK_URL,
)
from rml.package_logger import logger
from rml.ui import Step, Workflow, render_comments

client = Client(base_url=HOST)


def get_local_version() -> str:
    return version(PACKAGE_NAME)


def get_remote_version() -> str:
    response = client.get(VERSION_CHECK_URL, follow_redirects=True)
    response.raise_for_status()
    return response.text.strip()


def raise_if_not_in_git_repo() -> None:
    git_check_retcode, _, _ = local["git"]["rev-parse", "--is-inside-work-tree"].run(
        retcode=None
    )

    if git_check_retcode != 0:
        raise ValueError(
            "Not a git repository. Please run this script in a git repository."
        )


def get_git_root() -> Path:
    """
    Get the root directory of the current Git repository.
    """
    try:
        git_root = local["git"]["rev-parse", "--show-toplevel"]()
        return Path(git_root.strip())
    except Exception:
        raise ValueError("Could not determine the Git root directory")


def should_retry_http_error(e: Exception) -> bool:
    if isinstance(e, HTTPStatusError):
        return e.response.status_code // 100 == 5
    return False


@backoff.on_exception(
    backoff.expo,
    (HTTPStatusError, RequestError),
    max_tries=5,
    max_time=30,
    giveup=should_retry_http_error,
)
def get_check_status(check_id: str) -> tuple[str, Optional[list[APICommentResponse]]]:
    try:
        response = client.get(f"/api/check/{check_id}/")
        response.raise_for_status()
        response_body = response.json()
        logger.debug(response_body)
        comments = response_body.get("comments", None)
        if comments is not None:
            comments = list(map(APICommentResponse.model_validate, comments))
        return (response_body["status"], comments)
    except pydantic.ValidationError as e:
        logger.error(
            "Failed to validate APICommentResponse model received from the server"
        )
        raise e


def raise_if_files_not_relative_to_git_root(
    filenames: list[str], git_root: Path
) -> None:
    """
    Validate that all files are within the git repository.
    Raises ValueError if any file attempts to escape the repository root.
    """
    for filename in filenames:
        try:
            full_path = (git_root / filename).resolve()
            full_path.relative_to(git_root)
        except ValueError as e:
            raise ValueError(
                f"Invalid path {filename} - attempting to access file outside repository"
            ) from e


def get_files_to_zip(
    target_filenames: list[str],
    tempdir: Path,
    base_commit: str,
    head_commit: Optional[str],
    **kwargs,
) -> dict[str, Any]:
    raise_if_not_in_git_repo()
    git_root: Path = get_git_root()
    raise_if_files_not_relative_to_git_root(target_filenames, git_root)

    base_dir = tempdir / "base"
    head_dir = tempdir / "head"
    base_dir.mkdir(exist_ok=True)
    head_dir.mkdir(exist_ok=True)

    with local.cwd(git_root):
        tracked_filenames = local["git"]["ls-files"]().splitlines()
        deleted_filenames = local["git"]["ls-files", "-d"]().splitlines()
        tracked_filenames = list(set(tracked_filenames) - set(deleted_filenames))
        untracked_target_filenames = list(
            set(target_filenames) - set(tracked_filenames)
        )

        all_filenames = tracked_filenames + untracked_target_filenames

        # Export files at base commit
        for filename in all_filenames:
            try:
                file_content = local["git"]["show", f"{base_commit}:{filename}"]()
                dst_path = base_dir / filename
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_text(file_content)
            except ProcessExecutionError:
                logger.debug(f"File {filename} not found in {base_commit=}")
            except UnicodeDecodeError:
                logger.debug(f"File {filename} is not a text file")

        # Export files at head commit or working directory
        for filename in all_filenames:
            try:
                if head_commit is None:
                    dst_path = head_dir / filename
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    source_path = git_root / filename
                    if source_path.exists():
                        dst_path.write_text(source_path.read_text())
                    else:
                        logger.debug(f"File {filename} not found in working directory")
                else:
                    file_content = local["git"]["show", f"{head_commit}:{filename}"]()
                    dst_path = head_dir / filename
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    dst_path.write_text(file_content)
            except ProcessExecutionError:
                logger.debug(f"File {filename} not found in {head_commit=}")
            except UnicodeDecodeError:
                logger.debug(f"File {filename} is not a text file")

    return dict(
        git_root=git_root,
        all_filenames=all_filenames,
        base_dir=base_dir,
        head_dir=head_dir,
    )


def make_tar(
    git_root: Path, base_dir: Path, head_dir: Path, tempdir: Path, **kwargs
) -> dict[str, Any]:
    repo_dir_name = git_root.name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    archive_filename = f"{repo_dir_name}_{timestamp}.tar.gz"
    archive_path = Path(f"{tempdir}/{archive_filename}")

    try:
        with local.cwd(tempdir):
            local["tar"][
                "-czf",
                archive_path,
                "-C",
                base_dir.parent,
                base_dir.name,
                "-C",
                head_dir.parent,
                head_dir.name,
            ]()
    except ProcessExecutionError as e:
        logger.error(f"Tar failed with exit code {e.retcode}")
        logger.info(f"stdout: {e.stdout}")
        logger.info(f"stderr: {e.stderr}")
        raise e

    return dict(archive_filename=archive_filename, archive_path=archive_path)


@backoff.on_exception(
    backoff.expo,
    (HTTPStatusError, RequestError),
    max_tries=5,
    max_time=30,
    giveup=should_retry_http_error,
)
def post_check(
    archive_filename: str, archive_path: Path, target_filenames: list[str], **kwargs
) -> dict[str, Any]:
    try:
        post_response = client.post(
            "/api/check/",
            files={"tar_file": (archive_filename, archive_path.open("rb"))},
            data={"target_filenames": target_filenames},
            timeout=None,
        )

        post_response.raise_for_status()

        return dict(check_id=post_response.json()["check_id"])
    except HTTPStatusError as e:
        logger.error(
            f"Recurse.ML server returned a failure status code in POST: ({e.response.status_code})"
        )
        raise e
    except RequestError as e:
        logger.error("Error occured while POSTing data to Recurse server")
        raise e


def check_analysis_results(check_id: str, **kwargs):
    check_status, comments = get_check_status(check_id)
    while check_status not in ["success", "error"]:
        time.sleep(0.5)
        check_status, comments = get_check_status(check_id)
    if comments is None:
        raise ValueError(
            "Could not analyze the results, server did not respond with comments"
        )
    return dict(check_status=check_status, comments=comments)


def analyze(target_filenames: list[str], base: str, head: str) -> None:
    """Checks for bugs in target_filenames."""
    console = Console()
    handler = RichHandler(
        console=console,
        show_time=False,
    )
    logger.addHandler(handler)

    if len(target_filenames) == 0:
        logger.warning("No target file, no bugs!")
        return

    # Recording the implicit assumptions here
    # Once we process the changes, these will become relevant
    base_commit = base
    head_commit = head  # current index state

    workflow_steps = [
        Step(name="Looking for local changes", func=get_files_to_zip),
        Step(name="Tarballing files", func=make_tar),
        Step(name="Sending tarball to server", func=post_check),
        Step(name="Waiting for analysis results", func=check_analysis_results),
    ]
    with TemporaryDirectory() as tempdir:
        logger.debug(f"Using temporary directory: {tempdir}")
        workflow = Workflow(
            steps=workflow_steps,
            console=console,
            logger=logger,
            inputs=dict(
                target_filenames=target_filenames,
                tempdir=Path(tempdir),
                base_commit=base_commit,
                head_commit=head_commit,
            ),
        )
        workflow_output = workflow.run()
    comments = workflow_output["comments"]

    render_comments(comments, console=console, logger=logger)

    if len(comments) == 0:
        summary_text = Text("✨ No issues found! Your code is sparkling clean! ✨")

    else:
        summary_text = Text(
            f"😱 Found {len(comments)} {'issue' if len(comments) == 1 else 'issues'}. Time to roll up your sleeves! 😱"
        )

    console.print(summary_text)


@click.command()
@click.argument("target_filenames", nargs=-1, type=click.Path(exists=True))
@click.option("--base", default="HEAD", help="Base commit to compare against")
@click.option(
    "--head",
    default=None,
    help="Head commit to analyze. If None analyzes uncommited changes.",
)
def main(target_filenames: list[str], base: str, head: str) -> None:
    try:
        local_version = get_local_version()
        remote_version = get_remote_version()
        if local_version != remote_version:
            if click.confirm(
                f"rml is not up to date (local: {local_version}, latest: {remote_version}), run the install.sh script?",
                default=False,
            ):
                (local["curl"][INSTALL_URL] | local["sh"]) & FG
            else:
                click.echo("rml requires latest version to run, please update")
                sys.exit(0)

    except Exception as e:
        logger.error(
            f"An error occured when checking for updates: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
        )
        sys.exit(1)

    try:
        analyze(target_filenames, base=base, head=head)
        sys.exit(0)
    except Exception as e:
        logger.error(
            f"\nAn error occured: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
        )
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()

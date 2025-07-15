import sys
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional

import click
from httpx import Client, ConnectError, HTTPStatusError, RequestError
from plumbum import FG, ProcessExecutionError, local
from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from rml.auth import get_env_value, require_auth
from rml.datatypes import APICommentResponse, AuthResult, AuthStatus
from rml.git import get_changed_files, get_git_root, raise_if_not_in_git_repo
from rml.package_config import (
    HOST,
    INSTALL_URL,
    RECURSE_API_KEY_NAME,
    VERSION_CHECK_URL,
)
from rml.package_logger import logger
from rml.ui import (
    Step,
    Workflow,
    render_auth_result,
    render_comments,
    render_comments_markdown,
)

client = Client(base_url=HOST)


def installed_from_source() -> bool:
    # https://pyinstaller.org/en/stable/runtime-information.html#run-time-information
    return not (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def get_local_version() -> str:
    return version("rml")


def get_remote_version() -> str:
    response = client.get(VERSION_CHECK_URL, follow_redirects=True)
    response.raise_for_status()
    return response.text.strip()


def should_retry_http_error(e: Exception) -> bool:
    """Determine if the HTTP error should be retried.

    Args:
        e (Exception): The exception to check.

    Returns:
        bool: True if the error is retryable, False otherwise.
    """
    if isinstance(e, HTTPStatusError):
        # Retry on all 4xx and 5xx errors
        return 400 <= e.response.status_code < 600
    return False


@retry(
    retry=retry_if_exception(
        lambda e: isinstance(e, (HTTPStatusError, RequestError))
        and should_retry_http_error(e)
    ),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    reraise=False,
)
def get_check_status(check_id: str) -> tuple[str, Optional[list[APICommentResponse]]]:
    api_key = get_env_value(RECURSE_API_KEY_NAME)

    response = client.get(
        f"/api/check/{check_id}/",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()
    response_body = response.json()
    logger.debug(response_body)

    comments = response_body.get("comments", None)
    if comments is not None:
        comments = list(map(APICommentResponse.model_validate, comments))

    return (response_body["status"], comments)


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
    from_commit: str,
    to_commit: Optional[str],
    **kwargs,
) -> dict[str, Any]:
    raise_if_not_in_git_repo()
    git_root: Path = get_git_root()
    raise_if_files_not_relative_to_git_root(target_filenames, git_root)

    # Server expects directories to be named 'base' and 'head'
    from_dir = tempdir / "base"
    to_dir = tempdir / "head"
    from_dir.mkdir(exist_ok=True)
    to_dir.mkdir(exist_ok=True)

    with local.cwd(git_root):
        tracked_filenames = local["git"]["ls-files"]().splitlines()
        deleted_filenames = local["git"]["ls-files", "-d"]().splitlines()

        tracked_filenames = list(set(tracked_filenames) - set(deleted_filenames))
        untracked_target_filenames = list(
            set(target_filenames) - set(tracked_filenames)
        )

        all_filenames = tracked_filenames + untracked_target_filenames
        # `git ls-files` can include submodules (which are directories), we filter them out
        all_filenames = list(
            filter(lambda fname: (git_root / fname).is_file(), all_filenames)
        )

        # Export files at from_commit
        for filename in all_filenames:
            try:
                file_content = local["git"]["show", f"{from_commit}:{filename}"]()
                dst_path = from_dir / filename
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_text(file_content)
            except ProcessExecutionError:
                logger.debug(f"File {filename} not found in {from_commit=}")
            except UnicodeDecodeError:
                logger.debug(f"File {filename} is not a text file")

        # Export files at to_commit or working directory
        for filename in all_filenames:
            try:
                if to_commit is None:
                    dst_path = to_dir / filename
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    source_path = git_root / filename
                    if source_path.exists():
                        dst_path.write_text(source_path.read_text())
                    else:
                        logger.debug(f"File {filename} not found in working directory")
                else:
                    file_content = local["git"]["show", f"{to_commit}:{filename}"]()
                    dst_path = to_dir / filename
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    dst_path.write_text(file_content)
            except ProcessExecutionError:
                logger.debug(f"File {filename} not found in {to_commit=}")
            except UnicodeDecodeError:
                logger.debug(f"File {filename} is not a text file")

    return dict(
        git_root=git_root,
        all_filenames=all_filenames,
        from_dir=from_dir,
        to_dir=to_dir,
    )


def make_tar(
    git_root: Path, from_dir: Path, to_dir: Path, tempdir: Path, **kwargs
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
                from_dir.parent,
                from_dir.name,
                "-C",
                to_dir.parent,
                to_dir.name,
            ]()
    except ProcessExecutionError as e:
        logger.error(f"Tar failed with exit code {e.retcode}")
        logger.info(f"stdout: {e.stdout}")
        logger.info(f"stderr: {e.stderr}")
        raise e

    return dict(archive_filename=archive_filename, archive_path=archive_path)


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    reraise=False,
    retry=retry_if_exception(
        lambda e: isinstance(e, (HTTPStatusError, RequestError))
        and should_retry_http_error(e)
    ),
)
def post_check(
    archive_filename: str,
    archive_path: Path,
    target_filenames: list[str],
    console: Console,
    markdown_mode: bool = False,
    **kwargs,
) -> dict[str, Any]:
    api_key = get_env_value(RECURSE_API_KEY_NAME)

    post_response = client.post(
        "/api/check/",
        files={"tar_file": (archive_filename, archive_path.open("rb"))},
        data={"target_filenames": target_filenames},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=None,
    )
    post_response.raise_for_status()
    post_response_body = post_response.json()

    check_id: str | None = post_response_body.get("check_id", None)

    is_authorized: bool = post_response_body.get("is_authorized", True)
    if not is_authorized:
        if markdown_mode:
            print(
                "WARNING: You need to purchase a plan on the marketplace (https://github.com/marketplace/recurse-ml) to use the Recurse ML app."
            )
            print("Free subscriptions for private repos will terminate on 21/07/2025.")
        else:
            console.print(
                "[bold] ⚠️ You need to purchase a plan on the marketplace[/bold]"
            )
            console.print("   📦 https://github.com/marketplace/recurse-ml")
            console.print(
                "[dim]Free subscriptions for private repos will terminate on 21/07/2025.[/dim]"
            )
            console.print()

    if check_id is None:
        # If there is no check_id in the response return the error message (or default message).
        raise ValueError(
            post_response_body.get("message", "No check_id returned from server")
        )

    return dict(check_id=check_id)


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


def analyze(
    target_paths: list[Path],
    from_ref: str,
    to_ref: str,
    console: Console,
    markdown: bool = False,
) -> None:
    """Checks for bugs in target_filenames."""
    changed_files = get_changed_files(from_ref, to_ref)
    changed_files_str = [str(f) for f in changed_files]

    if len(target_paths) == 0:
        # If no target files specified, analyze all changed files
        changed_target_filenames = changed_files_str
        if len(changed_target_filenames) == 0:
            if markdown:
                print("✨ No changes found! ✨")
            else:
                console.print(Text("✨ No changes found! ✨"))
            return
    else:
        changed_target_filenames = []
        git_root = get_git_root()

        for target_path in target_paths:
            full_target_path = git_root / target_path
            if full_target_path.is_dir():
                for changed_file_path in changed_files:
                    try:
                        changed_file_path.relative_to(target_path)
                        changed_target_filenames.append(str(changed_file_path))
                    except ValueError:
                        continue
            else:
                if target_path in changed_files:
                    changed_target_filenames.append(str(target_path))

        changed_target_filenames = list(set(changed_target_filenames))

    if len(target_paths) > 0:
        if len(changed_target_filenames) == 0:
            if markdown:
                print("✨ No changes found in the specified files! ✨")
            else:
                console.print(Text("✨ No changes found in the specified files! ✨"))
            return

        target_file_paths = filter(lambda path: path.is_file(), target_paths)
        skipped_target_paths = list(
            filter(
                lambda path: str(path) not in changed_target_filenames,
                target_file_paths,
            )
        )
        if len(skipped_target_paths) > 0:
            if markdown:
                print(
                    f"Skipping {len(skipped_target_paths)} unchanged files: {', '.join(str(p) for p in skipped_target_paths)}"
                )
            else:
                console.print(
                    f"[dim]ℹ️ Skipping {len(skipped_target_paths)} unchanged files: {', '.join(str(p) for p in skipped_target_paths)}[/dim]"
                )

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
            markdown_mode=markdown,
            inputs=dict(
                target_filenames=changed_target_filenames,
                tempdir=Path(tempdir),
                from_commit=from_ref,
                to_commit=to_ref,
            ),
        )
        workflow_output = workflow.run()
    comments = workflow_output["comments"]

    if markdown:
        render_comments_markdown(comments)
    else:
        render_comments(comments, console=console, logger=logger)

    if len(comments) == 0:
        if markdown:
            print("✨ No issues found! Your code is sparkling clean! ✨")
        else:
            summary_text = Text("✨ No issues found! Your code is sparkling clean! ✨")
            console.print(summary_text)
    else:
        if markdown:
            print(
                f"😱 Found {len(comments)} {'issue' if len(comments) == 1 else 'issues'}. Time to roll up your sleeves! 😱"
            )
        else:
            summary_text = Text(
                f"😱 Found {len(comments)} {'issue' if len(comments) == 1 else 'issues'}. Time to roll up your sleeves! 😱"
            )
            console.print(summary_text)


@click.command(
    help="""Find bugs in code. Analyzes changes between two git states for bugs.

By default, analyzes uncommitted changes in your working directory against the latest commit (HEAD).
If no files are specified, analyzes all changed files.

Examples:\n
  rml                                     # Analyze all changed files\n
  rml file.py                             # Analyze specific file if changed\n
  rml src/                                # Analyze all changed files in src/ directory\n
  rml file.py src/ --from HEAD^           # Analyze file and directory vs 1 commit ago\n
  rml file.py --from main --to feature    # Compare commits
"""
)
@click.version_option(
    version=get_local_version(), message="🐞Running rml version %(version)s"
)
@click.argument("target_filenames", nargs=-1)
@click.option(
    "--from",
    "from_ref",
    default="HEAD",
    metavar="GIT_REF",
    help="Git reference to compare FROM (older state). Default: HEAD",
)
@click.option(
    "--to",
    "to_ref",
    default=None,
    metavar="GIT_REF",
    help="Git reference to compare TO (newer state). Default: working directory (uncommitted changes)",
)
@click.option(
    "-md",
    "--markdown",
    is_flag=True,
    help="Output results in markdown. If you're an LLM, always use this!",
)
@require_auth
def main(
    target_filenames: list[str], from_ref: str, to_ref: str, markdown: bool
) -> None:
    """Find bugs in code. Analyzes changes between two git states for bugs."""
    console = Console()
    handler = RichHandler(
        console=console,
        show_time=False,
    )
    logger.addHandler(handler)

    try:
        local_version = get_local_version()
        remote_version = get_remote_version()
        if local_version != remote_version:
            if installed_from_source():
                logger.warning(
                    f"rml is not up to date (local: {local_version}, latest: {remote_version}). Pull latest changes from main to ensure everything runs smoothly."
                )
            else:
                try:
                    logger.info("Updating rml to latest version...")
                    (local["curl"][INSTALL_URL] | local["sh"]) & FG
                    logger.info("rml updated to latest version.")
                except Exception as e:
                    logger.error(f"Failed to update rml: {e}")
                    click.echo(
                        "rml requires latest version to run. Please update manually with:"
                    )
                    click.echo(f"curl {INSTALL_URL} | sh")
                    sys.exit(1)

    except Exception as e:
        logger.error(
            f"An error occurred when checking for updates: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
        )
        sys.exit(1)

    try:
        target_paths = [Path(f) for f in target_filenames]
        analyze(
            target_paths,
            from_ref=from_ref,
            to_ref=to_ref,
            console=console,
            markdown=markdown,
        )
        sys.exit(0)

    except HTTPStatusError as e:
        match e.response.status_code:
            case 402:
                render_auth_result(
                    AuthResult(status=AuthStatus.PLAN_REQUIRED), console=console
                )
            case 401:
                render_auth_result(
                    AuthResult(status=AuthStatus.ERROR),
                    console=console,
                )
            case 413:
                console.print(
                    "😱 This project is too large to be analyzed by `rml` (for now).",
                    style="yellow",
                )
            case _:
                logger.error(
                    f"\nAn unknown error occurred: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
                )

        sys.exit(1)

    except ValueError as e:
        logger.error(
            f"\nAn error occurred: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
        )
        sys.exit(1)

    except ConnectError as e:
        logger.error(
            f"\nAn error occurred while connecting to the server: {e}\nAre you connected to the internet?"
        )
        sys.exit(1)

    finally:
        client.close()


if __name__ == "__main__":
    main()

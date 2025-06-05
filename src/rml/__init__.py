import asyncio
import sys
import time
import webbrowser
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional

import backoff
import click
from httpx import Client, HTTPStatusError, RequestError
from plumbum import FG, ProcessExecutionError, local
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

from rml.auth import (
    authenticate_with_github,
    clear_env_data,
    get_env_value,
    is_authenticated,
    require_auth,
)
from rml.datatypes import APICommentResponse
from rml.package_config import (
    GITHUB_ACCESS_TOKEN_KEYNAME,
    GITHUB_USER_ID_KEYNAME,
    HOST,
    INSTALL_URL,
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


def giveup_on_http_error(e: Exception) -> bool:
    if isinstance(e, HTTPStatusError):
        # Give up on 401 (failed auth), 402 (subscription required), and 5xx errors
        return (
            e.response.status_code // 100 == 5
            or e.response.status_code == 401
            or e.response.status_code == 402
        )
    return True


@backoff.on_exception(
    backoff.expo,
    (HTTPStatusError, RequestError),
    max_tries=5,
    max_time=30,
    giveup=giveup_on_http_error,
)
def get_check_status(check_id: str) -> tuple[str, Optional[list[APICommentResponse]]]:
    access_token = get_env_value(GITHUB_ACCESS_TOKEN_KEYNAME)
    user_id = get_env_value(GITHUB_USER_ID_KEYNAME)

    response = client.get(
        f"/api/check/{check_id}/",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"user_id": user_id},
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


@backoff.on_exception(
    backoff.expo,
    (HTTPStatusError, RequestError),
    max_tries=5,
    max_time=30,
    giveup=giveup_on_http_error,
)
def post_check(
    archive_filename: str, archive_path: Path, target_filenames: list[str], **kwargs
) -> dict[str, Any]:
    access_token = get_env_value(GITHUB_ACCESS_TOKEN_KEYNAME)
    user_id = get_env_value(GITHUB_USER_ID_KEYNAME)

    post_response = client.post(
        "/api/check/",
        files={"tar_file": (archive_filename, archive_path.open("rb"))},
        data={"target_filenames": target_filenames, "user_id": user_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=None,
    )
    post_response.raise_for_status()

    return dict(check_id=post_response.json()["check_id"])


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
    target_filenames: list[str],
    from_ref: str,
    to_ref: str,
    console: Console,
    markdown: bool = False,
) -> None:
    """Checks for bugs in target_filenames."""
    if len(target_filenames) == 0:
        logger.warning("No target file, no bugs!")
        return

    # Recording the implicit assumptions here
    # Once we process the changes, these will become relevant
    from_commit = from_ref
    to_commit = to_ref  # current index state

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
                target_filenames=target_filenames,
                tempdir=Path(tempdir),
                from_commit=from_commit,
                to_commit=to_commit,
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


@click.group()
@click.version_option(
    version=get_local_version(), message="🐞Running rml version %(version)s"
)
def cli():
    """Find bugs in code. Analyzes changes between two git states for bugs."""
    pass


@cli.group()
def auth():
    """Authentication commands"""
    pass


@auth.command()
def login():
    """Authenticate with GitHub"""
    result = asyncio.run(authenticate_with_github())
    render_auth_result(result, console=Console())


@auth.command()
def logout():
    """Clear authentication credentials"""
    clear_env_data([GITHUB_ACCESS_TOKEN_KEYNAME, GITHUB_USER_ID_KEYNAME])
    click.echo("✅ Logged out successfully")


@auth.command()
def status():
    """Show authentication status"""
    if is_authenticated():
        click.echo("✅ Authenticated")
    else:
        click.echo("❌ Not authenticated")


@cli.command(
    help="""Find bugs in code. Analyzes changes between two git states for bugs.

By default, analyzes uncommitted changes in your working directory against the latest commit (HEAD).

Examples:\n
  rml analyze file.py                             # Analyze uncommitted changes\n
  rml analyze file.py --from HEAD^                # Compare vs 1 commit ago\n
  rml analyze file.py --from main --to feature    # Compare commits
"""
)
@click.argument("target_filenames", nargs=-1, type=click.Path(exists=True))
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
def analyze_cmd(
    target_filenames: list[str], from_ref: str, to_ref: str, markdown: bool
) -> None:
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
            f"An error occured when checking for updates: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
        )
        sys.exit(1)

    try:
        analyze(
            target_filenames,
            from_ref=from_ref,
            to_ref=to_ref,
            console=console,
            markdown=markdown,
        )
        sys.exit(0)
    except HTTPStatusError as e:
        if e.response.status_code == 402:
            panel = Panel(
                "[bold yellow]Subscription Required[/bold yellow]\n\n"
                "To analyze your code with rml, you need an active subscription.\n"
                "Please purchase a plan to continue.\n\n"
                "[link]https://github.com/marketplace/recurse-ml[/link]",
                title="💳 Plan Needed",
                border_style="yellow",
            )
            console.print(panel)

            if click.confirm(
                "Would you like to open the marketplace in your browser?", default=True
            ):
                webbrowser.open("https://github.com/marketplace/recurse-ml")

            sys.exit(1)
        elif e.response.status_code == 401:
            logger.error("❌ Authentication failed. Please run `rml auth login` again.")
            sys.exit(1)
        else:
            logger.error(
                f"\nHTTP error occurred: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
            )
            sys.exit(1)

    except ValueError as e:
        logger.error(
            f"\nAn error occured: {e}\nPlease submit an issue on https://github.com/Recurse-ML/rml/issues/new with the error message and the command you ran."
        )
        sys.exit(1)

    finally:
        client.close()


if __name__ == "__main__":
    cli()

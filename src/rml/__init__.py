import click
import pydantic

from typing import Any, Optional
from datetime import datetime
import time
from httpx import Client, HTTPStatusError, RequestError
from plumbum import ProcessExecutionError, local
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.text import Text
from rml.datatypes import Comment
from rml.package_config import HOST, ENV, console, logger
from rml.ui import Workflow, Step, render_comments

client = Client(base_url=HOST)


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


def get_check_status(check_id: str) -> tuple[str, Optional[list[Comment]]]:
    try:
        response = client.get(f"/api/check/{check_id}/")
        response.raise_for_status()
        response_body = response.json()
        logger.debug(response_body)
        comments = response_body.get("comments", None)
        if comments is not None:
            comments = list(map(Comment.model_validate, comments))
        return (response_body["status"], comments)
    except pydantic.ValidationError as e:
        logger.error("Failed to validate Comment model received from the server")
        raise e
    except HTTPStatusError as e:
        logger.error(
            f"Recurse.ML server returned a failure status code: ({response.status_code})"
        )
        raise e
    except RequestError as e:
        logger.error("Error occured while connecting to recurse server")
        raise e


def get_check_status_mock(check_id: str) -> tuple[str, Optional[list[Comment]]]:
    return (
        "completed",
        [
            Comment(
                relative_path="src/rml/__init__.py",
                line_no=80,
                body="This will cause some bug",
                head_source="",
            ),
            Comment(
                relative_path="src/rml/__init__.py",
                line_no=200,
                body="This will cause another bug",
                head_source="",
            ),
            Comment(
                relative_path="src/rml/datatypes.py",
                line_no=30,
                body="This will not integrate well",
                head_source="",
            ),
        ],
    )


def get_files_to_zip(target_filenames: list[str], **kwargs) -> dict[str, Any]:
    raise_if_not_in_git_repo()
    git_root: Path = get_git_root()
    with local.cwd(git_root):
        tracked_filenames = local["git"]["ls-files"]().splitlines()
        deleted_filenames = local["git"]["ls-files", "-d"]().splitlines()
        tracked_filenames = list(set(tracked_filenames) - set(deleted_filenames))

        untracked_target_filenames = list(
            set(target_filenames) - set(tracked_filenames)
        )

        # HACK: assumes `.git/` repo is at the project root
        #       not always the case
        git_dir_filenames = local["find"][".git/", "-type", "f"]().splitlines()
    all_filenames = git_dir_filenames + tracked_filenames + untracked_target_filenames

    return dict(
        git_root=git_root,
        all_filenames=all_filenames,
    )


def make_tar(
    git_root: Path, all_filenames: list[str], tempdir: str, **kwargs
) -> dict[str, Any]:
    repo_dir_name = git_root.name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    archive_filename = f"{repo_dir_name}_{timestamp}.tar.gz"
    archive_path = Path(f"{tempdir}/{archive_filename}")
    with local.cwd(git_root):
        try:
            local["tar"]["-czf", archive_path, *all_filenames]()
        except ProcessExecutionError as e:
            logger.error(f"Tar failed with exit code {e.retcode}")
            logger.info(f"stdout: {e.stdout}")
            logger.info(f"stderr: {e.stderr}")
            raise e

    return dict(archive_filename=archive_filename, archive_path=archive_path)


def post_check(
    archive_filename: str, archive_path: Path, target_filenames: list[str], **kwargs
) -> dict[str, Any]:
    try:
        post_response = client.post(
            "/api/check/",
            files={"tar_file": (archive_filename, archive_path.open("rb"))},
            data={"target_filenames": target_filenames},
            timeout=20,
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
    status_check_fn = get_check_status_mock if ENV == "testing" else get_check_status
    check_status, comments = status_check_fn(check_id)
    while check_status not in ["completed", "error"]:
        time.sleep(0.5)
        check_status, comments = status_check_fn(check_id)
    if comments is None:
        raise ValueError(
            "Could not analyze the results, server did not respond with comments"
        )
    return dict(check_status=check_status, comments=comments)


def analyze(target_filenames: list[str]) -> None:
    """Checks for bugs in target_filenames."""
    if len(target_filenames) == 0:
        logger.warning("No target file, no bugs!")
        return
    # Recording the implicit assumptions here
    # Once we process the changes, these will become relevant
    base_commit = "HEAD"
    head_commit = "INDEX"  # current index state

    workflow_steps = [
        Step(name="Analyze git repo", func=get_files_to_zip),
        Step(name="Tarballing repo files", func=make_tar),
        Step(name="Sending tarball to server", func=post_check),
        Step(name="Collecting analysis results", func=check_analysis_results),
    ]
    with TemporaryDirectory() as tempdir:
        logger.info(f"Using temporary directory: {tempdir}")
        workflow = Workflow(
            steps=workflow_steps,
            console=console,
            logger=logger,
            inputs=dict(target_filenames=target_filenames, tempdir=tempdir),
        )
        workflow_output = workflow.run()
    comments = workflow_output["comments"]

    render_comments(comments, console=console, logger=logger)

    summary_text = Text("Found ")
    summary_text += Text(
        f"{len(comments)}",
        style="white on red" if len(comments) > 0 else "white on blue",
    )
    summary_text += " issues!"
    console.print(summary_text)


@click.command()
@click.argument("target_filenames", nargs=-1, type=click.Path(exists=True))
def main(target_filenames: list[str]) -> int:
    ret_code = 0

    try:
        analyze(target_filenames)
    except Exception as e:
        logger.exception(
            f"\nAn error occured: {e}\nPlease report this to abc@discord.com"
        )
        ret_code = 1
    finally:
        client.close()
    return ret_code


if __name__ == "__main__":
    main()

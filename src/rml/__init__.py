import click
import sys
from typing import Optional
from datetime import datetime
import time
from httpx import Client, HTTPStatusError
from plumbum import local
from pathlib import Path
from tempfile import TemporaryDirectory

from rml.datatypes import Comment
from rml.package_config import HOST

client = Client(base_url=HOST)


def pformat_comment(comment: Comment) -> str:
    """Pretty format a comment."""
    pretty_output = f"{comment.relative_path}:{comment.line_no}\n"
    target_line = comment.head_source.splitlines()[comment.line_no - 1]
    pretty_output += f">>  {target_line}\n"
    pretty_output += comment.body + "\n"

    if comment.documentation_url is not None:
        pretty_output += f"More info: {comment.documentation_url}\n"
    return pretty_output


def exit_if_not_in_git_repo() -> None:
    git_check_retcode, _, _ = local["git"]["rev-parse", "--is-inside-work-tree"].run(retcode=None)

    if git_check_retcode != 0:
        print("Not a git repository. Please run this script in a git repository.")
        sys.exit(1)


def get_git_root() -> Path:
    """
    Get the root directory of the current Git repository.
    """
    try:
        git_root = local["git"]["rev-parse", "--show-toplevel"]()
        return Path(git_root.strip())
    except Exception as e:
        raise RuntimeError("Could not determine the Git root directory.") from e


def get_check_status(check_id: str) -> tuple[str, Optional[list[Comment]]]:
    try:
        response = client.get(f"/api/check/{check_id}/")
        response.raise_for_status()
        response_body = response.json()
        print(response_body)
        comments = response_body.get("comments", None)
        if comments is not None:
            comments = list(map(Comment.model_validate, comments))
        return (response_body["status"], comments)
    except HTTPStatusError:
        print(f"Error connecting to RECURSE_SERVER ({response.status_code})")
        sys.exit(1)

def post_check(archive_filename: str, archive_path: Path, target_filenames: list[str]) -> str:
    try:
        post_response = client.post(
            "/api/check/",
            files={"tar_file": (archive_filename, archive_path.open("rb"))},
            data={"target_filenames": target_filenames},
            timeout=10.0
        )

        post_response.raise_for_status()
        return post_response.json()["check_id"]
    except HTTPStatusError as e:
        print(f"Error posting a check to RECURSE_SERVER ({e.response.status_code})")
        sys.exit(1)


@click.command()
@click.argument("target_filenames", nargs=-1, type=click.Path(exists=True))
def main(target_filenames: list[str]) -> None:
    """ Checks for bugs in target_filenames.
    """
    if len(target_filenames) == 0:
        print("No target file, no bugs!")
        return

    exit_if_not_in_git_repo()
    git_root: Path = get_git_root()

    # Recording the implicit assumptions here
    # Once we process the changes, these will become relevant
    base_commit = "HEAD"
    head_commit = "INDEX"  # current index state

    # Gzip current repo at base_commit
    # Create a tarball from all tracked filenames
    with local.cwd(git_root), TemporaryDirectory() as tempdir:
        tracked_filenames = local["git"]["ls-files"]().splitlines()

        untracked_target_filenames = list(set(target_filenames) - set(tracked_filenames))

        # HACK: assumes `.git/` repo is at the project root
        #       not always the case
        git_dir_filenames = local["find"][".git/", "-type", "f"]().splitlines()

        all_filenames = git_dir_filenames + tracked_filenames + untracked_target_filenames

        repo_dir_name = git_root.name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        archive_filename = f"{repo_dir_name}_{timestamp}.tar.gz"
        archive_path = Path(f"{tempdir}/{archive_filename}")
        local["tar"]["-czf", archive_path, *all_filenames]()

        check_id = post_check(archive_filename, archive_path, target_filenames)

    check_status, comments = get_check_status(check_id)

    while check_status not in ["completed", "error"]:
        time.sleep(0.5)
        check_status, comments = get_check_status(check_id)

    if comments is None:
        print("Analysis failed!")
        sys.exit(1)

    for comment in comments:
        print(pformat_comment(comment))

    print(f"Found {len(comments)} issues!")


if __name__ == "__main__":
    try:
        main()
    finally:
        client.close()

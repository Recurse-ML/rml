from pathlib import Path
from typing import Optional

from plumbum import local


def raise_if_not_in_git_repo() -> None:
    """
    Raise ValueError if the current directory is not inside a git repository.
    """
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

    Returns:
        Path to the git repository root

    Raises:
        ValueError: If not in a git repository or can't determine root
    """
    try:
        git_root = local["git"]["rev-parse", "--show-toplevel"]()
        return Path(git_root.strip())
    except Exception:
        raise ValueError("Could not determine the Git root directory")


def get_changed_files(from_ref: str, to_ref: Optional[str] = None) -> list[str]:
    """
    Get the list of files that have changed between two git references.

    Args:
        from_ref: The base commit/reference
        to_ref: The target commit/reference. If None, compares against working directory.

    Returns:
        List of relative file paths that have changed

    Raises:
        ValueError: If not in a git repository
        ProcessExecutionError: If git commands fail
    """
    raise_if_not_in_git_repo()

    with local.cwd(get_git_root()):
        if to_ref is None:
            # Compare against working directory - include both modified and untracked files
            # Get modified/deleted files
            changed_files = local["git"]["diff", "--name-only", from_ref]().splitlines()
            # Get untracked files (newly added files that aren't committed yet)
            untracked_files = local["git"][
                "ls-files", "--others", "--exclude-standard"
            ]().splitlines()
            all_changed_files = changed_files + untracked_files
        else:
            # Compare between two commits
            all_changed_files = local["git"][
                "diff", "--name-only", from_ref, to_ref
            ]().splitlines()

        # Filter out empty strings and remove duplicates
        return list(set(f for f in all_changed_files if f.strip()))

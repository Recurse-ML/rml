import os
import subprocess


def test_e2e():
    bug_branch = os.environ.get("BUG_BRANCH")
    assert bug_branch is not None, "BUG_BRANCH is not set"
    result = subprocess.run(
        [
            "rml",
            "-md",
            "--from",
            bug_branch,
            "--to",
            "main",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # TODO (Armin): verify reported output

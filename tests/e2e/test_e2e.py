import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.timeout(300)
def test_e2e():
    test_repo = os.environ.get("TEST_REPO")
    assert test_repo is not None, "TEST_REPO is not set"
    test_repo = Path(test_repo)
    assert test_repo.exists(), "TEST_REPO does not exist"

    bug_branch = os.environ.get("BUG_BRANCH")
    assert bug_branch is not None, "BUG_BRANCH is not set"
    result = subprocess.run(
        [
            "rml",
            "-md",
            "--from",
            bug_branch,
            "--to",
            "origin/main",
        ],
        stdout=subprocess.PIPE,
        text=True,
        cwd=test_repo,
    )
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0
    assert "Time to roll up your sleeves!" in result.stdout

import os
import shutil
import subprocess
import sys
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
    rml_path = shutil.which("rml")
    assert rml_path is not None, "rml is not on PATH"
    result = subprocess.run(
        [
            rml_path,
            "-md",
            "--from",
            bug_branch,
            "--to",
            "main",
        ],
        stdout=sys.stdout,
        text=True,
        cwd=test_repo,
    )
    assert result.returncode == 0
    # TODO (Armin): verify reported output

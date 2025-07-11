from pathlib import Path

import pytest
from plumbum import local

from rml.git import get_changed_files, get_git_root, raise_if_not_in_git_repo


@pytest.fixture(scope="function")
def git_repo(tmp_path):
    """Create a temporary git repository with known commits."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo using plumbum
    with local.cwd(repo_path):
        local["git"]["init"]()
        local["git"]["config", "user.email", "test@example.com"]()
        local["git"]["config", "user.name", "Test User"]()

        # Create initial files and commit
        (repo_path / "file1.py").write_text("print('hello')")
        (repo_path / "file2.py").write_text("print('world')")
        local["git"]["add", "."]()
        local["git"]["commit", "-m", "Initial commit"]()

        # Create second commit with changes
        (repo_path / "file1.py").write_text("print('hello updated')")
        (repo_path / "file3.py").write_text("print('new file')")
        local["git"]["add", "."]()
        local["git"]["commit", "-m", "Second commit"]()

    return repo_path


def test_raise_if_not_in_git_repo_success(git_repo):
    """Test that raise_if_not_in_git_repo passes when in a git repository."""
    with local.cwd(git_repo):
        raise_if_not_in_git_repo()


def test_raise_if_not_in_git_repo_failure(tmp_path):
    """Test that raise_if_not_in_git_repo raises when not in a git repository."""
    non_git_dir = tmp_path / "not_a_git_repo"
    non_git_dir.mkdir()

    with local.cwd(non_git_dir):
        with pytest.raises(ValueError, match="Not a git repository"):
            raise_if_not_in_git_repo()


def test_get_git_root(git_repo):
    """Test getting the git repository root."""
    with local.cwd(git_repo):
        root = get_git_root()
        assert root == git_repo


def test_get_git_root_failure(tmp_path):
    """Test that get_git_root raises when not in a git repository."""
    non_git_dir = tmp_path / "not_a_git_repo"
    non_git_dir.mkdir()

    with local.cwd(non_git_dir):
        with pytest.raises(
            ValueError, match="Could not determine the Git root directory"
        ):
            get_git_root()


def test_get_changed_files_between_commits(git_repo):
    """Test getting changed files between two commits."""
    with local.cwd(git_repo):
        changed_files = get_changed_files("HEAD~1", "HEAD")

        # Should include modified and new files
        assert Path("file1.py") in changed_files
        assert Path("file3.py") in changed_files
        assert Path("file2.py") not in changed_files  # unchanged
        assert len(changed_files) == 2


def test_get_changed_files_working_directory(git_repo):
    """Test getting changed files between commit and working directory."""
    with local.cwd(git_repo):
        # Make some changes in working directory
        (git_repo / "file1.py").write_text("print('working directory change')")
        (git_repo / "file4.py").write_text("print('new working file')")

        changed_files = get_changed_files("HEAD")

        # Should include modified and new files in working directory
        assert Path("file1.py") in changed_files
        assert Path("file4.py") in changed_files
        assert Path("file2.py") not in changed_files  # unchanged
        assert Path("file3.py") not in changed_files  # unchanged


def test_get_changed_files_no_changes(git_repo):
    """Test getting changed files when there are no changes."""
    with local.cwd(git_repo):
        # Compare HEAD with itself
        changed_files = get_changed_files("HEAD", "HEAD")

        # Should be empty
        assert changed_files == []


def test_get_changed_files_single_file_change(git_repo):
    """Test getting changed files when only one file changes."""
    with local.cwd(git_repo):
        # Create a new commit with only one file change
        (git_repo / "file2.py").write_text("print('world updated')")
        local["git"]["add", "file2.py"]()
        local["git"]["commit", "-m", "Update file2"]()

        changed_files = get_changed_files("HEAD~1", "HEAD")

        assert changed_files == [Path("file2.py")]


def test_get_changed_files_multiple_scenarios(git_repo):
    """Test multiple scenarios in sequence."""
    with local.cwd(git_repo):
        # Scenario 1: Add a new file
        (git_repo / "config.py").write_text("DEBUG = True")
        local["git"]["add", "config.py"]()
        local["git"]["commit", "-m", "Add config"]()

        changed_files = get_changed_files("HEAD~1", "HEAD")
        assert changed_files == [Path("config.py")]

        # Scenario 2: Modify multiple files
        (git_repo / "file1.py").write_text("print('hello again')")
        (git_repo / "config.py").write_text("DEBUG = False")
        local["git"]["add", "."]()
        local["git"]["commit", "-m", "Update multiple files"]()

        changed_files = get_changed_files("HEAD~1", "HEAD")
        assert set(changed_files) == {Path("file1.py"), Path("config.py")}

        # Scenario 3: Delete a file
        (git_repo / "file3.py").unlink()
        local["git"]["add", "."]()
        local["git"]["commit", "-m", "Delete file3"]()

        changed_files = get_changed_files("HEAD~1", "HEAD")
        assert changed_files == [
            Path("file3.py")
        ]  # Deleted files still show up in diff


def test_get_changed_files_empty_strings_filtered(git_repo):
    """Test that empty strings are filtered out from git output."""
    with local.cwd(git_repo):
        # This test ensures our filtering logic works
        # Even if git returns empty lines, they should be filtered out
        changed_files = get_changed_files("HEAD~1", "HEAD")

        assert all(len(str(f).strip()) > 0 for f in changed_files)
        assert Path("") not in changed_files


def test_get_changed_files_with_subdirectories(git_repo):
    """Test getting changed files in subdirectories."""
    with local.cwd(git_repo):
        # Create subdirectory structure
        (git_repo / "src").mkdir()
        (git_repo / "tests").mkdir()
        (git_repo / "src" / "main.py").write_text("def main(): pass")
        (git_repo / "tests" / "test_main.py").write_text("def test_main(): pass")

        local["git"]["add", "."]()
        local["git"]["commit", "-m", "Add subdirectories"]()

        # Modify files in subdirectories
        (git_repo / "src" / "main.py").write_text("def main(): print('updated')")
        (git_repo / "tests" / "test_new.py").write_text("def test_new(): pass")

        local["git"]["add", "."]()
        local["git"]["commit", "-m", "Update subdirectory files"]()

        changed_files = get_changed_files("HEAD~1", "HEAD")

        # Should include files with relative paths
        assert Path("src/main.py") in changed_files
        assert Path("tests/test_new.py") in changed_files
        assert Path("tests/test_main.py") not in changed_files  # unchanged


def test_get_changed_files_invalid_ref(git_repo):
    """Test error handling for invalid git references."""
    with local.cwd(git_repo):
        # This should raise an exception due to invalid git reference
        with pytest.raises(Exception):  # plumbum.ProcessExecutionError
            get_changed_files("invalid-ref", "HEAD")


def test_get_changed_files_outside_git_repo(tmp_path):
    """Test error handling when not in a git repository."""
    # Create a directory that's not a git repo
    non_git_dir = tmp_path / "not_a_git_repo"
    non_git_dir.mkdir()

    with local.cwd(non_git_dir):
        # Should raise ValueError because it's not a git repo
        with pytest.raises(ValueError, match="Not a git repository"):
            get_changed_files("HEAD")


def test_get_changed_files_duplicates_removed(git_repo):
    """Test that duplicate files are removed from the result."""
    with local.cwd(git_repo):
        # This test ensures our deduplication logic works
        changed_files = get_changed_files("HEAD~1", "HEAD")

        assert len(changed_files) == len(set(changed_files))


def test_get_changed_files_integration_with_analyze():
    """Integration test to verify get_changed_files works with analyze function."""
    from unittest.mock import Mock, patch

    from rich.console import Console

    from rml import analyze

    console = Mock(spec=Console)

    with patch("rml.get_changed_files") as mock_get_changed:
        mock_get_changed.return_value = [Path("file1.py"), Path("file2.py")]

        with patch("rml.TemporaryDirectory"), patch("rml.Workflow") as mock_workflow:
            mock_workflow_instance = Mock()
            mock_workflow.return_value = mock_workflow_instance
            mock_workflow_instance.run.return_value = {"comments": []}

            # Test analyze with no target files - should analyze all changed files
            analyze([], "HEAD", None, console, markdown=True)

            # Verify get_changed_files was called
            mock_get_changed.assert_called_once_with("HEAD", None)

            # Verify workflow was called with all changed files
            mock_workflow.assert_called_once()
            args, kwargs = mock_workflow.call_args
            assert kwargs["inputs"]["target_filenames"] == ["file1.py", "file2.py"]

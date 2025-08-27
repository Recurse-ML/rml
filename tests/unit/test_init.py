import httpx
import pytest
from tenacity import RetryError

import rml.__init__ as rml_init
from rml.package_config import GET_CHECK_ROUTE, HOST, POST_CHECK_ROUTE


@pytest.fixture(autouse=True)
def disable_sleep(monkeypatch):
    """Disable sleep for fast tests."""
    monkeypatch.setattr("time.sleep", lambda x: None)
    monkeypatch.setattr("tenacity.nap.sleep", lambda x: None)


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Mock environment variables."""
    monkeypatch.setattr("rml.__init__.get_env_value", lambda name: "test-token")


def test_get_check_status_retries_on_read_timeout_then_succeeds(respx_mock):
    """Should retry on ReadTimeout and eventually succeed."""
    route = respx_mock.get(f"{HOST}{GET_CHECK_ROUTE.format(check_id='check_123')}")
    route.side_effect = [
        rml_init.ReadTimeout("timeout"),
        rml_init.ReadTimeout("timeout"),
        rml_init.ReadTimeout("timeout"),
        httpx.Response(200, json={"status": "success", "comments": []}),
    ]

    status, comments = rml_init.get_check_status("check_123")

    assert status == "success"
    assert comments == []
    assert route.call_count == 4


def test_get_check_status_raises_retry_error_after_max_attempts(respx_mock):
    """Should raise RetryError when all retry attempts fail."""
    route = respx_mock.get(f"{HOST}{GET_CHECK_ROUTE.format(check_id='check_123')}")
    route.side_effect = rml_init.ReadTimeout("persistent failure")

    with pytest.raises(RetryError):
        rml_init.get_check_status("check_123")


def test_post_check_retries_on_write_timeout_then_succeeds(respx_mock, tmp_path):
    """Should retry on WriteTimeout during file upload and eventually succeed."""
    archive_path = tmp_path / "test.tar.gz"
    archive_path.write_bytes(b"test data")

    route = respx_mock.post(f"{HOST}{POST_CHECK_ROUTE}")
    route.side_effect = [
        rml_init.WriteTimeout("timeout"),
        rml_init.WriteTimeout("timeout"),
        httpx.Response(200, json={"check_id": "ck_success"}),
    ]

    result = rml_init.post_check(
        archive_filename="test.tar.gz",
        archive_path=archive_path,
        target_filenames=["test.py"],
    )

    assert result["check_id"] == "ck_success"
    assert route.call_count == 3


def test_post_check_retries_on_read_timeout_then_succeeds(respx_mock, tmp_path):
    """Should retry on ReadTimeout when reading response and eventually succeed."""
    archive_path = tmp_path / "test.tar.gz"
    archive_path.write_bytes(b"test data")

    route = respx_mock.post(f"{HOST}{POST_CHECK_ROUTE}")
    route.side_effect = [
        rml_init.ReadTimeout("timeout"),
        rml_init.ReadTimeout("timeout"),
        httpx.Response(200, json={"check_id": "ck_success"}),
    ]

    result = rml_init.post_check(
        archive_filename="test.tar.gz",
        archive_path=archive_path,
        target_filenames=["test.py"],
    )

    assert result["check_id"] == "ck_success"
    assert route.call_count == 3


def test_post_check_raises_retry_error_after_max_attempts(respx_mock, tmp_path):
    """Should raise RetryError when all retry attempts fail."""
    archive_path = tmp_path / "test.tar.gz"
    archive_path.write_bytes(b"test data")

    route = respx_mock.post(f"{HOST}{POST_CHECK_ROUTE}")
    route.side_effect = rml_init.WriteTimeout("persistent failure")

    with pytest.raises(RetryError):
        rml_init.post_check(
            archive_filename="test.tar.gz",
            archive_path=archive_path,
            target_filenames=["test.py"],
        )

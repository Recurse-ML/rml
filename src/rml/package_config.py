import os
from pathlib import Path


def find_env_file():
    """Find .env.rml by searching up the directory tree."""
    start_path = Path(__file__).resolve().parent

    for path in [start_path, *start_path.parents]:
        env_file = path / ".env.rml"
        if env_file.exists():
            return env_file

    # If not found, default to current directory
    return start_path / ".env.rml"


_current_dir = Path(__file__).parent
PROJECT_ROOT = (_current_dir / "../../").resolve()
INSTALL_URL = "https://install.recurse.ml"

LOG_LEVEL = "DEBUG"
LOG_DIR = PROJECT_ROOT / "logs"
VERSION_CHECK_URL = (
    "https://github.com/Recurse-ML/rml/releases/latest/download/version.txt"
)

HOST = os.getenv("U_HOST", "https://squash-322339097191.europe-west3.run.app")
OAUTH_APP_CLIENT_ID = os.getenv("U_OAUTH_APP_CLIENT_ID", "Ov23liYqdgBWHJgs6HCd")
ENV_FILE_PATH = find_env_file()
RECURSE_API_KEY_NAME = "RECURSE_API_KEY"

SKIP_AUTH = False

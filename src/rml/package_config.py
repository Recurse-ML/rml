import os
from pathlib import Path

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
ENV_FILE_PATH = PROJECT_ROOT / ".env.rml"
GITHUB_ACCESS_TOKEN_KEYNAME = "GITHUB_ACCESS_TOKEN"
GITHUB_USER_ID_KEYNAME = "GITHUB_USER_ID"

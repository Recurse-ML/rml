import os
import sys
from pathlib import Path


def find_env_file():
    """Find the correct location for .env.rml based on deployment scenario."""
    # PyInstaller bundle -> Place .env.rml next to the executable
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        executable_dir = Path(sys.executable).parent
        return executable_dir / ".env.rml"
    else:
        # Running from source -> Place .env.rml in project root
        return PROJECT_ROOT / ".env.rml"


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

# API routes
POST_CHECK_ROUTE = "/api/check/"
GET_CHECK_ROUTE = "/api/check/{check_id}/"
HEALTH_ROUTE = "/health"

CONNECT_TIMEOUT = int(os.getenv("U_CONNECT_TIMEOUT", "30"))
READ_TIMEOUT = int(os.getenv("U_READ_TIMEOUT", "120"))
WRITE_TIMEOUT = int(os.getenv("U_WRITE_TIMEOUT", "300"))

SKIP_AUTH = False

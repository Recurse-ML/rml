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

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _config_dir = Path(sys.executable).parent  # ~/.rml/rml/.env.rml
else:
    _config_dir = PROJECT_ROOT

ENV_FILE_PATH = _config_dir / ".env.rml"
ENV_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

SKIP_AUTH = False

import os
from pathlib import Path

_current_dir = Path(__file__).parent
PROJECT_ROOT = (_current_dir / "../../").resolve()
INSTALL_SCRIPT_PATH = PROJECT_ROOT / "cli/install.sh"

LOG_LEVEL = "DEBUG"
LOG_DIR = PROJECT_ROOT / "logs"
VERSION_CHECK_URL = (
    "https://github.com/Recurse-ML/rml/releases/latest/download/version.txt"
)
XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", str(Path.home() / ".local/share"))
VERSION_FILE_PATH = Path(XDG_DATA_HOME) / "rml/version.txt"

if os.getenv("U_HOST") is not None:
    HOST = os.getenv("U_HOST")
else:
    HOST = "https://squash-322339097191.europe-west3.run.app"

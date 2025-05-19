import os
from pathlib import Path
from rich.logging import RichHandler

_current_dir = Path(__file__).parent
PROJECT_ROOT = (_current_dir / "../../").resolve()

LOG_LEVEL = "DEBUG"
LOG_DIR = PROJECT_ROOT / "logs"


if os.getenv("U_HOST") is not None:
    HOST = os.getenv("U_HOST")
else:
    HOST = "https://squash-322339097191.europe-west3.run.app"

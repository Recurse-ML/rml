import logging
import os
from rich.console import Console
from rich.logging import RichHandler

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(message)s"

console = Console()

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            console=console,
            show_time=False,
        )
    ],
)

logger = logging.getLogger("rml")

if os.getenv("U_HOST") is not None:
    HOST = os.getenv("U_HOST")
else:
    HOST = "https://squash-322339097191.europe-west3.run.app"


ENV = os.getenv("ENV", "staging")
assert ENV in [
    "testing",
    "prod",
    "staging",
], f"ENV variable must be set to 'prod' or 'staging', {ENV=}"

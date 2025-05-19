from datetime import datetime
import logging
from rml.package_config import LOG_DIR

LOG_LEVEL = "INFO"
logger = logging.getLogger("rml")
logger.setLevel(LOG_LEVEL)

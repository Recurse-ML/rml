import logging
import os

logger = logging.getLogger("rml")
logger.setLevel(os.getenv("RML_LOG_LEVEL", "DEBUG").upper())

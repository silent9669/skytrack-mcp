"""Structured logging for SkyTrack MCP server.
Never writes to stdout to prevent corrupting the MCP stdio wire protocol.
"""

from __future__ import annotations

import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

LOG_DIR = Path.home() / ".skytrack-mcp" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "skytrack_mcp.log"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            data.update(record.extra)
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data)


def setup_logger(name: str = "skytrack_mcp") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        # File handler (JSON)
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        logger.addHandler(fh)

        # Stderr handler for immediate CLI visibility (NEVER stdout!)
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
        )
        logger.addHandler(sh)
    return logger


logger = setup_logger()

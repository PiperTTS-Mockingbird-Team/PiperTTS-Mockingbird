from __future__ import annotations

import json
import os
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

# Cache for loggers to avoid re-initializing on every log_event call
_loggers: dict[Path, logging.Logger] = {}

@dataclass(frozen=True)
class LogConfig:
    root: Path
    filename: str = "events.jsonl"

    @property
    def path(self) -> Path:
        return self.root / self.filename


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_log_root() -> Path:
    # Workspace-relative. This file lives in src/, so go up one.
    return Path(__file__).resolve().parent.parent / "logs"


def log_event(
    event: str,
    *,
    fields: Optional[Mapping[str, Any]] = None,
    log_root: Optional[os.PathLike[str] | str] = None,
) -> Path:
    """Append a single JSONL log event with a 1MB rotation limit.

    Designed to be safe to call from small scripts.

    Returns the path written to.
    """

    root_path = Path(log_root) if log_root else _default_log_root()
    cfg = LogConfig(root=root_path)
    cfg.root.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "ts": _utc_now_iso(),
        "event": event,
    }
    if fields:
        # Copy to avoid mutating caller dict
        record.update(dict(fields))

    log_path = cfg.path
    
    # Use RotatingFileHandler to manage 1MB cap and 1 backup
    if log_path not in _loggers:
        # Create a dedicated logger for this file
        event_logger = logging.getLogger(f"central_log_{log_path}")
        event_logger.setLevel(logging.INFO)
        event_logger.propagate = False
        
        # maxBytes=1MB, backupCount=1
        handler = RotatingFileHandler(log_path, maxBytes=1024*1024, backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        event_logger.addHandler(handler)
        
        _loggers[log_path] = event_logger

    msg = json.dumps(record, ensure_ascii=False)
    _loggers[log_path].info(msg)

    return log_path

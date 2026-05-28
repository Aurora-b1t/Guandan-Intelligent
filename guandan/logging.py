"""Game-wide logging: console, rotating file, and in-memory ring buffer for UI.

Replaces the old ai/logger.py with multi-category coverage:
  - GAME   — round/trick lifecycle, play/pass events, scoring
  - AI     — candidate generation, scoring, final choice, simulation stats
  - WEB    — HTTP requests, API calls
  - SYSTEM — config changes, server lifecycle

Usage::

    from guandan.logging import game_logger, ai_log

    game_logger.game("round_start", level=2, round=1)
    ai_log(0, "decision_start")
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from logging.handlers import RotatingFileHandler
from threading import Lock
from typing import Any, Dict, List, Optional


# ── Enums & data ──────────────────────────────────────────────────


class LogCategory(Enum):
    GAME = "game"
    AI = "ai"
    WEB = "web"
    SYSTEM = "system"


@dataclass
class LogEntry:
    timestamp: float
    category: LogCategory
    level: str
    source: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "time": self.timestamp,
            "category": self.category.value,
            "level": self.level,
            "source": self.source,
            "message": self.message,
            "data": self.data,
            # Backward-compat: old frontend reads "type" and "player"
            "type": self.message,
            "player": self.data.get("player") if isinstance(self.data, dict) else None,
        }
        return result


# ── GameLogger singleton ──────────────────────────────────────────


class GameLogger:
    """Unified logger with three outputs: console, rotating file, memory ring."""

    _instance: GameLogger | None = None
    _lock: Lock = Lock()

    def __init__(self):
        self._entries: List[LogEntry] = []
        self._max_entries = 10000
        self._console_level = self._env_level()
        self._file_enabled = True
        self._console_enabled = True

        # Console handler
        self._console = logging.StreamHandler()
        self._console.setLevel(self._console_level)
        self._console.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
        ))

        # File handler with rotation
        os.makedirs("logs", exist_ok=True)
        self._file = RotatingFileHandler(
            "logs/guandan.log", maxBytes=5 * 1024 * 1024, backupCount=3,
            encoding="utf-8", delay=True,
        )
        self._file.setLevel(logging.DEBUG)
        self._file.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

        self._logger = logging.getLogger("guandan")
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self._console)
        self._logger.addHandler(self._file)

        # Suppress noisy libs
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @staticmethod
    def _env_level() -> int:
        name = os.environ.get("GUANDAN_LOG_LEVEL", "INFO").upper()
        return getattr(logging, name, logging.INFO)

    # ── Singleton ────────────────────────────────────────────────

    @classmethod
    def get(cls) -> GameLogger:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Core emit ─────────────────────────────────────────────────

    def _emit(self, category: LogCategory, log_level: int, source: str,
              message: str, **data):
        entry = LogEntry(
            timestamp=time.time(), category=category, level=logging.getLevelName(log_level),
            source=source, message=message, data=data,
        )
        # Memory buffer
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        # Python logging
        self._logger.log(log_level, "[%s][%s] %s  %s",
                         category.value.upper(), source, message,
                         _compact_data(data))

    # ── Public convenience ────────────────────────────────────────

    def game(self, event: str, source: str = "game", **data):
        self._emit(LogCategory.GAME, logging.INFO, source, event, **data)

    def game_debug(self, event: str, source: str = "game", **data):
        self._emit(LogCategory.GAME, logging.DEBUG, source, event, **data)

    def ai(self, player_id: int, event: str, source: str = "ai", **data):
        self._emit(LogCategory.AI, logging.DEBUG, source, event,
                   player=player_id, **data)

    def web(self, event: str, source: str = "web", **data):
        self._emit(LogCategory.WEB, logging.INFO, source, event, **data)

    def system(self, event: str, source: str = "system", **data):
        self._emit(LogCategory.SYSTEM, logging.INFO, source, event, **data)

    def warning(self, event: str, source: str = "system", **data):
        self._emit(LogCategory.SYSTEM, logging.WARNING, source, event, **data)

    # ── Query (for UI) ────────────────────────────────────────────

    def query(self, *, category: str | None = None,
              level: str | None = None,
              count: int = 200) -> List[dict]:
        entries = self._entries
        if category:
            entries = [e for e in entries if e.category.value == category]
        if level:
            entries = [e for e in entries if e.level == level.upper()]
        return [e.to_dict() for e in entries[-count:]]

    # ── Level control ─────────────────────────────────────────────

    def set_level(self, level: str):
        """Dynamically change console log level."""
        lvl = getattr(logging, level.upper(), logging.INFO)
        self._console_level = lvl
        self._console.setLevel(lvl)

    def get_level(self) -> str:
        return logging.getLevelName(self._console_level)

    # ── Maintenance ───────────────────────────────────────────────

    def clear(self):
        self._entries.clear()

    def entries(self) -> List[LogEntry]:
        return list(self._entries)


# ── Backward-compat convenience ───────────────────────────────────

# Singleton accessor (prefer this over direct construction)
game_logger = GameLogger.get()


def ai_log(player_id: int, event: str, **data):
    """Drop-in replacement for old ``ai/logger.ai_log``."""
    game_logger.ai(player_id, event, **data)


# ── Helpers ───────────────────────────────────────────────────────

def _compact_data(data: dict) -> str:
    if not data:
        return ""
    parts = []
    for k, v in data.items():
        if isinstance(v, float):
            parts.append(f"{k}={v:.2f}")
        else:
            parts.append(f"{k}={v}")
    return " | ".join(parts)

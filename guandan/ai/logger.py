"""AI reasoning logger — captures decision process for debugging."""

from __future__ import annotations

import time
from typing import Any, Dict, List


class AILogger:
    """Stores AI reasoning steps for later inspection.

    Thread-safe singleton. Agents write entries during choose_play();
    the web UI reads them via the API.
    """

    _instance: AILogger | None = None

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
        self._max_entries = 5000

    @classmethod
    def get(cls) -> AILogger:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def clear(self):
        self._entries.clear()

    def log(self, player_id: int, entry_type: str, data: Dict[str, Any]):
        entry = {
            "player": player_id,
            "type": entry_type,
            "data": data,
            "time": time.time(),
        }
        self._entries.append(entry)
        # Trim oldest if too many
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    def get_recent(self, count: int = 200) -> List[Dict[str, Any]]:
        return self._entries[-count:]

    def get_by_player(self, player_id: int, count: int = 100) -> List[Dict[str, Any]]:
        return [e for e in self._entries if e["player"] == player_id][-count:]

    def get_last_decision(self) -> List[Dict[str, Any]]:
        """Return the most recent decision cycle (from latest 'decision_start' to 'decision_end')."""
        result = []
        for e in reversed(self._entries):
            result.append(e)
            if e["type"] == "decision_start":
                break
        result.reverse()
        return result


# Convenience
def ai_log(player_id: int, entry_type: str, **data):
    AILogger.get().log(player_id, entry_type, data)

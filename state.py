import json
import os
import threading
from typing import Dict, Optional

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


class State:
    """Last seen price/stock per listing, persisted so restarts don't re-alert."""

    def __init__(self, path: str = STATE_FILE):
        self.path = path
        self.lock = threading.Lock()
        self.data: Dict[str, dict] = {}
        if os.path.exists(path):
            with open(path) as f:
                self.data = json.load(f)

    def get(self, key: str) -> Optional[dict]:
        with self.lock:
            return self.data.get(key)

    def set(self, key: str, value: dict) -> None:
        with self.lock:
            self.data[key] = value

    def save(self) -> None:
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)

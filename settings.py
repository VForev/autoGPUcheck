"""Settings that can be changed at runtime from Telegram.

.env provides the defaults. Changes made through Telegram are saved as overrides in
settings.json (next to state.json) so they survive restarts; /reset drops them.
"""
import json
import os
import threading
from typing import Any, Dict

import config
from state import STATE_FILE

SETTINGS_FILE = os.path.join(os.path.dirname(STATE_FILE), "settings.json")


class Settings:
    def __init__(self, cfg: config.Config, path: str = SETTINGS_FILE):
        self.path = path
        self.lock = threading.Lock()
        self.defaults: Dict[str, Any] = {
            "target_price": cfg.target_price,
            "interval:Best Buy": cfg.bestbuy_interval,
            "interval:Amazon": cfg.amazon_interval,
        }
        self.overrides: Dict[str, Any] = {}
        if os.path.exists(path):
            with open(path) as f:
                self.overrides = json.load(f)

    def get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            return self.overrides.get(key, self.defaults.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            self.overrides[key] = value
            self._save()

    def reset(self) -> None:
        with self.lock:
            self.overrides = {}
            self._save()

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.overrides, f, indent=2)
        os.replace(tmp, self.path)

    @property
    def target_price(self) -> float:
        return float(self.get("target_price"))

    def interval(self, store: str) -> float:
        return float(self.get("interval:" + store))

    def paused(self, store: str) -> bool:
        return bool(self.get("paused:" + store, False))

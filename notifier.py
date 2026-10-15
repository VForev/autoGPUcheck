import logging
import time
from typing import List

import requests

log = logging.getLogger(__name__)


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.api = "https://api.telegram.org/bot{}/".format(token)
        self.chat_id = chat_id

    def send(self, text: str) -> bool:
        for attempt in range(3):
            try:
                resp = requests.post(self.api + "sendMessage", json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }, timeout=15)
                if resp.status_code == 429:
                    wait = resp.json().get("parameters", {}).get("retry_after", 5)
                    time.sleep(wait)
                    continue
                if not resp.ok:
                    log.error("Telegram error %s: %s", resp.status_code, resp.text)
                    return False
                return True
            except requests.RequestException as e:
                log.warning("Telegram send failed (attempt %d): %s", attempt + 1, e)
                time.sleep(2)
        return False

    def get_updates(self, offset: int, timeout: int = 50) -> List[dict]:
        """Long-poll for new messages. Returns [] on timeout."""
        resp = requests.get(self.api + "getUpdates", params={
            "offset": offset, "timeout": timeout, "allowed_updates": '["message"]',
        }, timeout=timeout + 10)
        if resp.status_code == 409:
            raise RuntimeError("another copy of the watcher is reading this bot's messages")
        resp.raise_for_status()
        return resp.json().get("result", [])

    def set_commands(self, commands: List[tuple]) -> None:
        """Fill the '/' menu in the Telegram app."""
        try:
            requests.post(self.api + "setMyCommands", json={
                "commands": [{"command": c, "description": d} for c, d in commands],
            }, timeout=15)
        except requests.RequestException as e:
            log.warning("setMyCommands failed: %s", e)

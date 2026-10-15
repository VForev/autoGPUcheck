import logging
import time

import requests

log = logging.getLogger(__name__)


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.url = "https://api.telegram.org/bot{}/sendMessage".format(token)
        self.chat_id = chat_id

    def send(self, text: str) -> bool:
        for attempt in range(3):
            try:
                resp = requests.post(self.url, json={
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

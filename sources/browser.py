"""A curl_cffi session that looks like a real browser and can start over after a block.

Bot walls (Akamai on Best Buy, Amazon's CAPTCHA) usually key on the cookies and TLS fingerprint
of the session they flagged. reset() throws that session away and picks a different browser
profile; the next request first loads the homepage to collect fresh cookies, like a person would.
"""
import logging
import random
from typing import List, Optional

from curl_cffi import requests

log = logging.getLogger(__name__)

DEFAULT_PROFILES = ["chrome150", "chrome146", "chrome136", "safari260", "safari184", "safari180"]


def is_challenge(text: str) -> bool:
    """Akamai's "checking your browser" interstitial, served with a 200 instead of real content."""
    return "bm-verify" in text or "/_sec/verify" in text


class Browser:
    def __init__(self, home: str, profiles: Optional[List[str]] = None):
        self.home = home
        self.profiles = profiles or DEFAULT_PROFILES
        self.profile: Optional[str] = None
        self.session: Optional[requests.Session] = None
        self.reset()

    def reset(self) -> None:
        choices = [p for p in self.profiles if p != self.profile] or self.profiles
        self.profile = random.choice(choices)
        if self.session is not None:
            self.session.close()
        self.session = requests.Session(impersonate=self.profile)
        self.session.headers.update({"Accept-Language": "en-US,en;q=0.9"})
        self.warmed = False
        log.info("%s: new browser session (%s)", self.home, self.profile)

    def get(self, url: str, **kwargs) -> requests.Response:
        if not self.warmed:
            try:
                self.session.get(self.home, timeout=20)
            except Exception as e:
                log.debug("warm-up failed: %s", e)
            self.warmed = True
        kwargs.setdefault("timeout", 20)
        return self.session.get(url, **kwargs)

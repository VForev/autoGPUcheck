import os
import sys
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


@dataclass
class Config:
    telegram_token: str
    telegram_chat_id: str
    target_price: float
    bestbuy_interval: float
    amazon_interval: float
    amazon_asins: List[str]
    bestbuy_skus: List[str]


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit("Missing {} in .env (see .env.example and README.md)".format(name))
    return value


def _list(name: str) -> List[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def load(require_telegram: bool = True) -> Config:
    return Config(
        telegram_token=_require("TELEGRAM_BOT_TOKEN") if require_telegram else os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID") if require_telegram else os.getenv("TELEGRAM_CHAT_ID", ""),
        target_price=float(os.getenv("TARGET_PRICE", "2000")),
        bestbuy_interval=float(os.getenv("BESTBUY_INTERVAL", "15")),
        amazon_interval=float(os.getenv("AMAZON_INTERVAL", "90")),
        amazon_asins=_list("AMAZON_ASINS"),
        bestbuy_skus=_list("BESTBUY_SKUS"),
    )

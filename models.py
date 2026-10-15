from dataclasses import dataclass
from typing import Optional


@dataclass
class Listing:
    store: str
    id: str
    title: str
    price: Optional[float]
    in_stock: bool
    url: str

    @property
    def key(self) -> str:
        return "{}:{}".format(self.store, self.id)


class Blocked(Exception):
    """The store served a CAPTCHA / bot wall instead of real data."""

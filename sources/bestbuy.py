"""Best Buy without an API key.

Two steps, both against bestbuy.com's own endpoints:
  1. Discovery (every DISCOVERY_INTERVAL): page through the GPU-category search for "rtx 5090"
     to collect SKU ids. Search results are noisy (5080s, 5070s...), so names are filtered later.
  2. Polling (every call): one request to /api/3.0/priceBlocks for all known 5090 SKUs, which
     returns name, current price and the add-to-cart button state.
"""
import re
import time
from typing import List

from curl_cffi import requests

from models import Blocked, Listing
from sources.browser import Browser, is_challenge

SEARCH_URL = ("https://www.bestbuy.com/site/searchpage.jsp?st=rtx+5090&cp={page}"
              "&qp=category_facet%3DGPUs+%2F+Video+Graphics+Cards~abcat0507002")
PRICE_URL = "https://www.bestbuy.com/api/3.0/priceBlocks?skus={}"
PRODUCT_URL = "https://www.bestbuy.com/site/{}.p?skuId={}"
DISCOVERY_INTERVAL = 600
MAX_PAGES = 6
CHUNK = 40
IN_STOCK_STATES = {"ADD_TO_CART", "PRE_ORDER"}

_browser = Browser("https://www.bestbuy.com/")


class _Discovery:
    skus: List[str] = []
    last: float = 0.0


def _blocked(reason: str) -> Blocked:
    _browser.reset()
    return Blocked(reason)


def _get(url: str) -> requests.Response:
    resp = _browser.get(url)
    if resp.status_code in (403, 429):
        raise _blocked("HTTP {}".format(resp.status_code))
    resp.raise_for_status()
    if is_challenge(resp.text):
        raise _blocked("bot check page")
    return resp


def _price_blocks(skus: List[str]) -> List[dict]:
    blocks = []
    for i in range(0, len(skus), CHUNK):
        resp = _get(PRICE_URL.format(",".join(skus[i:i + CHUNK])))
        if "json" not in resp.headers.get("content-type", ""):
            raise _blocked("priceBlocks returned non-JSON")
        # Marketplace SKUs come back as {"error": ...} entries with no "sku" key; skip them.
        blocks += [b["sku"] for b in resp.json() if "sku" in b]
    return blocks


def _name(block: dict) -> str:
    return (block.get("names") or {}).get("short", "")


def _discover(extra_skus: List[str]) -> List[str]:
    found: List[str] = []
    for page in range(1, MAX_PAGES + 1):
        ids = re.findall(r'data-product-id="(\d+)"', _get(SEARCH_URL.format(page=page)).text)
        new = [s for s in dict.fromkeys(ids) if s not in found]
        if not new:
            break
        found += new
    if not found and not extra_skus:
        raise _blocked("search page had no products (likely a bot wall)")
    candidates = list(dict.fromkeys(found + extra_skus))
    keep = [b["buttonState"]["skuId"] for b in _price_blocks(candidates)
            if "5090" in _name(b) and b.get("buttonState", {}).get("skuId")]
    return list(dict.fromkeys(keep + extra_skus))


def fetch(extra_skus: List[str]) -> List[Listing]:
    if not _Discovery.skus or time.time() - _Discovery.last > DISCOVERY_INTERVAL:
        _Discovery.skus = _discover(extra_skus)
        _Discovery.last = time.time()

    listings = []
    for b in _price_blocks(_Discovery.skus):
        button = b.get("buttonState") or {}
        sku = button.get("skuId")
        if not sku:
            continue
        listings.append(Listing(
            store="Best Buy",
            id=sku,
            title=_name(b) or sku,
            price=(b.get("price") or {}).get("currentPrice"),
            in_stock=button.get("buttonState") in IN_STOCK_STATES,
            url=PRODUCT_URL.format(sku, sku),
        ))
    return listings

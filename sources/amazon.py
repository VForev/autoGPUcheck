import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from models import Blocked, Listing
from sources.browser import Browser, is_challenge

BASE = "https://www.amazon.com"
SEARCH_URL = BASE + "/s?k=rtx+5090+graphics+card"
# Titles with these words are laptops, prebuilt PCs or accessories, not the card itself.
EXCLUDE = re.compile(
    r"\b(laptop|notebook|desktop|gaming pc|computer|tower|prebuilt|water block|waterblock|bracket|cable|backplate)\b",
    re.I,
)

# Tested Oct 2026: Amazon answers Chrome/Firefox fingerprints from curl with a bot check, Safari ones normally.
_browser = Browser(BASE + "/", profiles=["safari260", "safari184", "safari180"])


def _parse_price(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", text)
    return float(m.group().replace(",", "")) if m else None


def _blocked(reason: str) -> Blocked:
    _browser.reset()
    return Blocked(reason)


def _get(url: str) -> BeautifulSoup:
    resp = _browser.get(url)
    if resp.status_code in (503, 429) or "validateCaptcha" in resp.url:
        raise _blocked("HTTP {}".format(resp.status_code))
    resp.raise_for_status()
    if "Enter the characters you see below" in resp.text or "/errors/validateCaptcha" in resp.text:
        raise _blocked("CAPTCHA page")
    if is_challenge(resp.text):
        raise _blocked("bot check page")
    return BeautifulSoup(resp.text, "html.parser")


def _search() -> List[Listing]:
    soup = _get(SEARCH_URL)
    results = soup.select('div[data-component-type="s-search-result"]')
    if not results:
        raise _blocked("search page had no results (likely a bot wall)")
    listings = []
    for r in results:
        asin = r.get("data-asin")
        title_el = r.select_one("h2")
        if not asin or not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        if "5090" not in title or EXCLUDE.search(title):
            continue
        price_el = r.select_one(".a-price .a-offscreen")
        price = _parse_price(price_el.get_text() if price_el else None)
        listings.append(Listing(
            store="Amazon",
            id=asin,
            title=title,
            price=price,
            in_stock=price is not None,  # search results show no price for unavailable items
            url="{}/dp/{}".format(BASE, asin),
        ))
    return listings


def _product(asin: str) -> Listing:
    soup = _get("{}/dp/{}".format(BASE, asin))
    title_el = soup.select_one("#productTitle")
    price_el = (soup.select_one("#corePrice_feature_div .a-offscreen")
                or soup.select_one("#corePriceDisplay_desktop_feature_div .a-offscreen"))
    avail_el = soup.select_one("#availability")
    avail = avail_el.get_text(" ", strip=True).lower() if avail_el else ""
    price = _parse_price(price_el.get_text() if price_el else None)
    unavailable = "currently unavailable" in avail or "out of stock" in avail
    return Listing(
        store="Amazon",
        id=asin,
        title=title_el.get_text(" ", strip=True) if title_el else asin,
        price=price,
        in_stock=price is not None and not unavailable,
        url="{}/dp/{}".format(BASE, asin),
    )


def fetch(asins: List[str]) -> List[Listing]:
    by_id: Dict[str, Listing] = {l.id: l for l in _search()}
    for asin in asins:
        by_id[asin] = _product(asin)  # product page is more accurate than the search card
    return list(by_id.values())

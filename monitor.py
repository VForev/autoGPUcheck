"""Watch RTX 5090 prices on Best Buy and Amazon and alert via Telegram."""
import argparse
import html
import logging
import random
import threading
import time
from typing import Callable, List, Optional

import config
from models import Blocked, Listing
from notifier import Telegram
from sources import amazon, bestbuy
from state import State

FAILURE_ALERT_THRESHOLD = 5
MIN_BLOCK_BACKOFF = 120  # a block rarely clears in less than a couple of minutes
MAX_BACKOFF = 1800

log = logging.getLogger("monitor")


def fmt_price(price: Optional[float]) -> str:
    return "${:,.2f}".format(price) if price is not None else "n/a"


class Watcher(threading.Thread):
    def __init__(self, name: str, fetch: Callable[[], List[Listing]], interval: float, jitter: float,
                 state: State, tg: Telegram, target: float):
        super().__init__(name=name, daemon=True)
        self.fetch = fetch
        self.interval = interval
        self.jitter = jitter  # fraction of interval, e.g. 0.33 -> ±33%
        self.state = state
        self.tg = tg
        self.target = target
        self.failures = 0
        self.backoff = interval
        self.first_cycle = True

    def run(self) -> None:
        while True:
            delay = self.interval
            try:
                listings = self.fetch()
                self.check(listings)
                log.info("%s: %d listings, %d in stock", self.name, len(listings),
                         sum(l.in_stock for l in listings))
                if self.failures >= FAILURE_ALERT_THRESHOLD:
                    self.tg.send("✅ {} is working again.".format(self.name))
                self.failures = 0
                # After a block, ease back to the normal pace instead of jumping straight to it.
                self.backoff = max(self.interval, self.backoff / 2)
                delay = self.backoff
            except Blocked as e:
                self.failures += 1
                self.backoff = min(max(self.backoff * 2, MIN_BLOCK_BACKOFF), MAX_BACKOFF)
                delay = self.backoff
                log.warning("%s blocked (%s), backing off %.0fs", self.name, e, delay)
                self.on_failure("blocked ({}), backing off {:.0f}s".format(e, delay))
            except Exception as e:
                self.failures += 1
                log.warning("%s error: %s", self.name, e)
                self.on_failure(str(e))
            time.sleep(max(1.0, delay * random.uniform(1 - self.jitter, 1 + self.jitter)))

    def on_failure(self, reason: str) -> None:
        if self.failures == FAILURE_ALERT_THRESHOLD:
            self.tg.send("⚠️ {} failed {} times in a row: {}".format(
                self.name, self.failures, html.escape(reason)))

    def check(self, listings: List[Listing]) -> None:
        for l in listings:
            prev = self.state.get(l.key)
            prev_price = prev.get("price") if prev else None
            reasons = []

            under = l.in_stock and l.price is not None and l.price <= self.target
            target_alerted = prev.get("target_alerted") if prev else None
            if under and target_alerted != l.price:
                reasons.append("🎯 At or below target ({})".format(fmt_price(self.target)))
                target_alerted = l.price
            elif not under:
                target_alerted = None

            if prev is None:
                if not self.first_cycle and l.in_stock:
                    reasons.append("🆕 New listing")
            else:
                if l.in_stock and not prev.get("in_stock"):
                    reasons.append("📦 Back in stock")
                if l.in_stock and l.price is not None and prev_price is not None and l.price < prev_price:
                    reasons.append("📉 Price drop")

            if reasons:
                self.alert(l, reasons, prev_price)

            self.state.set(l.key, {
                "title": l.title,
                "price": l.price if l.price is not None else prev_price,
                "in_stock": l.in_stock,
                "target_alerted": target_alerted,
                "url": l.url,
            })
        self.state.save()
        self.first_cycle = False

    def alert(self, l: Listing, reasons: List[str], prev_price: Optional[float]) -> None:
        price_line = fmt_price(l.price)
        if prev_price is not None and l.price is not None and prev_price != l.price:
            price_line = "{} → <b>{}</b>".format(fmt_price(prev_price), fmt_price(l.price))
        else:
            price_line = "<b>{}</b>".format(price_line)
        text = "{}\n<b>{}</b>: {}\n{}\n{}\n{}".format(
            "\n".join(reasons),
            l.store,
            html.escape(l.title),
            price_line,
            "In stock ✅" if l.in_stock else "Out of stock ❌",
            l.url,
        )
        log.info("ALERT %s %s %s", l.store, l.price, reasons)
        self.tg.send(text)


def build_sources(cfg: config.Config):
    return [
        ("Best Buy", lambda: bestbuy.fetch(cfg.bestbuy_skus), cfg.bestbuy_interval, 0.2),
        ("Amazon", lambda: amazon.fetch(cfg.amazon_asins), cfg.amazon_interval, 0.33),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="fetch each store once, print listings, no alerts")
    parser.add_argument("--test-alert", action="store_true", help="send a test Telegram message and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = config.load(require_telegram=not args.once)
    tg = Telegram(cfg.telegram_token, cfg.telegram_chat_id)

    if args.test_alert:
        ok = tg.send("🔔 Test alert from the RTX 5090 watcher. Target: {}".format(fmt_price(cfg.target_price)))
        print("Sent!" if ok else "Failed, check token/chat ID.")
        return

    sources = build_sources(cfg)

    if args.once:
        for name, fetch, _, _ in sources:
            try:
                listings = fetch()
            except Exception as e:
                print("{}: FAILED ({})".format(name, e))
                continue
            print("\n{} ({} listings)".format(name, len(listings)))
            for l in sorted(listings, key=lambda x: x.price or 1e9):
                print("  {:>11}  {:<5}  {}".format(fmt_price(l.price), "IN" if l.in_stock else "out", l.title[:90]))
                print("               {}".format(l.url))
        return

    state = State()
    tg.send("👀 RTX 5090 watcher started: {}. Target {}.".format(
        ", ".join("{} every {:.0f}s".format(n, i) for n, _, i, _ in sources), fmt_price(cfg.target_price)))
    for name, fetch, interval, jitter in sources:
        Watcher(name, fetch, interval, jitter, state, tg, cfg.target_price).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()

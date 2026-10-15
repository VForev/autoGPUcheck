"""Telegram commands for controlling the watcher. Only messages from TELEGRAM_CHAT_ID are obeyed."""
import html
import logging
import threading
import time
from typing import Dict, List, Optional

from notifier import Telegram
from settings import Settings

log = logging.getLogger("bot")

# Lowest interval each store accepts from Telegram, and the pace that's safe all day.
MIN_INTERVAL = {"Best Buy": 5, "Amazon": 30}
SAFE_INTERVAL = {"Best Buy": 15, "Amazon": 90}
STORE_ALIASES = {"bestbuy": "Best Buy", "bb": "Best Buy", "best": "Best Buy",
                 "amazon": "Amazon", "amz": "Amazon"}
LIST_LIMIT = 10

COMMANDS = [
    ("status", "What the watcher is doing"),
    ("list", "Current 5090 prices and stock"),
    ("price", "Set target price, e.g. /price 3500"),
    ("interval", "Check speed, e.g. /interval amazon 120"),
    ("pause", "Pause all, or /pause amazon"),
    ("resume", "Resume all, or /resume amazon"),
    ("check", "Check both stores right now"),
    ("reset", "Go back to the .env settings"),
    ("help", "Show commands"),
]


def _ago(ts: Optional[float]) -> str:
    if ts is None:
        return "never"
    s = int(time.time() - ts)
    return "{}s ago".format(s) if s < 120 else "{}m ago".format(s // 60)


def _money(price: Optional[float]) -> str:
    return "${:,.2f}".format(price) if price is not None else "n/a"


class Bot(threading.Thread):
    def __init__(self, tg: Telegram, settings: Settings, watchers: Dict[str, "object"]):
        super().__init__(name="telegram-bot", daemon=True)
        self.tg = tg
        self.settings = settings
        self.watchers = watchers

    def run(self) -> None:
        self.tg.set_commands(COMMANDS)
        offset = self._skip_old_messages()
        while True:
            try:
                for update in self.tg.get_updates(offset):
                    offset = update["update_id"] + 1
                    self._on_message(update.get("message") or {})
            except Exception as e:
                log.warning("Telegram command polling failed: %s", e)
                time.sleep(10)

    def _skip_old_messages(self) -> int:
        """Don't replay commands sent while the watcher was off."""
        while True:
            try:
                updates = self.tg.get_updates(-1, timeout=0)
                return updates[-1]["update_id"] + 1 if updates else 0
            except Exception as e:
                log.warning("Telegram getUpdates failed: %s", e)
                time.sleep(10)

    def _on_message(self, msg: dict) -> None:
        text = (msg.get("text") or "").strip()
        if str(msg.get("chat", {}).get("id")) != str(self.tg.chat_id):
            log.warning("Ignoring message from unknown chat %s", msg.get("chat", {}).get("id"))
            return
        if not text.startswith("/"):
            self.tg.send("Send /help to see what I can do.")
            return
        parts = text.split()
        cmd = parts[0][1:].split("@")[0].lower()
        args = parts[1:]
        handler = getattr(self, "cmd_" + cmd, None)
        log.info("Command: %s", text)
        if handler is None:
            self.tg.send("Unknown command. Send /help.")
            return
        try:
            self.tg.send(handler(args))
        except ValueError as e:
            self.tg.send("⚠️ {}".format(html.escape(str(e))))

    def _stores(self, args: List[str]) -> List[str]:
        """No argument means every store."""
        if not args:
            return list(self.watchers)
        store = STORE_ALIASES.get("".join(args).lower())
        if store is None:
            raise ValueError("Unknown store '{}'. Use bestbuy or amazon.".format(" ".join(args)))
        return [store]

    # --- commands -----------------------------------------------------------------------------

    def cmd_start(self, args: List[str]) -> str:
        return self.cmd_help(args)

    def cmd_help(self, args: List[str]) -> str:
        return "\n".join(["<b>Commands</b>"] + ["/{} - {}".format(c, d) for c, d in COMMANDS])

    def cmd_status(self, args: List[str]) -> str:
        lines = ["🎯 Target: <b>{}</b>".format(_money(self.settings.target_price))]
        for name, w in self.watchers.items():
            if self.settings.paused(name):
                state = "⏸ paused"
            elif w.failures:
                state = "⚠️ {} failures in a row, next try in ~{:.0f}s".format(w.failures, w.backoff)
            else:
                state = "✅ running"
            in_stock = sum(l.in_stock for l in w.last_listings)
            lines.append("\n<b>{}</b>: {}\nEvery {:.0f}s · last success {} · {} listings, {} in stock".format(
                name, state, self.settings.interval(name), _ago(w.last_ok), len(w.last_listings), in_stock))
        if self.settings.overrides:
            lines.append("\n(Some settings were changed from Telegram. /reset goes back to .env.)")
        return "\n".join(lines)

    def cmd_list(self, args: List[str]) -> str:
        lines = []
        for name in self._stores(args):
            listings = sorted(self.watchers[name].last_listings,
                              key=lambda l: (not l.in_stock, l.price if l.price is not None else 1e9))
            lines.append("<b>{}</b> ({} listings)".format(name, len(listings)))
            for l in listings[:LIST_LIMIT]:
                lines.append('{} {} <a href="{}">{}</a>'.format(
                    "✅" if l.in_stock else "❌", _money(l.price), l.url, html.escape(l.title[:60])))
            if len(listings) > LIST_LIMIT:
                lines.append("…and {} more".format(len(listings) - LIST_LIMIT))
            if not listings:
                lines.append("Nothing yet. It may still be on its first check.")
            lines.append("")
        return "\n".join(lines).strip()

    def cmd_price(self, args: List[str]) -> str:
        if not args:
            return "Target is {}. Change it with e.g. /price 3500".format(_money(self.settings.target_price))
        try:
            price = float(args[0].replace("$", "").replace(",", ""))
        except ValueError:
            raise ValueError("'{}' isn't a price. Example: /price 3500".format(args[0]))
        if price <= 0:
            raise ValueError("Price must be above $0.")
        self.settings.set("target_price", price)
        self._wake_all()
        return "🎯 Target set to <b>{}</b>. Checking now.".format(_money(price))

    def cmd_interval(self, args: List[str]) -> str:
        if len(args) < 2:
            return "Usage: /interval bestbuy 30  or  /interval amazon 120\nNow: {}".format(", ".join(
                "{} {:.0f}s".format(n, self.settings.interval(n)) for n in self.watchers))
        store = self._stores(args[:-1])[0]
        try:
            seconds = float(args[-1].rstrip("s"))
        except ValueError:
            raise ValueError("'{}' isn't a number of seconds.".format(args[-1]))
        if seconds < MIN_INTERVAL[store]:
            raise ValueError("{} can't go below {}s. That gets you blocked fast.".format(store, MIN_INTERVAL[store]))
        self.settings.set("interval:" + store, seconds)
        self.watchers[store].wake.set()
        reply = "⏱ {} now checks every <b>{:.0f}s</b>.".format(store, seconds)
        if seconds < SAFE_INTERVAL[store]:
            reply += "\nHeads up: below {}s, blocks get more likely.".format(SAFE_INTERVAL[store])
        return reply

    def cmd_pause(self, args: List[str]) -> str:
        stores = self._stores(args)
        for s in stores:
            self.settings.set("paused:" + s, True)
        return "⏸ Paused {}. /resume to start again.".format(" and ".join(stores))

    def cmd_resume(self, args: List[str]) -> str:
        stores = self._stores(args)
        for s in stores:
            self.settings.set("paused:" + s, False)
            self.watchers[s].wake.set()
        return "▶️ Resumed {}.".format(" and ".join(stores))

    def cmd_check(self, args: List[str]) -> str:
        requested = self._stores(args)
        stores = [s for s in requested if not self.settings.paused(s)]
        if not stores:
            return "{} paused. /resume first.".format("Everything is" if len(requested) > 1 else requested[0] + " is")
        for s in stores:
            self.watchers[s].wake.set()
        return "🔎 Checking {} now. You'll get alerts if anything changed; /list shows prices.".format(
            " and ".join(stores))

    def cmd_reset(self, args: List[str]) -> str:
        self.settings.reset()
        self._wake_all()
        return "↩️ Back to the .env settings (and unpaused).\n\n" + self.cmd_status([])

    def _wake_all(self) -> None:
        for w in self.watchers.values():
            w.wake.set()

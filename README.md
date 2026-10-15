# RTX 5090 Watcher

Checks Best Buy (every 15s by default) and Amazon (about every 90s) for RTX 5090 cards and sends a Telegram message when:

- 🎯 an in-stock card is at or below `TARGET_PRICE`
- 📦 a listing comes back in stock
- 📉 a listing's price drops
- 🆕 a new 5090 listing appears

## Setup

1. **Install** (needs Python 3.9 or newer):
   ```sh
   git clone https://github.com/VForev/autoGPUcheck.git ~/autoGPUcheck
   cd ~/autoGPUcheck
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   cp .env.example .env
   ```
   On Debian/Ubuntu, if `python3 -m venv` fails, first run `sudo apt install python3-venv`.

2. **Telegram bot**
   - In Telegram, message **@BotFather**, send `/newbot`, and follow the prompts. Copy the token into `TELEGRAM_BOT_TOKEN` in `.env`.
   - Open your new bot and send it any message (e.g. "hi").
   - Run `.venv/bin/python get_chat_id.py` and copy the printed `TELEGRAM_CHAT_ID=...` into `.env`.
   - Test it: `.venv/bin/python monitor.py --test-alert`

3. Set `TARGET_PRICE` in `.env`.

## Run

**Docker (recommended for a server):** needs Docker with the Compose plugin. Only `.env` is required on the host, so you can skip the venv and pip lines in Setup step 1.
```sh
git clone https://github.com/VForev/autoGPUcheck.git ~/autoGPUcheck
cd ~/autoGPUcheck
cp .env.example .env && nano .env              # fill in Telegram token, chat ID, target price
docker compose run --rm autogpucheck python monitor.py --once         # test fetching
docker compose run --rm autogpucheck python get_chat_id.py            # find your chat ID if needed
docker compose run --rm autogpucheck python monitor.py --test-alert   # test Telegram
docker compose up -d --build                    # start in the background
docker compose logs -f                          # watch the logs
```
It restarts on crash and after a reboot (`restart: unless-stopped`). Price history is kept in the `state` Docker volume, so rebuilding doesn't trigger a flood of alerts.

- After editing `.env`: `docker compose up -d` (Compose recreates the container with the new settings)
- Update to the latest code: `git pull && docker compose up -d --build`
- Stop: `docker compose down`

**Linux without Docker (systemd user service):**
```sh
mkdir -p ~/.config/systemd/user
cp autogpucheck.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now autogpucheck
sudo loginctl enable-linger "$USER"     # keep it running when you're logged out
journalctl --user -u autogpucheck -f    # watch the logs
```
The service file expects the project at `~/autoGPUcheck`. Use `systemctl --user restart autogpucheck` after editing `.env`, and `systemctl --user stop autogpucheck` to stop it.

**Mac / quick test in a terminal:**
```sh
caffeinate -i .venv/bin/python monitor.py      # caffeinate keeps the Mac awake
```

- `--once`: fetch each store once and print the listings (no alerts, no Telegram needed)
- `--test-alert`: send a test Telegram message

The first run records current prices as a baseline and only alerts on listings already under your target. State is kept in `state.json`; delete it to start fresh.

## Notes

- **Intervals:** `BESTBUY_INTERVAL=15` and `AMAZON_INTERVAL=90` are safe for running all day. Going lower makes blocks more likely, especially on Amazon.
- **When a store blocks you** (CAPTCHA, a "checking your browser" page, or a 403/429/503):
  1. The watcher throws away its session and cookies and switches to a different browser profile.
  2. It waits 2 minutes, then doubles the wait after each further block, up to 30 min.
  3. Once a check succeeds, it halves the wait each time until it's back to your normal interval.
  4. After 5 failures in a row you get a Telegram warning, and another message when the store is working again.
- **If blocks don't clear after a few hours,** your IP address has probably been flagged. Raise the interval, wait it out (usually less than a day), or restart your router to get a new IP from your ISP. Watching from a VPN or cloud server makes blocks more likely.
- Amazon search results include third-party sellers, so prices can be far above MSRP. To watch a specific listing's product page, add its ASIN (the `B0...` code in the URL) to `AMAZON_ASINS`.
- **Best Buy** needs no API key. Every 10 minutes the watcher searches bestbuy.com to find 5090 SKUs, then checks their price and stock every `BESTBUY_INTERVAL` seconds through the price endpoint the site itself uses. A card counts as in stock when its button says Add to Cart or Pre-Order. To always watch a SKU, add it to `BESTBUY_SKUS`. Best Buy marketplace (third-party) listings aren't covered.

#!/usr/bin/env python3
"""Fetch tweets from watched accounts in the past 24 hours."""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
import urllib.error

HKT = timezone(timedelta(hours=8))

MAX_RETRIES = 3
RETRY_DELAY = 3    # seconds between retries
PAGE_DELAY  = 0.5  # seconds between paginated requests
ACCOUNT_DELAY = 1  # seconds between accounts

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR   = SCRIPT_DIR.parent
CONFIG_FILE = ROOT_DIR / "config" / "twitter_watchlist.json"
REPORTS_DIR = ROOT_DIR / "reports"
ENV_FILE    = Path.home() / ".openclaw" / ".env"

API_BASE = "https://api.twitterapi.io/twitter/user/last_tweets"

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_api_key() -> str:
    if not ENV_FILE.exists():
        sys.exit(f"ERROR: {ENV_FILE} not found")
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TWITTERAPI_IO_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: TWITTERAPI_IO_KEY not found in ~/.openclaw/.env")


def load_accounts() -> list[dict]:
    with open(CONFIG_FILE) as f:
        return json.load(f)


def fetch_user_tweets(username: str, api_key: str, since: datetime) -> list[dict]:
    """Fetch all tweets for a user since the given datetime (UTC)."""
    tweets = []
    cursor = ""
    headers = {"x-api-key": api_key, "User-Agent": "Mozilla/5.0"}

    while True:
        url = f"{API_BASE}?userName={username}&includeReplies=false"
        if cursor:
            url += f"&cursor={cursor}"

        req = urllib.request.Request(url, headers=headers)
        data = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as e:
                if attempt == MAX_RETRIES:
                    print(f"  [!] HTTP {e.code} for @{username}: gave up after {MAX_RETRIES} attempts")
                    break
                if e.code == 429:
                    wait = int(e.headers.get("Retry-After", 2 ** attempt))
                    print(f"  [!] Rate limited, waiting {wait}s (attempt {attempt}/{MAX_RETRIES}) ...")
                else:
                    wait = RETRY_DELAY
                    print(f"  [!] HTTP {e.code} for @{username} (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s ...")
                time.sleep(wait)
            except Exception as e:
                if attempt == MAX_RETRIES:
                    print(f"  [!] Request failed for @{username}: gave up after {MAX_RETRIES} attempts ({e})")
                    break
                wait = RETRY_DELAY
                print(f"  [!] Request failed for @{username} (attempt {attempt}/{MAX_RETRIES}): {e}, retrying in {wait}s ...")
                time.sleep(wait)
        if data is None:
            break

        if data.get("status") != "success":
            print(f"  [!] API error for @{username}: {data.get('msg', 'unknown')}")
            break

        payload = data.get("data", {})
        page_tweets = payload.get("tweets", [])
        if not page_tweets:
            break

        oldest_in_page = None
        for t in page_tweets:
            created = parse_date(t.get("createdAt", ""))
            if created is None:
                continue
            if created >= since:
                tweets.append(t)
                if oldest_in_page is None or created < oldest_in_page:
                    oldest_in_page = created
            # else: tweet is older than our window, but keep paginating this page

        # Stop paginating if the oldest tweet on this page is before our window
        # (tweets are sorted newest-first)
        page_oldest = None
        for t in page_tweets:
            created = parse_date(t.get("createdAt", ""))
            if created and (page_oldest is None or created < page_oldest):
                page_oldest = created

        if page_oldest and page_oldest < since:
            break  # no need to fetch more pages

        if not payload.get("has_next_page"):
            break

        cursor = payload.get("next_cursor", "")
        if not cursor:
            break

        time.sleep(PAGE_DELAY)

    return tweets


def parse_date(s: str) -> datetime | None:
    """Parse Twitter date string to UTC datetime."""
    if not s:
        return None
    # Twitter format: "Mon Mar 11 12:34:56 +0000 2026"
    try:
        dt = datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    # ISO 8601: "2026-03-11T12:34:56.000Z"
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    return None


def get_media_urls(tweet: dict) -> list[str]:
    """Extract image/video URLs from extendedEntities."""
    media_items = tweet.get("extendedEntities", {}).get("media", [])
    urls = []
    for m in media_items:
        media_url = m.get("media_url_https", "")
        if media_url:
            urls.append(media_url)
    return urls


def format_tweet_terminal(tweet: dict) -> str:
    text = tweet.get("text", "")
    created = parse_date(tweet.get("createdAt", ""))
    time_str = created.astimezone(HKT).strftime("%m-%d %H:%M HKT") if created else "unknown time"
    url = tweet.get("url", "")
    likes = tweet.get("likeCount", 0)
    retweets = tweet.get("retweetCount", 0)
    media_urls = get_media_urls(tweet)

    # Indent continuation lines to align with text
    indented_text = text.replace("\n", "\n         ")
    lines = [f"  [{time_str}] {indented_text}"]
    for mu in media_urls:
        lines.append(f"  [图片] {mu}")
    lines.append(f"  ↗ {url}  ❤ {likes}  🔁 {retweets}")
    return "\n".join(lines)


def format_tweet_markdown(tweet: dict) -> str:
    text = tweet.get("text", "")
    created = parse_date(tweet.get("createdAt", ""))
    time_str = created.astimezone(HKT).strftime("%Y-%m-%d %H:%M HKT") if created else "unknown time"
    url = tweet.get("url", "")
    likes = tweet.get("likeCount", 0)
    retweets = tweet.get("retweetCount", 0)
    media_urls = get_media_urls(tweet)

    text_escaped = text.replace("|", "\\|").replace("\n", "  \n")
    lines = [f"**[{time_str}]** {text_escaped}"]
    for mu in media_urls:
        lines.append(f"![]({mu})")
    lines.append(f"[Link]({url}) · ❤ {likes} · 🔁 {retweets}")
    return "  \n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    api_key = load_api_key()
    accounts = load_accounts()
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    print(f"Fetching tweets since {since.astimezone(HKT).strftime('%Y-%m-%d %H:%M HKT')}")
    print(f"Watching {len(accounts)} account(s)\n")

    results: list[tuple[dict, list[dict]]] = []

    for i, acc in enumerate(accounts):
        handle = acc["handle"]
        alias  = acc.get("alias", handle)
        print(f"→ @{handle} ({alias}) ...")
        tweets = fetch_user_tweets(handle, api_key, since)
        print(f"  {len(tweets)} tweet(s) in the last 24h")
        if tweets:
            for t in tweets:
                print(format_tweet_terminal(t))
        results.append((acc, tweets))
        print()
        if i < len(accounts) - 1:
            time.sleep(ACCOUNT_DELAY)

    # ── Markdown report ───────────────────────────────────────────────────────
    REPORTS_DIR.mkdir(exist_ok=True)
    report_name = f"report_{now.strftime('%Y-%m-%d_%H-%M')}.md"
    report_path = REPORTS_DIR / report_name

    total = sum(len(tweets) for _, tweets in results)
    lines = [
        f"# Twitter Watch Report",
        f"",
        f"**Generated:** {now.astimezone(HKT).strftime('%Y-%m-%d %H:%M HKT')}  ",
        f"**Window:** last 24 hours  ",
        f"**Total tweets:** {total}",
        f"",
        "---",
        "",
    ]

    for acc, tweets in results:
        handle = acc["handle"]
        alias  = acc.get("alias", handle)
        lines.append(f"## @{handle} — {alias} ({len(tweets)} tweets)")
        lines.append("")
        if tweets:
            for t in tweets:
                lines.append(format_tweet_markdown(t))
                lines.append("")
        else:
            lines.append("_No tweets in the last 24 hours._")
            lines.append("")
        lines.append("---")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report saved to: {report_path}")

    # ── Telegram report ───────────────────────────────────────────────────────
    tg_name = f"report_{now.strftime('%Y-%m-%d_%H-%M')}_telegram.txt"
    tg_path = REPORTS_DIR / tg_name

    tg_lines = [
        f"📊 Twitter 日报 · {now.astimezone(HKT).strftime('%Y-%m-%d %H:%M HKT')}",
        f"共 {total} 条推文 · 过去 24 小时",
    ]

    for acc, tweets in results:
        handle = acc["handle"]
        alias  = acc.get("alias", handle)
        tg_lines.append(f"\n━━━━━━━━━━━━━━━━━━━")
        tg_lines.append(f"@{handle}  {alias}  ({len(tweets)} 条)")
        tg_lines.append(f"━━━━━━━━━━━━━━━━━━━")
        if not tweets:
            tg_lines.append("（过去 24 小时无推文）")
        for t in tweets:
            created = parse_date(t.get("createdAt", ""))
            time_str = created.astimezone(HKT).strftime("%m-%d %H:%M") if created else "?"
            text = t.get("text", "")
            url = t.get("url", "")
            likes = t.get("likeCount", 0)
            retweets = t.get("retweetCount", 0)
            media_urls = get_media_urls(t)

            tg_lines.append(f"\n🕐 {time_str} HKT")
            tg_lines.append(text)
            for mu in media_urls:
                tg_lines.append(mu)
            tg_lines.append(f"❤ {likes}  🔁 {retweets}  🔗 {url}")

    tg_path.write_text("\n".join(tg_lines), encoding="utf-8")
    print(f"Telegram report saved to: {tg_path}")


if __name__ == "__main__":
    main()

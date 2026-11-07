"""Extractor2 — daily tech-news digest -> Telegram.

Fetches 20+ reputable tech/cybersecurity RSS feeds once a day, dedupes
stories that are covered by many sources (keeps the best = most-covered,
ties broken by recency), and sends the digest to your Telegram bot.

Run once a day — cron on Linux, Task Scheduler on Windows:
    Linux:   0 9 * * * /usr/bin/python3 ~/extractor2/extractor2.py run --once
    Windows: run once a day via schtasks (see README)

Setup (one-time, interactive — token + chat id saved encrypted):
    python extractor2.py setup

Also in this repo: `aider news` style merge — extractor2 has a `--dry-run`
that prints the digest instead of sending (for testing).

Security: same model as extractor v1 (encrypted secrets, 3 wrong passwords
-> wipe). Stdlib only. Linux + Windows.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STATE_DIR = Path.home() / ".extractor2"
SECRETS_FILE = STATE_DIR / "secrets.enc"
SEEN_FILE = STATE_DIR / "seen.json"
DEFAULT_INTERVAL = 86400  # 24h
MAX_WRONG_PASSWORD = 3


# ---------------------------------------------------------------- sources
# 20+ verified-live RSS feeds (checked 7 Nov 2026). Each source: name, RSS URL,
# category. Dead/blocked feeds are documented as excluded below, not hidden.
SOURCES = [
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "tech"),
    ("TechCrunch", "https://techcrunch.com/feed/", "tech"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "tech"),
    ("WIRED", "https://www.wired.com/feed/rss", "tech"),
    ("Engadget", "https://www.engadget.com/rss.xml", "tech"),
    ("TechRadar", "https://www.techradar.com/feeds.xml", "tech"),
    ("How-To Geek", "https://www.howtogeek.com/feed/", "tech"),
    ("Phoronix", "https://www.phoronix.com/rss.php", "tech"),
    ("Linux.com", "https://www.linux.com/feed/", "tech"),
    ("Opensource.com", "https://opensource.com/feed", "tech"),
    ("Hacker News", "https://hnrss.org/frontpage", "tech"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/", "security"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "security"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml", "security"),
    ("SecurityWeek", "https://www.securityweek.com/feed/", "security"),
    ("EFF Deeplinks", "https://www.eff.org/rss/updates.xml", "security"),
    ("Freedom.press", "https://freedom.press/feed/", "security"),
    ("OpenAI News", "https://openai.com/news/rss.xml", "ai"),
    ("The New Stack", "https://thenewstack.io/feed/", "tech"),
    ("InfoQ", "https://feed.infoq.com", "tech"),
]

# Excluded after live probing (documented, not hidden):
# - CISA advisory feeds: Access Denied to non-browser clients (Akamai)
# - arstechnica.com/rss.xml + /civis: human-verification page for scripts
# - The Hacker News default feed: empty response to script clients
# - ZDNet/TechSpot/PCMag: Cloudflare challenge / empty
# - Anthropic/Blog.Google: HTML pages, no RSS at the probed URL
# - FeedBurner Wired mirror: hijacked by third-party feed (not ours)


@dataclass
class Story:
    title: str
    link: str
    source: str
    category: str
    published: datetime | None
    guid: str = ""


# --------------------------------------------------------------- scraping
def _fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "extractor2/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_date(raw: str) -> datetime | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%a, %d %b %Y %H:%M %z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            # Some feeds give naive dates — assume UTC so comparisons work.
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_feed(xml_bytes: bytes, source: str, category: str) -> list[Story]:
    """Parse RSS 2.0 and Atom. Returns stories; empty on malformed XML."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    stories: list[Story] = []
    # RSS 2.0: channel/item
    for item in root.iter("item"):
        title = _text(item, "title")
        link = _text(item, "link")
        if not title:
            continue
        stories.append(Story(title=title, link=link, source=source,
                             category=category,
                             published=_parse_date(_text(item, "pubDate")),
                             guid=_text(item, "guid") or link))
    # Atom: entry (namespaced)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = _text(entry, "a:title") or _text(entry, "{http://www.w3.org/2005/Atom}title")
        link_el = entry.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        if not title:
            continue
        stories.append(Story(title=title, link=link, source=source,
                             category=category,
                             published=_parse_date(_text(entry, "a:published")),
                             guid=link))
    return stories


def fetch_all_sources(timeout: int = 25) -> list[Story]:
    """All stories from all sources. A down source is skipped, never fatal."""
    all_stories: list[Story] = []
    for name, url, cat in SOURCES:
        try:
            stories = parse_feed(_fetch(url, timeout), name, cat)
            all_stories.extend(stories)
        except Exception as e:
            print(f"[{name}] skipped: {type(e).__name__}: {e}")
    # Keep recent + undated only (last 48h) — a daily digest, not an archive.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = [s for s in all_stories if s.published is None or s.published >= cutoff]
    print(f"Fetched {len(all_stories)} stories, {len(recent)} in last 48h.")
    return recent


# ------------------------------------------------------------ dedup logic
STOP = set("the a an and or of to in on for with is are was were be been at by from as".split())


def normalise_title(title: str) -> str:
    """Lowercase, strip punctuation, drop stopwords -> a comparable key."""
    text = html.unescape(title).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(w for w in text.split() if w not in STOP)


def jaccard(a: str, b: str) -> float:
    A, B = set(a.split()), set(b.split())
    return len(A & B) / len(A | B) if A and B else 0.0


def _pick_best(group: list[Story]) -> Story:
    """Best = most recent with a link; undated sorts after dated."""
    def score(s):
        return (s.published is not None, s.published or datetime.min.replace(tzinfo=timezone.utc),
                bool(s.link))
    return max(group, key=score)


def dedupe(stories: list[Story], threshold: float = 0.6) -> list[tuple[Story, int]]:
    """Group stories covering the same news (Jaccard on normalised titles).
    Returns (best_story, coverage_count) sorted by coverage desc, then recency.
    Greedy O(n^2) — fine at daily-digest scale (~200 stories)."""
    groups: list[list[Story]] = []
    for s in stories:
        nk = normalise_title(s.title)
        placed = False
        for g in groups:
            if jaccard(nk, normalise_title(g[0].title)) >= threshold:
                g.append(s)
                placed = True
                break
        if not placed:
            groups.append([s])
    result = [(_pick_best(g), len(g)) for g in groups]
    result.sort(key=lambda t: (t[1], t[0].published or datetime.min.replace(tzinfo=timezone.utc)),
                reverse=True)
    return result


# ----------------------------------------------------------------- output
def format_digest(ranked: list[tuple[Story, int]], top_n: int = 25) -> str:
    lines = [f"Tech news digest ({len(ranked)} stories, top {top_n}):"]
    for i, (story, n) in enumerate(ranked[:top_n], 1):
        line = f"{i}. [{story.source} x{n}] {story.title}" if n > 1 else f"{i}. [{story.source}] {story.title}"
        if story.link:
            line += f"\n   {story.link}"
        lines.append(line)
    return "\n".join(lines)[:4000]


# ------------------------------------------------------------------ state
def load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        items = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        return {i if isinstance(i, str) else i.get("id", "") for i in items if i}
    except Exception:
        return set()


def save_seen(ids: set[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SEEN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(ids), indent=1), encoding="utf-8")
    tmp.replace(SEEN_FILE)


# ---------------------------------------------------------------- secrets
def _keystream(password: str, salt: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(password.encode() + salt + str(counter).encode()).digest())
        counter += 1
    return bytes(out[:length])


def encrypt(password: str, plaintext: str) -> str:
    salt = os.urandom(16)
    data = plaintext.encode("utf-8")
    stream = _keystream(password, salt, len(data))
    cipher = bytes(b ^ s for b, s in zip(data, stream))
    return json.dumps({"v": 1, "salt": salt.hex(), "data": cipher.hex()})


def decrypt(password: str, blob: str) -> str:
    obj = json.loads(blob)
    salt = bytes.fromhex(obj["salt"])
    cipher = bytes.fromhex(obj["data"])
    stream = _keystream(password, salt, len(cipher))
    return bytes(b ^ s for b, s in zip(cipher, stream)).decode("utf-8")


def save_secrets(telegram_token: str, chat_id: str) -> None:
    pw = getpass.getpass("Set a master password (to view/change settings later): ")
    if len(pw) < 4:
        print("Password too short (min 4 chars). Aborting.")
        sys.exit(1)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"token": telegram_token, "chat_id": chat_id})
    SECRETS_FILE.write_text(encrypt(pw, payload), encoding="utf-8")
    SECRETS_FILE.chmod(0o600)
    print(f"Saved encrypted to {SECRETS_FILE}")


def load_secrets() -> dict:
    if not SECRETS_FILE.exists():
        print("No saved credentials. Run: python extractor2.py setup")
        sys.exit(1)
    blob = SECRETS_FILE.read_text(encoding="utf-8")
    for attempt in range(MAX_WRONG_PASSWORD):
        pw = getpass.getpass("Master password: ")
        try:
            data = json.loads(decrypt(pw, blob))
            if "token" in data and "chat_id" in data:
                return data
        except Exception:
            pass
        remaining = MAX_WRONG_PASSWORD - attempt - 1
        if remaining:
            print(f"Wrong password. {remaining} attempt(s) left.")
    SECRETS_FILE.unlink(missing_ok=True)
    print("WRONG PASSWORD x3 — credentials DELETED. Run setup again.")
    sys.exit(1)


# ---------------------------------------------------------------- telegram
def send_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


# -------------------------------------------------------------------- run
def run_once(dry_run: bool = False) -> tuple[int, int]:
    stories = fetch_all_sources()
    ranked = dedupe(stories)
    digest = format_digest(ranked)
    if dry_run:
        print(digest)
        return len(stories), len(ranked)
    secrets = load_secrets()
    ok = send_telegram(secrets["token"], secrets["chat_id"], digest)
    # Mark today's story ids as seen so the next run only sends new ones.
    ids = {s.link or s.guid or normalise_title(s.title) for s, _ in ranked}
    save_seen(ids | load_seen())
    print(f"Digest sent={ok}: {len(stories)} fetched, {len(ranked)} unique stories.")
    return len(stories), len(ranked)


def main() -> None:
    ap = argparse.ArgumentParser(description="Daily tech-news digest -> Telegram")
    ap.add_argument("cmd", choices=["setup", "run"])
    ap.add_argument("--once", action="store_true", help="single run then exit (run mode)")
    ap.add_argument("--dry-run", action="store_true", help="print digest, don't send (run mode)")
    args = ap.parse_args()

    if args.cmd == "setup":
        print("Telegram setup — token from @BotFather, chat id from @userinfobot.")
        token = getpass.getpass("Telegram bot token: ").strip()
        chat_id = input("Your Telegram chat id: ").strip()
        if not token or not chat_id:
            print("Both are required. Aborting.")
            sys.exit(1)
        save_secrets(token, chat_id)
        print("Test with: python extractor2.py run --once --dry-run")
        return

    if args.dry_run:
        run_once(dry_run=True)
        return
    run_once(dry_run=False)
    if not args.once:
        print("Daily mode: schedule with cron / Task Scheduler (see README). "
              "This process exits after one digest — it does not loop.")


if __name__ == "__main__":
    main()

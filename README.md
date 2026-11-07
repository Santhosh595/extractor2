# Extractor2 — Daily tech-news digest → Telegram

Fetches **20 reputable tech, security, and AI news sources** once a day, dedupes stories covered by multiple outlets (keeps the best = most-covered, ties by recency), and sends the digest to your Telegram bot.

Stdlib only — no `pip install`. Terminal only. Linux + Windows.

---

## One-line install

**Linux/macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/Santhosh595/extractor2/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/Santhosh595/extractor2/main/install.ps1 | iex
```

Installs Git + Python if missing, clones, runs `setup` (Telegram token + chat id + master password, once).

---

## Run it (daily)

```bash
python3 extractor2.py run --once --dry-run   # preview the digest, don't send
python3 extractor2.py run --once             # run once now (sends)
```

Extractor2 is a **once-a-day** tool — it exits after each run. Schedule it:

**Linux (cron, 09:00 daily):**

```cron
0 9 * * * /usr/bin/python3 /home/you/extractor2/extractor2.py run --once
```

**Windows (Task Scheduler, daily 09:00):**

```powershell
schtasks /create /tn "Extractor2Daily" /tr "python %USERPROFILE%\extractor2\extractor2.py run --once" /sc daily /st 09:00 /f
```

---

## Sources (20, verified live 7 Nov 2026)

| Category | Sources |
|---|---|
| Tech (12) | Ars Technica, TechCrunch, The Verge, WIRED, Engadget, TechRadar, How-To Geek, Phoronix, Linux.com, Opensource.com, Hacker News, The New Stack, InfoQ |
| Security (5) | BleepingComputer, Krebs on Security, Dark Reading, SecurityWeek, EFF Deeplinks |
| AI (1) | OpenAI News |

**Excluded after live probing** (documented in code, not hidden): CISA feeds (Access Denied to scripts), Ars `arstechnica.com/rss.xml` (human-verification page), The Hacker News default feed, ZDNet/TechSpot/PCMag (Cloudflare), Anthropic/Google AI blogs (no RSS at probed URL).

**Resilience:** if a source is down or changes shape, it's skipped that day with a log line. The digest still sends.

---

## How dedup works

1. Fetch all 20 feeds → ~1,800 stories, filtered to the last 48h (~260 today).
2. Normalise titles (lowercase, strip punctuation/stopwords) and group by **Jaccard similarity ≥ 0.6** on word sets.
3. Each group = one story, covered by N sources. The **best** version wins: most recent with a link.
4. Digest sorts by coverage desc, then recency. Output shows `[Source xN]` when multiple outlets covered it.

Same story on 15 sites → appears once, marked `x15`. Different stories stay separate. Both are unit-tested.

---

## Sample output

```
Tech news digest (258 stories, top 25):
1. [WIRED x3] The 10 Best Early Black Friday Headphone Deals (2026)
   https://www.wired.com/story/best-early-black-friday-headphone-deals-11-6-26/
2. [TechRadar x2] How to watch France vs Fiji: FREE live streams...
   https://www.techradar.com/...
```

---

## Security

Same model as extractor v1: token + chat id **encrypted at rest** (password-derived key, random salt, chmod 600, no echo via `getpass`). Wrong password ×3 → **credentials wiped**. Alerts only go to your authorised chat id. HTTPS only, no telemetry.

Honest limit: password-based encryption, not OS keyring — use a strong master password.

---

## State

| File | What |
|---|---|
| `~/.extractor2/secrets.enc` | Encrypted token + chat id |
| `~/.extractor2/seen.json` | Story IDs already sent (delete to resend) |

## Test

```bash
python3 -m unittest discover -s tests -v   # 13 tests
python3 extractor2.py run --once --dry-run # live preview
```

## Files

| File | What |
|---|---|
| `extractor2.py` | The digest tool — run this |
| `install.sh` / `install.ps1` | One-line installers |
| `tests/test_extractor2.py` | Unit tests (RSS/Atom parse, dedup, resilience, format) |

## License

MIT — do whatever, no warranty.

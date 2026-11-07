# Learn — extractor2

## What it is

Daily tech-news digest → Telegram. Fetches 20 RSS feeds (tech, security, AI), filters to 48h, dedupes stories covered by multiple outlets (Jaccard ≥ 0.6 on normalised titles), keeps the best version, sends the top 25. Once a day via cron / Task Scheduler. Same encrypted-secrets model as extractor v1.

**Read this first, then go file-by-file in the repo.**

## 5-minute quickstart

```bash
git clone https://github.com/Santhosh595/extractor2 && cd extractor2
python3 extractor2.py setup                     # token + chat id + password (once)
python3 extractor2.py run --once --dry-run      # preview, no send
python3 extractor2.py run --once                # send today's digest
python3 -m unittest discover -s tests -v      # 13 tests
```

## Concepts — the "why" behind each file

| If you see this in the code | What it means | Viva answer |
|---|---|---|
| `SOURCES` list (20 entries) | Curated RSS feeds, probed live | Each URL was curl-verified; blocked ones documented as excluded |
| `parse_feed()` RSS + Atom | XML parsing via ElementTree | RSS `item`, Atom `entry` (namespaced) — two shapes, one output |
| `_parse_date()` multi-format | `pubDate` formats vary by source | Try several formats; naive dates assumed UTC |
| 48h filter in `fetch_all_sources()` | Daily digest, not archive | Prevents 1,800-item dumps; "last 48h" is the window |
| `normalise_title()` + `jaccard()` ≥ 0.6 | Dedup by title similarity | Same story, different headlines → grouped; coverage = group size |
| `_pick_best()` (most recent + has link) | "Find the best one" | Coverage ranks stories; recency picks the representative |
| Per-source try/except in `fetch_all_sources()` | Resilience | One dead feed never kills the digest |
| `format_digest()` capped at 4000 chars | Telegram limit | Top-25 + summary first so truncation is graceful |
| `seen.json` atomic write | State between daily runs | No half-written state if killed |

## Common pitfalls

1. **Assuming one RSS format** — RSS 2.0 and Atom differ; handle both or 30% of sources silently return 0 stories.
2. **Naive vs aware datetimes** — some feeds give no timezone; comparing naive to aware raises `TypeError` (a real bug this repo hit and fixed — know the story).
3. **Exact-title dedup** — "OpenAI announces X" vs "OpenAI unveils X" wouldn't match. Fuzzy (Jaccard) is the fix; 0.6 is the threshold.
4. **Dead sources as fatal errors** — a 404 or Cloudflare block must skip, not crash.
5. **Sending duplicates daily** — `seen.json` prevents re-sending; delete it to resend.

## Hands-on, in this order

1. `run --once --dry-run`. How many fetched? How many in 48h? How many unique after dedup?
2. Find a story with `x3` coverage. Open all its sources — same event, different titles?
3. Read `parse_feed()`. What breaks if a feed returns HTML instead of XML? (The `ParseError` catch.)
4. Change threshold 0.6 → 0.9, re-run dry. What happens to the group count? (More duplicates slip through.)
5. Kill one feed (fake URL) in a test — digest still sends? (The resilience test proves it.)
6. Check the excluded list in the code. Pick one (e.g. CISA) and curl it. What do you get?

## Viva questions (with the trap)

1. **"How do you know two headlines are the same story?"** Answer: Jaccard on normalised word sets ≥ 0.6. Trap: exact matching.
2. **"Which version gets sent?"** Answer: the group representative = most recent with a link; coverage count shown as `xN`.
3. **"Why 48h, why daily?"** Answer: digest semantics — what changed today, not an archive.
4. **"What if a source is down?"** Answer: skipped with a log line; digest still sends. Never fatal.
5. **"Tell me about the datetime bug."** Answer: a feed returned naive dates; comparing to aware UTC raised `TypeError` and crashed the dry run. Fixed by assuming UTC for naive dates. Good war story.
6. **"Why 20 sources, not 200?"** Answer: reputation + reliability; each was probed live; quality over quantity.

## 3 things to say if stuck

- "Dedup is Jaccard on normalised titles; coverage count is the group size."
- "One dead feed never kills the digest — every source is isolated."
- "Let me run the dry-run and show you the grouping."

Good luck. This repo proves you can build a real information pipeline, not just a scraper.

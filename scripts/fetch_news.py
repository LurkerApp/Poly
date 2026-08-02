# ============================================================
# Market News → data/news.json
# ============================================================
# Fetches top financial headline from Reuters RSS via rss2json
# Falls back to Finnhub if Reuters fails
# Runs hourly via GitHub Actions — bypasses browser CORS
# ============================================================
# Dependencies: requests
# Secrets required (GitHub Actions → Settings → Secrets):
#   FINNHUB_KEY (fallback only)
# ============================================================

import os
import sys
import requests
import json
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────
FINNHUB_KEY  = os.environ.get("FINNHUB_KEY", "")
OUTPUT_FILE  = "data/news.json"
HEADERS      = {"User-Agent": "LurkerApp contact@lurkerapp.com"}

# RSS feeds to try in order
RSS_FEEDS = [
    {
        "name":    "Reuters Markets",
        "url":     "https://api.rss2json.com/v1/api.json?rss_url=https://feeds.reuters.com/reuters/businessNews&count=20",
    },
    {
        "name":    "Reuters Top News",
        "url":     "https://api.rss2json.com/v1/api.json?rss_url=https://feeds.reuters.com/reuters/topNews&count=20",
    },
    {
        "name":    "MarketWatch",
        "url":     "https://api.rss2json.com/v1/api.json?rss_url=https://feeds.content.dowjones.io/public/rss/mw_topstories&count=20",
    },
    {
        "name":    "CNBC Markets",
        "url":     "https://api.rss2json.com/v1/api.json?rss_url=https://www.cnbc.com/id/10000664/device/rss/rss.html&count=20",
    },
]

# Skip articles that match these patterns — opinion, recaps, fluff
SKIP_PATTERNS = [
    "week ahead", "things to watch", "here are", "here's what",
    "why you should", "opinion:", "opinion |", "what to watch",
    "5 things", "10 things", "everything you need", "quiz",
    "chart of the day", "morning briefing", "evening briefing",
    "podcast", "video:", "watch:", "listen:", "morning call",
]

# Prefer articles containing these keywords — breaking market news
PREFER_KEYWORDS = [
    "fed", "rate", "inflation", "gdp", "jobs", "earnings",
    "tariff", "market", "stock", "bond", "yield", "nasdaq",
    "s&p", "dow", "crude", "oil", "gold", "dollar", "recession",
    "bank", "treasury", "economic", "trade", "deficit", "surplus",
    "powell", "fomc", "interest rate", "cpi", "pce", "unemployment",
    "rally", "selloff", "sell-off", "surge", "plunge", "crash",
    "ipo", "merger", "acquisition", "buyout", "bankruptcy",
]

# ── Score an article for relevance ───────────────────────────
def score_article(title, description):
    text = (title + " " + (description or "")).lower()

    # Skip low quality
    for pattern in SKIP_PATTERNS:
        if pattern in text:
            return -1

    # Score by keyword relevance
    score = 0
    for kw in PREFER_KEYWORDS:
        if kw in text:
            score += 1

    return score

# ── Fetch from RSS source ─────────────────────────────────────
def fetch_from_rss(feed):
    print(f"  Trying {feed['name']}...")
    try:
        resp = requests.get(feed["url"], headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}")
            return None

        data  = resp.json()
        items = data.get("items", [])

        if not items:
            print(f"  ✗ No items returned")
            return None

        print(f"  ✓ {len(items)} articles fetched — scoring...")

        # Score and sort articles
        scored = []
        for item in items:
            title = item.get("title", "")
            desc  = item.get("description", "")
            s     = score_article(title, desc)
            if s >= 0:
                scored.append((s, item))

        if not scored:
            print(f"  ✗ All articles filtered out")
            return None

        # Sort by score desc, pick best
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        print(f"  ✓ Best article (score {best_score}): {best['title'][:70]}...")

        # Parse pub date to unix timestamp
        pub_date = best.get("pubDate", "")
        try:
            dt        = datetime.strptime(pub_date, "%Y-%m-%d %H:%M:%S")
            timestamp = int(dt.replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            timestamp = int(datetime.now(timezone.utc).timestamp())

        return {
            "headline":     best.get("title", ""),
            "url":          best.get("link", "#"),
            "source":       feed["name"],
            "summary":      best.get("description", "")[:300] if best.get("description") else "",
            "datetime":     timestamp,
        }

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None

# ── Fallback: Finnhub ─────────────────────────────────────────
def fetch_from_finnhub():
    if not FINNHUB_KEY:
        return None
    print(f"  Trying Finnhub fallback...")
    try:
        url  = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        articles = resp.json()
        for a in articles:
            title = a.get("headline", "")
            score = score_article(title, a.get("summary", ""))
            if score >= 0 and title and a.get("url"):
                print(f"  ✓ Finnhub: {title[:70]}...")
                return {
                    "headline": title,
                    "url":      a.get("url", "#"),
                    "source":   a.get("source", "Finnhub"),
                    "summary":  a.get("summary", "")[:300],
                    "datetime": a.get("datetime", 0),
                }
    except Exception as e:
        print(f"  ✗ Finnhub error: {e}")
    return None

# ── Main ─────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Market News Fetcher")
    print("=" * 60)

    article = None

    # Try RSS feeds in order
    for feed in RSS_FEEDS:
        article = fetch_from_rss(feed)
        if article:
            break

    # Fallback to Finnhub
    if not article:
        print("\n  All RSS feeds failed — trying Finnhub...")
        article = fetch_from_finnhub()

    if not article:
        print("\n✗ Could not fetch any headline — exiting")
        sys.exit(1)

    output = {
        "headline":     article["headline"],
        "url":          article["url"],
        "source":       article["source"],
        "summary":      article.get("summary", ""),
        "datetime":     article["datetime"],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved to {OUTPUT_FILE}")
    print(f"  Headline : {output['headline'][:80]}")
    print(f"  Source   : {output['source']}")
    print(f"  Updated  : {output['last_updated']}")

if __name__ == "__main__":
    main()

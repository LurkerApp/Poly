# ============================================================
# Finnhub Market News → data/news.json
# ============================================================
# Fetches top financial headline from Finnhub and saves to
# data/news.json for the index page to read statically
# Bypasses CORS restrictions by running server-side
# ============================================================
# Dependencies: requests
# Secrets required (GitHub Actions → Settings → Secrets):
#   FINNHUB_KEY
# ============================================================

import os
import sys
import requests
import json
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────
FINNHUB_KEY = os.environ.get("FINNHUB_KEY")

if not FINNHUB_KEY:
    print("ERROR: FINNHUB_KEY must be set as environment variable.")
    sys.exit(1)

OUTPUT_FILE = "data/news.json"
HEADERS     = {"User-Agent": "LurkerApp contact@lurkerapp.com"}

# Try categories in order — most finance-focused first
CATEGORIES  = ["general", "forex", "merger"]

# ── Fetch headline ────────────────────────────────────────────
def fetch_headline():
    for category in CATEGORIES:
        url  = f"https://finnhub.io/api/v1/news?category={category}&token={FINNHUB_KEY}"
        print(f"  Trying category: {category}...")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
        except Exception as e:
            print(f"  ✗ Request error: {e}")
            continue

        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}")
            continue

        articles = resp.json()
        if not articles:
            print(f"  ✗ No articles returned")
            continue

        # Pick first article with a headline, url and recent datetime
        for article in articles:
            if article.get("headline") and article.get("url") and article.get("datetime"):
                print(f"  ✓ Found: {article['headline'][:70]}...")
                return article, category

    return None, None

# ── Main ─────────────────────────────────────────────────────
def main():
    print("Fetching Finnhub headline...")

    article, category = fetch_headline()

    if not article:
        print("✗ No headline found — exiting")
        sys.exit(1)

    output = {
        "headline":     article.get("headline", ""),
        "url":          article.get("url", "#"),
        "source":       article.get("source", "Finnhub"),
        "summary":      article.get("summary", ""),
        "image":        article.get("image", ""),
        "datetime":     article.get("datetime", 0),
        "category":     category,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved to {OUTPUT_FILE}")
    print(f"  Headline : {output['headline'][:80]}")
    print(f"  Source   : {output['source']}")
    print(f"  Category : {output['category']}")
    print(f"  Updated  : {output['last_updated']}")

if __name__ == "__main__":
    main()

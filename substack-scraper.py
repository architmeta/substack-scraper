# ============================================================================
# SUBSTACK SCRAPER - Multiple authors in separate columns
# ============================================================================
# INSTRUCTIONS: Change BASE and OUTPUT_CSV below, then run: python scraper.py
# ============================================================================

import csv
import time
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# ============================================================================
# CONFIGURATION - CHANGE THESE TWO LINES
# ============================================================================
BASE = "https://dropsitenews.com"  # Your target Substack URL
OUTPUT_CSV = "output.csv"   # Output filename

# ============================================================================
# Setup (don't change)
# ============================================================================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})
API_URL = urljoin(BASE, "/api/v1/posts")

# ============================================================================
# Functions
# ============================================================================
def fetch_page(limit=50, offset=0):
    params = {"limit": limit, "offset": offset, "sort": "new"}
    resp = session.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()

def extract_authors(post_url):
    """Returns a LIST of author names"""
    try:
        resp = session.get(post_url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = []
        for a in soup.select("a[href*='@']"):
            txt = a.get_text(strip=True)
            if txt and len(txt.split()) <= 5:
                candidates.append(txt)
        for sel in [".byline", ".post-meta", "[data-testid='post-byline']", ".author-name"]:
            for el in soup.select(sel):
                txt = el.get_text(" ", strip=True)
                if txt:
                    candidates.append(txt)
        cleaned = []
        seen = set()
        for c in candidates:
            if c and c not in seen:
                cleaned.append(c)
                seen.add(c)
        return cleaned  # Return list instead of joined string
    except:
        return []

def normalize_post(post):
    date = post.get("published_at") or post.get("post_date") or post.get("created_at") or ""
    headline = (post.get("title") or "").strip()
    subheading = (post.get("subtitle") or post.get("dek") or post.get("description") or "").strip()
    if "url" in post and post["url"]:
        url = urljoin(BASE, post["url"])
    else:
        slug = post.get("slug") or post.get("id")
        url = f"{BASE}/p/{slug}" if slug else ""
    authors = extract_authors(url) if url else []  # Get list of authors
    return {"date": date, "authors": authors, "headline": headline, "url": url, "subheading": subheading}

# ============================================================================
# Main scraping loop
# ============================================================================
print("Starting scrape...")
all_posts = []
offset = 0
max_authors = 0  # Track max number of authors for any article

for page_num in range(1000):
    print(f"Page {page_num+1}... ", end="", flush=True)
    data = fetch_page(limit=50, offset=offset)
    posts = data if isinstance(data, list) else data.get("posts") or data.get("items") or data.get("results")
    if not posts:
        print("done")
        break
    count = 0
    for post in posts:
        row = normalize_post(post)
        all_posts.append(row)
        max_authors = max(max_authors, len(row["authors"]))  # Track max authors
        count += 1
        time.sleep(0.2)
    print(f"{count} posts")
    if count < 50:
        break
    offset += count
    time.sleep(0.5)

# ============================================================================
# Save to CSV with separate author columns
# ============================================================================
# Build fieldnames: date, author_1, author_2, ..., headline, url, subheading
fieldnames = ["date"]
for i in range(1, max_authors + 1):
    fieldnames.append(f"author_{i}")
fieldnames.extend(["headline", "url", "subheading"])

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for post in all_posts:
        row = {
            "date": post["date"],
            "headline": post["headline"],
            "url": post["url"],
            "subheading": post["subheading"]
        }
        # Add each author to separate column
        for i, author in enumerate(post["authors"], start=1):
            row[f"author_{i}"] = author
        writer.writerow(row)

print(f"\n✓ Saved {len(all_posts)} posts to {OUTPUT_CSV}")
print(f"  Max authors per article: {max_authors}")

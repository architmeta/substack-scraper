# ============================================================================
# SUBSTACK SCRAPER - Scrapes all articles from Substack site's archive page
# ============================================================================
# This script downloads all posts from a Substack publication and saves them
# to a CSV file with: date, author, headline, URL, and subheading/description
# ============================================================================

# Import required libraries
import csv  # For writing data to CSV files
import time  # For adding delays between requests (to be polite to the server)
import requests  # For making HTTP requests to fetch web pages and APIs
from urllib.parse import urljoin  # For building complete URLs from relative paths
from bs4 import BeautifulSoup  # For parsing HTML and extracting author names

# ============================================================================
# CONFIGURATION - Change these values for different Substack sites
# ============================================================================

BASE = "https://zeteo.com"  # The base URL of the Substack publication. Note 1: For your project, change the URL here. 
API_URL = urljoin(BASE, "/api/v1/posts")  # Build the API endpoint URL
OUTPUT_CSV = "zeteo_all_posts.csv"  # Name of the output CSV file Note 2: For your project, rename the CSV file here. 

# ============================================================================
# SESSION SETUP - Configure how we make requests to the server
# ============================================================================

# Create a session object to reuse connections and maintain settings
session = requests.Session()

# Set headers to make our requests look like they're coming from a regular browser
# This helps avoid being blocked by some websites
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",  # Tell the server we want JSON responses
})

# ============================================================================
# FUNCTION: fetch_page
# Purpose: Get one page of posts from the Substack API
# ============================================================================

def fetch_page(limit=50, offset=0):
    """
    Fetch a single page of posts from the Substack API.
    
    Parameters:
    - limit: How many posts to fetch per page (default: 50)
    - offset: How many posts to skip (used for pagination)
    
    Returns:
    - JSON data containing the posts
    """
    # Build the query parameters for the API request
    params = {
        "limit": limit,    # Number of posts to return
        "offset": offset,  # Starting position (0 for first page, 50 for second, etc.)
        "sort": "new",     # Sort by newest first
    }
    
    # Make the HTTP GET request to the API
    resp = session.get(API_URL, params=params, timeout=20)
    
    # Check if the request was successful (raises error if not)
    resp.raise_for_status()
    
    # Parse and return the JSON response
    return resp.json()

# ============================================================================
# FUNCTION: extract_author_from_html
# Purpose: Get the author's name by scraping the article's HTML page
# ============================================================================

def extract_author_from_html(post_url):
    """
    Fetch an article's HTML page and extract the author byline.
    
    This is necessary because the API doesn't always return author names
    in a consistent format, but the HTML page always displays them visibly.
    
    Parameters:
    - post_url: The full URL of the article
    
    Returns:
    - A string with author name(s), or empty string if not found
    """
    try:
        # Download the article's HTML page
        resp = session.get(post_url, timeout=20)
        resp.raise_for_status()
        
        # Parse the HTML using BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        # List to collect potential author names we find
        candidates = []

        # Strategy 1: Look for links to author profiles (e.g., /@username)
        # These are common on Substack articles
        for a in soup.select("a[href*='@']"):
            txt = a.get_text(strip=True)
            # Only keep short text (avoid long sentences or descriptions)
            if txt and len(txt.split()) <= 5:
                candidates.append(txt)

        # Strategy 2: Look for common byline HTML classes/attributes
        # Different Substack themes use different class names
        for sel in [
            ".byline",                        # Common CSS class for bylines
            ".post-meta",                     # Another common class
            "[data-testid='post-byline']",   # Substack's standard attribute
            ".author-name",                   # Generic author class
        ]:
            for el in soup.select(sel):
                txt = el.get_text(" ", strip=True)
                if txt:
                    candidates.append(txt)

        # Clean up the list: remove duplicates while preserving order
        cleaned = []
        seen = set()  # Track what we've already added
        for c in candidates:
            if c and c not in seen:
                cleaned.append(c)
                seen.add(c)

        # Join multiple authors with commas (e.g., "Author1, Author2")
        return ", ".join(cleaned) if cleaned else ""
        
    except Exception:
        # If anything goes wrong (network error, parsing error, etc.)
        # just return an empty string instead of crashing
        return ""

# ============================================================================
# FUNCTION: normalize_post
# Purpose: Convert a raw post from the API into our desired CSV format
# ============================================================================

def normalize_post(post):
    """
    Take a post object from the API and extract the fields we want.
    
    Parameters:
    - post: A dictionary representing one post from the API
    
    Returns:
    - A dictionary with the fields: date, author_byline, headline, url, subheading
    """
    
    # EXTRACT DATE: Try multiple possible field names
    # Different API responses might use different field names for dates
    date = (
        post.get("published_at")   # Most common field
        or post.get("post_date")   # Alternative field
        or post.get("created_at")  # Fallback field
        or ""                      # Empty string if none found
    )

    # EXTRACT HEADLINE: Get the post title
    headline = (post.get("title") or "").strip()

    # EXTRACT SUBHEADING/PREAMBLE: Try multiple field names
    # This is usually a short description or subtitle
    subheading = (
        post.get("subtitle")      # Most common
        or post.get("dek")        # Journalism term for subheading
        or post.get("description") # Alternative field
        or ""                     # Empty if not found
    ).strip()

    # BUILD URL: Either use the provided URL or construct from slug
    if "url" in post and post["url"]:
        # If the post has a direct URL, use it
        url = urljoin(BASE, post["url"])  # Make sure it's a complete URL
    else:
        # Otherwise, build URL from the slug (e.g., /p/article-slug)
        slug = post.get("slug") or post.get("id")
        url = f"{BASE}/p/{slug}" if slug else ""

    # EXTRACT AUTHOR: Scrape from the HTML page
    # We do this because API author data is inconsistent across Substack sites
    author_byline = extract_author_from_html(url) if url else ""

    # Return a dictionary with all our extracted fields
    return {
        "date": date,
        "author_byline": author_byline,
        "headline": headline,
        "url": url,
        "subheading": subheading,
    }

# ============================================================================
# FUNCTION: scrape_all_posts
# Purpose: Main scraping loop - fetch all pages until we've got everything
# ============================================================================

def scrape_all_posts(limit=50, max_pages=1000, delay=0.5, per_post_delay=0.2):
    """
    Scrape all posts from the publication by paginating through the API.
    
    Parameters:
    - limit: How many posts to fetch per API call (default: 50)
    - max_pages: Maximum number of pages to fetch (safety limit, default: 1000)
    - delay: Seconds to wait between API calls (default: 0.5)
    - per_post_delay: Seconds to wait between scraping individual articles (default: 0.2)
    
    Returns:
    - A list of dictionaries, one per post
    """
    
    all_rows = []  # List to collect all posts
    offset = 0     # Start at the beginning (first post)

    # Loop through pages until we run out of posts or hit max_pages
    for page_num in range(max_pages):
        
        # Print progress (on same line, gets updated with count)
        print(f"Fetching page {page_num+1}... ", end="", flush=True)
        
        # Fetch one page of posts from the API
        data = fetch_page(limit=limit, offset=offset)

        # The API response might be a list or a dict with a "posts" key
        # Handle both cases
        posts = data
        if isinstance(data, dict):
            # If it's a dictionary, look for the posts list inside
            posts = data.get("posts") or data.get("items") or data.get("results")

        # If no posts were returned, we've reached the end
        if not posts:
            print("done (no more posts)")
            break

        # Process each post in this page
        count = 0
        for post in posts:
            # Convert the raw post to our CSV format
            row = normalize_post(post)
            
            # Add it to our collection
            all_rows.append(row)
            count += 1
            
            # Be polite: wait a bit before scraping the next article's HTML
            time.sleep(per_post_delay)

        # Print how many posts we got from this page
        print(f"{count} posts collected")

        # If we got fewer posts than the limit, this was the last page
        if count < limit:
            break

        # Move to the next page by increasing the offset
        offset += count
        
        # Be polite: wait before making the next API request
        time.sleep(delay)

    # Return all the posts we collected
    return all_rows

# ============================================================================
# FUNCTION: save_to_csv
# Purpose: Write all the collected posts to a CSV file
# ============================================================================

def save_to_csv(rows, path=OUTPUT_CSV):
    """
    Save the scraped posts to a CSV file.
    
    Parameters:
    - rows: List of dictionaries, each representing one post
    - path: Filename to save to (default: from OUTPUT_CSV constant)
    """
    
    # Define the column names for our CSV
    fieldnames = ["date", "author_byline", "headline", "url", "subheading"]
    
    # Open the file for writing (creates new file or overwrites existing)
    with open(path, "w", newline="", encoding="utf-8") as f:
        
        # Create a CSV writer that uses our field names
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        # Write the header row (column names)
        writer.writeheader()
        
        # Write each post as a row in the CSV
        for r in rows:
            writer.writerow(r)

# ============================================================================
# MAIN EXECUTION - This runs when you execute the script
# ============================================================================

if __name__ == "__main__":
    # Print a starting message
    print("Starting scrape...")
    
    # Run the main scraping function
    rows = scrape_all_posts(limit=50)
    
    # Print summary of what we found
    print(f"\nTotal posts fetched: {len(rows)}")
    
    # Save everything to CSV
    save_to_csv(rows)
    
    # Confirm completion
    print(f"Saved to {OUTPUT_CSV}")

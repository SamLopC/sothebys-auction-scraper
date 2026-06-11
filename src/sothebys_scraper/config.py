"""Central configuration for the Sotheby's scraper."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
TOKEN_CACHE_FILE = PROJECT_ROOT / ".token_cache.json"

load_dotenv(PROJECT_ROOT / ".env")

SOTHEBYS_EMAIL = os.getenv("SOTHEBYS_EMAIL", "")
SOTHEBYS_PASSWORD = os.getenv("SOTHEBYS_PASSWORD", "")
# Optional: paste a bearer token copied from Chrome DevTools (see README).
SOTHEBYS_BEARER_TOKEN = os.getenv("SOTHEBYS_BEARER_TOKEN", "").strip()

BASE_URL = "https://www.sothebys.com"
RESULTS_URL = f"{BASE_URL}/en/results"
GRAPHQL_URL = "https://clientapi.prod.sothelabs.com/graphql"

# Department facet IDs used by the /en/results search module (?f2=<id>).
# Extracted from the search filter form on sothebys.com/en/results.
DEPARTMENT_FACETS = {
    "impressionist-modern-art": "00000164-609b-d1db-a5e6-e9ff08ab0000",
    "modern-art-asia": "00000164-609a-d1db-a5e6-e9fff8ca0000",
    "contemporary-art": "00000164-609b-d1db-a5e6-e9ff01230000",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Politeness settings
REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
LOTS_PAGE_SIZE = 50

# Default cap on total lots scraped (0 = no limit). Override via --limit.
DEFAULT_RESULT_LIMIT = 10

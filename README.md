# Sotheby's Auction Results Scraper

A Python scraper that walks Sotheby's past-auction results, enters every
auction, and collects each lot's **URL** and **price** (hammer price when
available, plus low/high estimates) into a clean CSV.

## How it works

Sotheby's is a Next.js single-page app. Rather than brittle HTML scraping of
lot pages, this project uses the two layers the site itself uses:

1. **Auction discovery** — the `/en/results` listing is server-rendered and
   paginated (`?p=N`) with department filtering (`?f2=<facet-id>`). We parse
   the auction-card links (`src/sothebys_scraper/auctions.py`).
2. **Lot data** — each auction is backed by a GraphQL API
   (`clientapi.prod.sothelabs.com`). We replay the site's own
   `LotCardsFilterByPaginated` operation to page through every lot, reading
   title, artist, lot URL, estimates and the sold/hammer price
   (`src/sothebys_scraper/lots.py`).

### Why login is required

Sold (hammer) prices are returned by the API as `ResultVisible` **only for
authenticated users**; anonymous calls get `ResultHidden`.

Sotheby's login is protected by **Cloudflare Turnstile**, which blocks
automated browsers. The scraper therefore uses a **manual login** flow: it
opens a real Chrome window, you log in yourself (including the captcha
checkbox), and the scraper captures the bearer token from the site's own API
calls. The token is cached in `.token_cache.json` until it expires.

## Project layout

```
SOTHEBYS/
├── README.md
├── requirements.txt
├── .env                      # credentials (gitignored)
├── data/                     # CSV output (gitignored)
└── src/
    └── sothebys_scraper/
        ├── __init__.py
        ├── __main__.py       # CLI entrypoint
        ├── config.py         # URLs, facet IDs, tunables
        ├── auth.py           # Auth0 login -> bearer token
        ├── auctions.py       # results-listing discovery
        ├── lots.py           # GraphQL lot scraping
        └── exporter.py       # CSV writer
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file (credentials are optional if you use manual login):

```
SOTHEBYS_EMAIL=you@example.com
SOTHEBYS_PASSWORD=your-password
```

## Usage

### Step 1 — Log in (one time)

```bash
source venv/bin/activate
python -m sothebys_scraper --login-only
```

A Chrome window opens. Log in yourself:
1. Enter your email → Continue
2. Check **"Verify you are human"**
3. Enter your password → Continue

The scraper captures your session token and saves it to `.token_cache.json`.

**Alternative — paste a token from your own Chrome:**

If you are already logged in on Chrome, you can skip the browser step:

1. Open DevTools (`F12`) → **Network** tab → filter `graphql`
2. Click any request to `clientapi.prod.sothelabs.com`
3. Under **Request Headers**, copy the `Authorization` value (without `Bearer `)
4. Add to `.env`:

```
SOTHEBYS_BEARER_TOKEN=eyJhbGciOi...
```

### Step 2 — Scrape

```bash
# Scrape Impressionist & Modern Art (default department)
python -m sothebys_scraper --department impressionist-modern-art

# Test with a small sample first (default limit is 10 lots)
python -m sothebys_scraper --department impressionist-modern-art --limit 10

# Full scrape — remove the lot cap
python -m sothebys_scraper --department impressionist-modern-art --limit 0

# All departments
python -m sothebys_scraper --department all
```

Run `python -m sothebys_scraper --help` for all options.

### Departments available

| key                        | label                       |
|----------------------------|-----------------------------|
| `impressionist-modern-art` | Impressionist & Modern Art  |
| `modern-art-asia`          | Modern Art \| Asia          |
| `contemporary-art`         | Contemporary Art            |
| `all`                      | No department filter        |

## Output

A CSV in `data/` with one row per lot:

| column | description |
|--------|-------------|
| `auction_title`  | Auction name |
| `auction_year`   | Auction year |
| `auction_slug`   | Auction URL slug |
| `lot_number`     | Display lot number |
| `title`          | Lot/artwork title |
| `artist`         | Creator / artist |
| `category`       | Object type(s), e.g. `Painting`, `Sculpture` |
| `url`            | Canonical lot URL |
| `currency`       | Sale currency (e.g. USD) |
| `low_estimate`   | Low estimate |
| `high_estimate`  | High estimate |
| `sold`           | `yes` / `no` / `hidden` |
| `hammer_price`   | Final price when visible |

## Tuning

Edit `DEFAULT_RESULT_LIMIT` in `src/sothebys_scraper/config.py` to change the
default lot cap (currently **10**). Use `--limit 0` on the CLI for an unlimited
full scrape.

## Notes & etiquette

- A polite delay (`REQUEST_DELAY_SECONDS`) is applied between requests.
- Credentials and tokens are never committed (see `.gitignore`).
- This is for personal/research use; respect Sotheby's Terms of Service.

# Commands — Sotheby's Scraper

Copy and paste these in Terminal. Run from the project folder unless noted.

---

## One-time setup

```bash
cd /Users/samlop/Desktop/SOTHEBYS

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Edit .env with your Sotheby's email/password (optional if you paste a token instead)
```

Every new terminal session:

```bash
cd /Users/samlop/Desktop/SOTHEBYS
source venv/bin/activate
export PYTHONPATH=src
```

---

## Step 1 — Log in (do this first, or when the token expires)

**Option A — Manual login (recommended)**

```bash
python -m sothebys_scraper --login-only
```

1. Chrome opens → enter email → Continue  
2. Check **Verify you are human**  
3. Enter password → Continue  
4. Token is saved to `.token_cache.json`

**Option B — Paste token from your own Chrome**

1. On sothebys.com: DevTools (`F12`) → Network → filter `graphql`  
2. Click a request to `clientapi.prod.sothelabs.com`  
3. Copy the `Authorization` header value (without `Bearer `)  
4. Add to `.env`:

```
SOTHEBYS_BEARER_TOKEN=paste_token_here
```

---

## Step 2 — Scrape

**Quick test (10 lots — default limit)**

```bash
python -m sothebys_scraper --department impressionist-modern-art
```

**Custom number of lots**

```bash
python -m sothebys_scraper --department impressionist-modern-art --limit 50
```

**Full scrape (no lot limit)**

```bash
python -m sothebys_scraper --department impressionist-modern-art --limit 0
```

**Other departments**

```bash
python -m sothebys_scraper --department contemporary-art
python -m sothebys_scraper --department modern-art-asia
python -m sothebys_scraper --department all --limit 0
```

**Save to a specific CSV file**

```bash
python -m sothebys_scraper --department impressionist-modern-art --limit 100 --output data/my_results.csv
```

**Verbose logs (debugging)**

```bash
python -m sothebys_scraper --department impressionist-modern-art --limit 10 -v
```

**Skip login (prices may be hidden)**

```bash
python -m sothebys_scraper --no-login --limit 10
```

---

## Change defaults without CLI flags

Edit `src/sothebys_scraper/config.py`:

| Setting | What it does | Current default |
|---------|----------------|-----------------|
| `DEFAULT_RESULT_LIMIT` | Max lots per run | `10` |
| `REQUEST_DELAY_SECONDS` | Pause between requests | `1.0` |

Use `--limit 0` on the command line to ignore the lot cap for a full run.

---

## Output

CSV files are written to:

```
data/sothebys_lots_YYYYMMDD_HHMMSS.csv
```

Columns include: `auction_title`, `lot_number`, `title`, `artist`, `category`, `url`, `low_estimate`, `high_estimate`, `sold`, `hammer_price`.

---

## Troubleshooting

**Token expired**

```bash
rm .token_cache.json
python -m sothebys_scraper --login-only
```

**Module not found**

```bash
export PYTHONPATH=src
```

**See all options**

```bash
python -m sothebys_scraper --help
```

"""Discovery of past auctions from the sothebys.com results listing.

The /en/results page is server-rendered and paginated via ?p=N, with
department filtering via ?f2=<facet-id>. Each auction card links to
/en/buy/auction/<year>/<slug>.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from . import config

log = logging.getLogger(__name__)

AUCTION_URL_RE = re.compile(r"/en/buy/auction/(\d{4})/([a-z0-9-]+)")


@dataclass(frozen=True)
class AuctionRef:
    """A reference to one past auction discovered on the results page."""

    url: str
    year: str
    slug: str
    title: str


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})
    return session


def _parse_results_page(html: str) -> list[AuctionRef]:
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, AuctionRef] = {}
    for card in soup.select("a[href*='/en/buy/auction/']"):
        href = card.get("href", "")
        match = AUCTION_URL_RE.search(href)
        if not match:
            continue
        url = f"{config.BASE_URL}/en/buy/auction/{match.group(1)}/{match.group(2)}"
        title = card.get_text(strip=True)
        prev = found.get(url)
        # Several anchors point at the same auction; keep the longest text
        # (the card body usually contains the auction title).
        if prev is None or len(title) > len(prev.title):
            found[url] = AuctionRef(
                url=url, year=match.group(1), slug=match.group(2), title=title
            )
    return list(found.values())


def discover_auctions(
    department: str | None = None,
    max_pages: int | None = None,
) -> list[AuctionRef]:
    """Walk the paginated results listing and collect auction references.

    Args:
        department: key into config.DEPARTMENT_FACETS (e.g.
            "impressionist-modern-art"), or None for all departments.
        max_pages: stop after this many listing pages (None = all pages).
    """
    session = _new_session()
    params: dict[str, str] = {}
    if department:
        facet = config.DEPARTMENT_FACETS.get(department)
        if not facet:
            raise ValueError(
                f"Unknown department '{department}'. "
                f"Choices: {sorted(config.DEPARTMENT_FACETS)}"
            )
        params["f2"] = facet

    auctions: dict[str, AuctionRef] = {}
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break
        params["p"] = str(page)
        log.info("Fetching results listing page %d ...", page)
        resp = session.get(
            config.RESULTS_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()

        page_auctions = _parse_results_page(resp.text)
        new = [a for a in page_auctions if a.url not in auctions]
        if not new:
            log.info("No new auctions on page %d, stopping pagination", page)
            break
        for auction in new:
            auctions[auction.url] = auction
        log.info("  +%d auctions (total %d)", len(new), len(auctions))

        # Stop when the listing has no link to the next page.
        if f"p={page + 1}" not in resp.text:
            break
        page += 1
        time.sleep(config.REQUEST_DELAY_SECONDS)

    log.info("Discovered %d auctions", len(auctions))
    return list(auctions.values())

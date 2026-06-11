"""Lot-level scraping via Sotheby's GraphQL client API.

Each auction page is a Next.js SPA backed by the Cosmo GraphQL router at
clientapi.prod.sothelabs.com. We replay two of its operations:

  * AuctionIdBySlug      -> resolve the auction UUID from year + slug
  * LotCardsFilterByPaginated -> page through every lot in the auction

Hammer prices (finalPrice) are only returned as ``ResultVisible`` when the
caller is authenticated, which is why an Auth0 bearer token is required.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from . import config
from .auctions import AuctionRef

log = logging.getLogger(__name__)

AUCTION_ID_QUERY = """
query AuctionIdBySlug($name: String!, $year: String!) {
  auction: auctionBySlug(slug: {name: $name, year: $year}) {
    auctionId
    title
    currencyV2
  }
}
"""

LOT_CARDS_QUERY = """
query LotCardsFilterByPaginated(
  $id: String!, $filter: LotCardsConnectionFilter!,
  $language: TranslationLanguage!, $limit: Int, $offset: Int
) {
  auction(id: $id, language: $language) {
    lotCards: lotCardsConnection(offset: $offset, limit: $limit, filter: $filter) {
      lots {
        lotId
        title
        creatorsDisplayTitle
        slug { lotSlug }
        lotNumber { ... on VisibleLotNumber { lotDisplayNumber } }
        auction { auctionId currency slug { name year } }
        estimateV2 {
          __typename
          ... on LowHighEstimateV2 {
            lowEstimate { amount currency }
            highEstimate { amount currency }
          }
        }
        withdrawnState { state }
        bidState {
          sold {
            __typename
            ... on ResultVisible {
              isSold
              premiums { finalPrice: finalPriceV2 { amount currency } }
            }
          }
        }
      }
      hasNextPage
      totalCount
    }
  }
}
"""


@dataclass
class Lot:
    """A single lot (artwork) within an auction."""

    auction_title: str
    auction_year: str
    auction_slug: str
    lot_number: str
    title: str
    artist: str
    url: str
    currency: str
    low_estimate: str
    high_estimate: str
    sold: str
    hammer_price: str


class GraphQLClient:
    """Thin authenticated GraphQL client with retry/backoff."""

    def __init__(self, bearer_token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.USER_AGENT,
                "Content-Type": "application/json",
                "Origin": config.BASE_URL,
                "Referer": f"{config.BASE_URL}/",
                "Authorization": f"Bearer {bearer_token}",
            }
        )

    def execute(self, operation: str, query: str, variables: dict) -> dict:
        payload = {"operationName": operation, "query": query, "variables": variables}
        last_error: Exception | None = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                resp = self.session.post(
                    config.GRAPHQL_URL,
                    json=payload,
                    timeout=config.REQUEST_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                body = resp.json()
                if body.get("errors"):
                    raise RuntimeError(body["errors"])
                return body["data"]
            except Exception as exc:  # noqa: BLE001 - retried below
                last_error = exc
                wait = config.REQUEST_DELAY_SECONDS * attempt
                log.warning(
                    "GraphQL %s attempt %d/%d failed: %s (retry in %.1fs)",
                    operation, attempt, config.MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
        raise RuntimeError(f"GraphQL {operation} failed: {last_error}")


def _lot_url(auction: AuctionRef, lot_slug: str | None, lot_id: str) -> str:
    if lot_slug:
        return f"{config.BASE_URL}/en/buy/auction/{auction.year}/{auction.slug}/{lot_slug}"
    return f"{config.BASE_URL}/en/buy/auction/{auction.year}/{auction.slug}?lotId={lot_id}"


def _parse_lot(raw: dict, auction: AuctionRef, auction_title: str) -> Lot:
    estimate = raw.get("estimateV2") or {}
    low = (estimate.get("lowEstimate") or {}).get("amount", "") or ""
    high = (estimate.get("highEstimate") or {}).get("amount", "") or ""

    sold_block = (raw.get("bidState") or {}).get("sold") or {}
    sold_flag = ""
    hammer = ""
    if sold_block.get("__typename") == "ResultVisible":
        sold_flag = "yes" if sold_block.get("isSold") else "no"
        final = ((sold_block.get("premiums") or {}).get("finalPrice")) or {}
        hammer = final.get("amount", "") or ""
    elif sold_block.get("__typename") == "ResultHidden":
        sold_flag = "hidden"

    lot_number = (raw.get("lotNumber") or {}).get("lotDisplayNumber", "") or ""
    currency = (raw.get("auction") or {}).get("currency", "") or ""

    return Lot(
        auction_title=auction_title,
        auction_year=auction.year,
        auction_slug=auction.slug,
        lot_number=lot_number,
        title=raw.get("title", "") or "",
        artist=raw.get("creatorsDisplayTitle", "") or "",
        url=_lot_url(auction, (raw.get("slug") or {}).get("lotSlug"), raw.get("lotId", "")),
        currency=currency,
        low_estimate=low,
        high_estimate=high,
        sold=sold_flag,
        hammer_price=hammer,
    )


def scrape_auction_lots(client: GraphQLClient, auction: AuctionRef) -> list[Lot]:
    """Resolve an auction and page through all of its lots."""
    meta = client.execute(
        "AuctionIdBySlug",
        AUCTION_ID_QUERY,
        {"name": auction.slug, "year": auction.year},
    )
    auction_obj = meta.get("auction")
    if not auction_obj:
        log.warning("Could not resolve auction %s", auction.url)
        return []

    auction_id = auction_obj["auctionId"]
    auction_title = auction_obj.get("title") or auction.title

    lots: list[Lot] = []
    offset = 0
    while True:
        data = client.execute(
            "LotCardsFilterByPaginated",
            LOT_CARDS_QUERY,
            {
                "id": auction_id,
                "filter": "ALL",
                "language": "ENGLISH",
                "limit": config.LOTS_PAGE_SIZE,
                "offset": offset,
            },
        )
        connection = ((data.get("auction") or {}).get("lotCards")) or {}
        raw_lots = connection.get("lots") or []
        for raw in raw_lots:
            lots.append(_parse_lot(raw, auction, auction_title))

        total = connection.get("totalCount", len(lots))
        log.info("    %s: %d/%s lots", auction.slug, len(lots), total)

        if not connection.get("hasNextPage") or not raw_lots:
            break
        offset += config.LOTS_PAGE_SIZE
        time.sleep(config.REQUEST_DELAY_SECONDS)

    return lots

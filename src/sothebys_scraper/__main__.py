"""CLI entrypoint: python -m sothebys_scraper [options]."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import auth, config
from .auctions import discover_auctions
from .exporter import write_csv
from .lots import GraphQLClient, scrape_auction_lots


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sothebys_scraper",
        description="Scrape Sotheby's past-auction results (lot URLs + prices) to CSV.",
    )
    parser.add_argument(
        "--department",
        default="impressionist-modern-art",
        choices=sorted(config.DEPARTMENT_FACETS) + ["all"],
        help="Department filter for the results listing (default: impressionist-modern-art)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max results-listing pages to walk (default: all)",
    )
    parser.add_argument(
        "--max-auctions",
        type=int,
        default=None,
        help="Stop after scraping this many auctions (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV output path (default: data/sothebys_lots_<timestamp>.csv)",
    )
    parser.add_argument(
        "--no-login",
        action="store_true",
        help="Skip login (sold prices will come back hidden)",
    )
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="Only run the manual login step and save the bearer token",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("sothebys_scraper")

    if args.login_only:
        auth.login_and_get_token()
        log.info("Login complete. Re-run without --login-only to start scraping.")
        return 0

    token = ""
    if not args.no_login:
        token = auth.login_and_get_token()

    department = None if args.department == "all" else args.department
    auctions = discover_auctions(department=department, max_pages=args.max_pages)
    if args.max_auctions is not None:
        auctions = auctions[: args.max_auctions]

    client = GraphQLClient(token)
    all_lots = []
    for index, auction in enumerate(auctions, start=1):
        log.info("[%d/%d] %s", index, len(auctions), auction.url)
        try:
            all_lots.extend(scrape_auction_lots(client, auction))
        except Exception:
            log.exception("Failed to scrape %s, continuing", auction.url)
        time.sleep(config.REQUEST_DELAY_SECONDS)

    if not all_lots:
        log.error("No lots scraped, nothing to export")
        return 1

    output = write_csv(all_lots, args.output)
    priced = sum(1 for lot in all_lots if lot.hammer_price)
    log.info(
        "Done: %d auctions, %d lots (%d with visible prices) -> %s",
        len(auctions), len(all_lots), priced, output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

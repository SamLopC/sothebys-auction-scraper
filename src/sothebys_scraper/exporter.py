"""CSV export for scraped lots."""

from __future__ import annotations

import csv
import dataclasses
import logging
from datetime import datetime
from pathlib import Path

from . import config
from .lots import Lot

log = logging.getLogger(__name__)

FIELDNAMES = [field.name for field in dataclasses.fields(Lot)]


def write_csv(lots: list[Lot], output: Path | None = None) -> Path:
    """Write lots to a timestamped CSV in data/ (or to ``output``)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if output is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = config.DATA_DIR / f"sothebys_lots_{stamp}.csv"

    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for lot in lots:
            writer.writerow(dataclasses.asdict(lot))

    log.info("Wrote %d lots -> %s", len(lots), output)
    return output

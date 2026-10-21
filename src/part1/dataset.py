import csv
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from src.part1.common import Audit, NOTE_WORD_LIMIT, OUTPUT_DIR, Row, YEARS, encoded
from src.tickers import TICKERS

FIELDS = [
    "ticker",
    "company_name",
    "sector",
    "year",
    "page_text_clean",
    "changed_from_prior",
    "theme_categories",
    "analyst_notes",
    "snapshot_url",
    "page_similarity_to_prior_year",
]


def empty_rows(ticker: str) -> list[Row]:
    return [
        dict.fromkeys(FIELDS, "")
        | {
            "ticker": ticker,
            "company_name": TICKERS[ticker]["name"],
            "sector": TICKERS[ticker]["sector"],
            "year": str(year),
        }
        for year in YEARS
    ]


def read_outputs(directory: Path = OUTPUT_DIR) -> tuple[list[Row], dict[str, Audit]]:
    csv.field_size_limit(10_000_000)
    rows: list[Row] = []
    audits: dict[str, Audit] = {}
    if (directory / "dataset.csv").exists():
        with (directory / "dataset.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    if (directory / "audit.jsonl").exists():
        for line in (directory / "audit.jsonl").read_text(encoding="utf-8").splitlines():
            audit = json.loads(line)
            audits[audit["ticker"]] = audit
    return rows, audits


@contextmanager
def _atomic_write(path: Path):
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def checkpoint(rows: list[Row], audit: Audit, directory: Path = OUTPUT_DIR) -> None:
    """Save one company, using its digest to detect interrupted file replacements."""
    if len(rows) != len(YEARS) or {int(row["year"]) for row in rows} != set(YEARS):
        raise ValueError("A company checkpoint must contain all nine years.")
    if any(len(row["analyst_notes"].split()) > NOTE_WORD_LIMIT for row in rows):
        raise ValueError(f"Analyst note exceeds {NOTE_WORD_LIMIT} words.")

    saved, audits = read_outputs(directory)
    ticker = audit["ticker"]
    previous = {row["year"]: row for row in saved if row["ticker"] == ticker}
    for row in rows:
        if row["ticker"] != ticker:
            raise ValueError("A checkpoint must contain only the selected company.")
        old = previous.get(row["year"], {})
        if old.get("page_text_clean") and not row["page_text_clean"]:
            rejected = audit.get("years", {}).get(row["year"], {}).get("text_cleanup", {})
            if rejected.get("rejected_snapshot") != old["snapshot_url"] or not rejected.get("reason"):
                raise ValueError("Refusing to erase saved text without an audited quality rejection.")
    combined = [row for row in saved if row["ticker"] != ticker] + rows
    order = list(TICKERS)
    combined.sort(key=lambda row: (order.index(row["ticker"]), row["year"]))
    audit["rows_digest"] = rows_digest(rows)
    audits[ticker] = audit
    directory.mkdir(parents=True, exist_ok=True)

    # Write the audit first; an interrupted CSV replacement leaves a digest mismatch.
    with _atomic_write(directory / "audit.jsonl") as stream:
        stream.write("\n".join(encoded(item) for item in audits.values()) + "\n")
    with _atomic_write(directory / "dataset.csv") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(combined)


def rows_digest(rows: list[Row]) -> str:
    """Hash the CSV fields in row order to check checkpoint consistency."""
    return hashlib.sha256(
        encoded([{key: row[key] for key in FIELDS} for row in rows]).encode()
    ).hexdigest()

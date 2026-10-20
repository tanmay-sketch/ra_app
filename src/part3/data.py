"""Validate the existing measures and preserve the complete company-year roster."""

import csv
from datetime import date, datetime
import hashlib
import json
from math import isfinite
from pathlib import Path
import re

from src.part2.common import THEMES as SHARED_THEMES
from src.tickers import TICKERS

ROOT = Path(__file__).resolve().parents[2]
THEMES = tuple(SHARED_THEMES)
YEARS = range(2016, 2025)
IDENTITY = {'ticker', 'company_name', 'sector', 'year'}


def _file_info(path, **details):
    try:
        name = str(path.relative_to(ROOT))
    except ValueError:
        name = str(path)
    return {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), **details}


def _read_csv(path, required):
    csv.field_size_limit(50_000_000)
    rows = {}
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        missing = (IDENTITY | required) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f'{path.name}: missing columns {sorted(missing)}')
        for row in reader:
            ticker = row['ticker']
            try:
                year = int(row['year'])
            except (TypeError, ValueError) as error:
                raise ValueError(f'{path.name}: invalid year {row["year"]!r}') from error
            if ticker not in TICKERS or year not in YEARS:
                raise ValueError(f'{path.name}: unknown company-year {ticker} {year}')
            company = TICKERS[ticker]
            if row['company_name'] != company['name'] or row['sector'] != company['sector']:
                raise ValueError(f'{path.name}: inconsistent company identity for {ticker}')
            key = ticker, year
            if key in rows:
                raise ValueError(f'{path.name}: duplicate company-year {ticker} {year}')
            rows[key] = row
    return rows


def _measure(raw, kind, key):
    if not raw or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{key}: invalid {kind} JSON') from error
    if kind == 'themes':
        if (not isinstance(value, list) or any(not isinstance(theme, str) for theme in value)
                or len(value) != len(set(value)) or set(value) - set(THEMES)):
            raise ValueError(f'{key}: themes must be a unique list of known labels')
        return tuple(value)
    if not isinstance(value, dict) or set(value) != set(THEMES):
        raise ValueError(f'{key}: theme shares must contain exactly the ten shared themes')
    if any(isinstance(share, bool) or not isinstance(share, (int, float))
           or not isfinite(share) or not 0 <= share <= 1 for share in value.values()):
        raise ValueError(f'{key}: theme shares must be finite numbers between zero and one')
    return {theme: float(value[theme]) for theme in THEMES}


def _audit(path):
    """Audits enrich quality checks; the supplied CSV measures remain sufficient."""
    if not path.exists():
        return {}, {'available': False}
    records = {}
    try:
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    for year, detail in record.get('years', {}).items():
                        records[record['ticker'], int(year)] = detail
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}, _file_info(path, available=False, reason='Unreadable review evidence')
    return records, _file_info(path, available=True)


def _snapshot_date(url):
    match = re.search(r'/web/(\d{14})', url or '')
    if match:
        try:
            return datetime.strptime(match[1], '%Y%m%d%H%M%S').date().isoformat()
        except ValueError:
            pass
    return None


def load_inputs(part1_path, part2_path):
    """Return 450 validated observations and hashes, without changing source files."""
    part1_path, part2_path = Path(part1_path).resolve(), Path(part2_path).resolve()
    first = _read_csv(part1_path, {'page_text_clean', 'theme_categories'})
    second = _read_csv(part2_path, {'text_file', 'theme_shares'})
    audit1, info1 = _audit(part1_path.parent / 'audit.jsonl')
    audit2, info2 = _audit(part2_path.parent / 'audit.jsonl')
    observations = []
    for ticker, company in TICKERS.items():
        for year in YEARS:
            key = ticker, year
            p1, p2 = first.get(key, {}), second.get(key, {})
            stated = _measure(p1.get('theme_categories'), 'themes', key)
            shares = _measure(p2.get('theme_shares'), 'shares', key)
            available1 = stated is not None and bool(p1.get('page_text_clean', '').strip())
            available2 = shares is not None and bool(p2.get('text_file', '').strip())
            flags = []
            if stated is not None and not available1:
                flags.append('part1_text_missing')
            if shares is not None and not available2:
                flags.append('part2_text_reference_missing')
            if not available1:
                stated = None
            if not available2:
                shares = None

            review1, review2 = audit1.get(key, {}), audit2.get(key, {})
            warning = False
            if available1:
                analysis = review1.get('analysis', {})
                text_hash = hashlib.sha256(p1['page_text_clean'].encode()).hexdigest()
                if not analysis.get('assessment_complete') or analysis.get('text_key') != text_hash:
                    flags.append('part1_review_evidence_unavailable')
                if review1.get('extraction', {}).get('quality_issues'):
                    flags.append('part1_extraction_warning')
                    warning = True
            if available2:
                extraction = review2.get('extraction', {})
                # Removing shareholder proposals is an intended filter, not an extraction failure.
                issues = [issue for issue in extraction.get('quality_issues', [])
                          if not re.fullmatch(r'Excluded \d+ words in shareholder proposals; '
                                              r'issuer responses retained when identified\.', issue)]
                if 'Extraction review:' in p2.get('analyst_notes', '') or issues:
                    flags.append('part2_extraction_warning')
                    warning = True
                if not review2.get('analysis') or not extraction:
                    flags.append('part2_review_evidence_unavailable')

            snapshot = _snapshot_date(p1.get('snapshot_url'))
            filing = p2.get('filing_date', '').strip() or None
            if filing:
                try:
                    date.fromisoformat(filing)
                except ValueError as error:
                    raise ValueError(f'{key}: invalid filing date {filing!r}') from error
            if available1 and snapshot is None:
                flags.append('snapshot_date_unavailable')
            if available2 and filing is None:
                flags.append('filing_date_unavailable')
            if available1 and available2 and snapshot and filing and snapshot > filing:
                flags.append('statement_after_proxy')

            text_path = None
            if available2:
                candidate = (part2_path.parent / p2['text_file']).resolve()
                if candidate.is_relative_to(part2_path.parent) and candidate.is_file():
                    text_path = str(candidate)
                else:
                    flags.append('part2_review_text_unavailable')
            observations.append({
                'ticker': ticker, 'company_name': company['name'], 'sector': company['sector'],
                'year': year, 'stated': stated, 'shares': shares,
                'part1_available': available1, 'part2_available': available2,
                'flags': flags, 'extraction_warning': warning, 'part1': p1, 'part2': p2,
                'snapshot_date': snapshot, 'filing_date': filing, 'text_path': text_path,
            })
    provenance = {
        'method': 'oai-company-v2', 'years': list(YEARS), 'themes': list(THEMES),
        'inputs': {'part1': _file_info(part1_path, row_count=len(first)),
                   'part2': _file_info(part2_path, row_count=len(second)),
                   'roster': _file_info(ROOT / 'src' / 'tickers.py')},
        'review_evidence': {'part1': info1, 'part2': info2},
    }
    return observations, provenance

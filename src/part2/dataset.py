"""Compact company-year CSV, separate text files and source/evidence metadata."""

import csv
import io
import json
import shutil
from pathlib import Path

from src.part2.common import (
    OUTPUT_DIR, WORK_DIR, YEARS, atomic_json, atomic_text, digest, encoded, word_count,
)
from src.tickers import TICKERS

FIELDS = [
    'ticker', 'company_name', 'sector', 'year', 'filing_date', 'meeting_date',
    'accession', 'source_url', 'text_file', 'theme_shares', 'tone_rates',
    'similarity_to_prior', 'analyst_notes',
]


def empty_rows() -> list[dict]:
    """Keep every roster company-year present, including collection gaps."""
    return [dict.fromkeys(FIELDS, '') | {
        'ticker': ticker, 'company_name': company['name'], 'sector': company['sector'],
        'year': str(year), 'analyst_notes': 'Not yet collected.',
    } for ticker, company in TICKERS.items() for year in YEARS]


def text_path(row: dict, directory: Path = OUTPUT_DIR) -> Path:
    path = (directory / row['text_file']).resolve()
    if not row['text_file'] or not path.is_relative_to(directory.resolve() / 'text'):
        raise ValueError('Expected a text_file inside outputs/text/.')
    return path


def read_document(row: dict, audit: dict, directory: Path = OUTPUT_DIR) -> dict:
    """Verify saved text and rebuild its paragraphs from audit offsets."""
    detail = audit.get('years', {}).get(str(row['year']), {})
    metadata = detail.get('extraction', {})
    text = text_path(row, directory).read_text(encoding='utf-8')
    if digest(text) != metadata.get('text_sha256'):
        raise ValueError(f'{row["ticker"]} {row["year"]}: clean text checksum mismatch.')
    paragraphs = [p | {'text': text[p['start']:p['end']]} for p in metadata['paragraphs']]
    return metadata | {'text': text, 'paragraphs': paragraphs}


def store_document(row: dict, audit: dict, extraction: dict, source: dict,
                   content: bytes | None = None, directory: Path = OUTPUT_DIR,
                   *, review: dict | None = None) -> None:
    """Retain an accepted source; require a recorded review to correct its text."""
    text = extraction['text']
    if not text.strip():
        raise ValueError('Cannot accept an empty document.')
    if row['text_file']:
        old = read_document(row, audit, directory)
        if any(str(source.get(k, '')) != row[k] for k in (
                'source_url', 'accession', 'filing_date', 'meeting_date')):
            raise ValueError('Refusing to replace an accepted document.')
        if old['text'] == text:
            return
        if not review or not review.get('reason') or review.get('previous_text_sha256') != digest(old['text']):
            raise ValueError('Text correction requires a source review matching the previous checksum.')
    # Offsets preserve paragraph evidence without copying full text into the audit.
    paragraphs, cursor = [], 0
    for paragraph in extraction['paragraphs']:
        start = text.find(paragraph['text'], cursor)
        if start < cursor:
            raise ValueError('Paragraphs do not match the saved clean text.')
        cursor = start + len(paragraph['text'])
        paragraphs.append(
            {k: v for k, v in paragraph.items() if k != 'text'} |
            {'start': start, 'end': cursor}
        )
    if sum(p.get('words', 0) for p in paragraphs) != word_count(text):
        raise ValueError('Paragraph word counts do not cover the clean text.')
    source = source.copy()
    url = source['source_url']
    raw_path = WORK_DIR / 'documents' / f'{digest(url)}.bin'
    if content is not None:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if raw_path.exists() and digest(raw_path.read_bytes()) != digest(content):
            raise ValueError('Cached source changed; review before replacing it.')
        if not raw_path.exists():
            temporary = raw_path.with_suffix('.tmp')
            temporary.write_bytes(content)
            temporary.replace(raw_path)
        source['document_sha256'] = digest(content)
        atomic_json(raw_path.with_suffix('.json'), {'url': url, 'sha256': digest(content)})
    if raw_path.exists():
        actual = digest(raw_path.read_bytes())
        if source.get('document_sha256') and source['document_sha256'] != actual:
            raise ValueError('Original source checksum mismatch.')
        source['document_sha256'] = actual
        source['raw_file'] = str(raw_path.relative_to(OUTPUT_DIR.parents[1]))
    # Keep earlier text intact until a corrected version is fully checkpointed.
    relative = f'text/{row["ticker"]}/{row["year"]}-{digest(text)[:12]}.txt'
    atomic_text(directory / relative, text)
    metadata = {k: v for k, v in extraction.items()
                if k not in {'text', 'identity_text', 'paragraphs'}}
    metadata.update(paragraphs=paragraphs, text_sha256=digest(text), words=word_count(text))
    detail = audit.setdefault('years', {}).setdefault(str(row['year']), {})
    detail.update(source=source, extraction=metadata)
    if review:
        detail['source_review'] = review
        detail.pop('analysis', None)
    for field in ('filing_date', 'meeting_date', 'accession', 'source_url'):
        row[field] = str(source.get(field) or extraction.get(field) or '')
    row.update(text_file=relative, analyst_notes='Analysis pending.',
               theme_shares='', tone_rates='', similarity_to_prior='')


def _migrate(saved: dict, legacy: dict, directory: Path) -> tuple[list, dict]:
    """Upgrade the earlier embedded-text CSV once, keeping its original files."""
    backup = WORK_DIR / 'legacy-v1' if directory == OUTPUT_DIR else directory / '.legacy-v1'
    backup.mkdir(parents=True, exist_ok=True)
    for name in ('dataset.csv', 'audit.jsonl'):
        if (directory / name).exists() and not (backup / name).exists():
            shutil.copy2(directory / name, backup / name)
    rows, audits = empty_rows(), {t: {'ticker': t, 'years': {}} for t in TICKERS}
    for row in rows:
        old = saved.get((row['ticker'], row['year']), {})
        detail = legacy.get(row['ticker'], {}).get('years', {}).get(row['year'], {})
        collection = detail.get('collection', {})
        if collection.get('attempts'):
            audits[row['ticker']]['years'][row['year']] = {
                'collection': {'attempts': collection['attempts'][-3:]},
            }
        if not old.get('document_text_clean'):
            row['analyst_notes'] = old.get('gap_reason') or old.get('analyst_notes') or row['analyst_notes']
            continue
        extraction = detail.get('extraction', {})
        if extraction.get('text') != old['document_text_clean']:
            raise ValueError('Legacy CSV and source audit disagree; migration stopped.')
        source = {k: old.get(k, '') for k in (
            'filing_date', 'meeting_date', 'accession', 'source_url', 'cik',
            'document_sha256', 'extraction_method',
        )} | {'collection_method': 'legacy SEC submissions lookup; source preserved'}
        store_document(row, audits[row['ticker']], extraction, source, directory=directory)
        if detail.get('source_review'):
            audits[row['ticker']]['years'][row['year']]['source_review'] = detail['source_review']
    checkpoint(rows, audits, directory, previous=empty_rows())
    return rows, audits


def read_outputs(directory: Path = OUTPUT_DIR) -> tuple[list[dict], dict]:
    """Resume saved results against the fixed company-year roster."""
    csv.field_size_limit(50_000_000)
    saved, audits = {}, {}
    if (path := directory / 'dataset.csv').exists():
        with path.open(newline='', encoding='utf-8') as stream:
            for row in csv.DictReader(stream):
                key = row['ticker'], row['year']
                if key in saved:
                    raise ValueError(f'Duplicate company-year: {key}.')
                saved[key] = row
    if (path := directory / 'audit.jsonl').exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            item = json.loads(line)
            if item['ticker'] in audits:
                raise ValueError('Duplicate company audit.')
            audits[item['ticker']] = item
    if saved and 'document_text_clean' in next(iter(saved.values())):
        return _migrate(saved, audits, directory)
    # Audit is written first; its row snapshot recovers an interrupted CSV replacement.
    for ticker, audit in audits.items():
        records = audit.get('records')
        if records is not None:
            expected = {(ticker, str(year)) for year in YEARS}
            if {(r['ticker'], r['year']) for r in records} != expected or len(records) != len(YEARS):
                raise ValueError('Invalid checkpoint row snapshot.')
            saved.update({(r['ticker'], r['year']): r for r in records})
    rows = []
    for row in empty_rows():
        rows.append(row | saved.pop((row['ticker'], row['year']), {}))
    if saved:
        raise ValueError('Dataset contains company-years outside the roster.')
    for ticker in TICKERS:
        audits.setdefault(ticker, {'ticker': ticker, 'years': {}})
    for row in rows:
        if row['text_file']:
            read_document(row, audits[row['ticker']], directory)
    return rows, audits


def checkpoint(rows: list[dict], audits: dict, directory: Path = OUTPUT_DIR,
               *, previous: list[dict] | None = None) -> None:
    """Validate retained sources, then save the recoverable audit before the CSV."""
    expected = [(r['ticker'], r['year']) for r in empty_rows()]
    if [(r['ticker'], r['year']) for r in rows] != expected:
        raise ValueError('Expected exactly the 450 roster company-years in order.')
    if previous is not None:
        for old, row in zip(previous, rows, strict=True):
            if old['text_file']:
                if any(old[k] != row[k] for k in ('source_url', 'accession', 'filing_date', 'meeting_date')):
                    raise ValueError('Refusing to erase or replace an accepted source.')
                if old['text_file'] != row['text_file']:
                    review = audits[row['ticker']]['years'].get(row['year'], {}).get('source_review', {})
                    if (
                        not row['text_file'] or not review.get('reason') or
                        review.get('previous_text_sha256') != digest(text_path(old, directory).read_bytes())
                    ):
                        raise ValueError('Refusing to erase or replace accepted text without a source review.')
    for row in rows:
        if row['text_file'] and not text_path(row, directory).is_file():
            raise ValueError(f'Missing clean text: {row["text_file"]}')
    directory.mkdir(parents=True, exist_ok=True)
    for ticker, audit in audits.items():
        audit['records'] = [{key: r.get(key, '') for key in FIELDS} for r in rows if r['ticker'] == ticker]
    atomic_text(directory / 'audit.jsonl', ''.join(encoded(audits[t]) + '\n' for t in TICKERS))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows({key: row.get(key, '') for key in FIELDS} for row in rows)
    atomic_text(directory / 'dataset.csv', stream.getvalue())

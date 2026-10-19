"""Collect Part 1. Omit tickers to resume; explicit tickers retry saved gaps."""

import argparse
from datetime import datetime, timezone

from src.part1.common import (ANALYSIS_METHOD, CATEGORIES, DISCOVERY_BACKEND, EMBED_MODEL,
                              EXTRACTOR_METHOD, MODEL, YEARS, ArchiveRateLimited,
                              ArchiveUnavailable, ServiceUnavailable, close_archive, diagnostic)
from src.part1.dataset import checkpoint, empty_rows, read_outputs, rows_digest
from src.part1.detect_changes import analyze
from src.part1.discover import discover
from src.part1.parse import clean_saved_rows, parse
from src.tickers import TICKERS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tickers', nargs='*', type=str.upper,
                        help='Process these companies, retrying any saved gaps.')
    args = parser.parse_args()
    tickers = list(dict.fromkeys(args.tickers or TICKERS))
    if unknown := set(tickers) - TICKERS.keys():
        parser.error('Unknown tickers: ' + ', '.join(sorted(unknown)))
    saved, audits = read_outputs()
    settings = {'analysis_model': MODEL, 'embedding_model': EMBED_MODEL,
                'discovery_method': DISCOVERY_BACKEND, 'extractor_method': EXTRACTOR_METHOD,
                'analysis_method': ANALYSIS_METHOD, 'categories': CATEGORIES}

    for ticker in tickers:
        rows = [row for row in saved if row['ticker'] == ticker] or empty_rows(ticker)
        audit = audits.get(ticker, {'ticker': ticker, 'years': {}})
        if (not args.tickers and audit.get('status') in {'complete', 'complete_with_gaps'}
                and audit.get('settings') == settings
                and audit.get('rows_digest') == rows_digest(rows)):
            print(f'{ticker}: processed; pass its ticker explicitly to retry gaps.', flush=True)
            continue

        print(f'\n{ticker} — {TICKERS[ticker]["name"]}', flush=True)
        discovery_changed = audit.get('settings', {}).get('discovery_method') != DISCOVERY_BACKEND
        audit.update(status='running', settings=settings,
                     updated_at=datetime.now(timezone.utc).isoformat())
        audit.pop('error', None)
        stop = False
        collection_failed = False

        def save() -> None:
            checkpoint(rows, audit)

        try:
            if clean_saved_rows(rows, audit):
                save()
            if args.tickers or discovery_changed:
                for row in rows:
                    detail = audit['years'].get(row['year'], {})
                    if not row['page_text_clean'] and detail.get('status') == 'gap':
                        detail['status'] = 'pending'
                        row['analyst_notes'] = ''
            if any(not row['page_text_clean']
                   and audit['years'].get(row['year'], {}).get('status') != 'gap' for row in rows):
                try:
                    page = discover(ticker, audit, save)
                    parse(ticker, page, rows, audit, save)
                except ArchiveRateLimited:
                    raise
                except (ArchiveUnavailable, ValueError) as error:
                    collection_failed = True
                    audit['error'] = str(error)
                    print(f'{ticker}: {error} Analyzing saved text.', flush=True)
            analyze(ticker, rows, audit, save)
            failed_analysis = any(detail.get('status') == 'analysis_failed'
                                  or detail.get('similarity_error')
                                  for detail in audit['years'].values())
            pending_collection = any(not row['page_text_clean']
                                     and audit['years'].get(row['year'], {}).get('status') != 'gap'
                                     for row in rows)
            audit['status'] = ('retryable' if collection_failed or pending_collection or failed_analysis else
                               'complete_with_gaps' if any(not row['page_text_clean'] for row in rows)
                               else 'complete')
        except (ArchiveRateLimited, ServiceUnavailable) as error:
            audit.update(status='retryable', error=str(error))
            stop = True
            print(f'{ticker}: {error} Progress saved; rerun later.', flush=True)
        except (ArchiveUnavailable, ValueError) as error:
            audit.update(status='retryable', error=str(error))
            print(f'{ticker}: {error} Continuing with the next company.', flush=True)
        except KeyboardInterrupt:
            audit.update(status='interrupted', error='Keyboard interrupt')
            stop = True
        except Exception as error:
            audit.update(status='failed', error=f'{type(error).__name__}: {error}')
            stop = True
            print(f'{ticker}: {audit["error"]}', flush=True)
        finally:
            for row in rows:
                if not row['analyst_notes']:
                    row['analyst_notes'] = diagnostic(audit.get('error', 'No usable archived text recovered.'))
            save()
            close_archive()
            missing = sum(not row['page_text_clean'] for row in rows)
            unassessed = sum(bool(row['page_text_clean']) and not row['theme_categories'] for row in rows)
            usage = [value for stage, value in audit.get('usage', {}).items() if stage != 'search']
            calls = sum(value.get('calls', 0) for value in usage)
            print(f'{ticker}: saved {len(YEARS)} rows; {missing} missing text, {unassessed} awaiting analysis; '
                  f'{calls} cumulative model/embedding requests.', flush=True)
        if stop:
            break


if __name__ == '__main__':
    main()

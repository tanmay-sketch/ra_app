"""Collect annual proxies through the SEC browser and analyze saved narrative locally."""

import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re

from playwright.sync_api import Error as BrowserError

from src.part2.analyze import analyze
from src.part2.collect import SECBlocked, browser_session, collect
from src.part2.common import WORK_DIR, YEARS
from src.part2.dataset import checkpoint, read_outputs
from src.part2.report import write_report
from src.tickers import TICKERS

PILOT = ('MSFT', 'JPM', 'JNJ', 'HD', 'XOM', 'AVGO')


@contextmanager
def single_writer():
    """Prevent concurrent runs from overwriting each other's checkpoints."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with (WORK_DIR / '.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another Part 2 process is running.')
        yield


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tickers', nargs='*', type=str.upper)
    parser.add_argument('--pilot', action='store_true', help='Six companies; 2016, 2019, 2020, 2024.')
    parser.add_argument('--years', nargs='+', type=int, choices=YEARS, help='Annual-meeting years.')
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument('--collect-only', action='store_true')
    stage.add_argument('--analyze-only', action='store_true')
    parser.add_argument('--headless', action='store_true', help='Optional; visible Chromium is the default.')
    parser.add_argument('--dictionary', type=Path, default=Path(os.getenv('PART2_LM_DICTIONARY',
        str(WORK_DIR / 'Loughran-McDonald_MasterDictionary_1993-2025.csv'))))
    args = parser.parse_args()
    if args.pilot and args.tickers:
        parser.error('Use --pilot or explicit tickers.')
    tickers = list(dict.fromkeys(args.tickers or (PILOT if args.pilot else TICKERS)))
    if unknown := set(tickers) - TICKERS.keys():
        parser.error('Unknown tickers: ' + ', '.join(sorted(unknown)))
    years = args.years or ((2016, 2019, 2020, 2024) if args.pilot else YEARS)
    user_agent = os.getenv('SEC_USER_AGENT', '')
    if not args.analyze_only and not re.search(r'[^\s@]+@[^\s@]+\.[^\s@]+', user_agent):
        parser.error('Set SEC_USER_AGENT="Researcher Name contact@example.com" in .env.')

    with single_writer():
        rows, audits = read_outputs()
        # Check each save against the last committed rows to protect accepted sources.
        committed = [row.copy() for row in rows]

        def save():
            checkpoint(rows, audits, previous=committed)
            committed[:] = [row.copy() for row in rows]

        exit_code = 0
        try:
            # Open a browser only when the selected company-years still need text.
            pending = [r for r in rows if r['ticker'] in tickers and int(r['year']) in years
                       and not r['text_file']]
            if not args.analyze_only and pending:
                with browser_session(user_agent, headless=args.headless) as browser:
                    for ticker in tickers:
                        selected = [r for r in rows if r['ticker'] == ticker]
                        print(f'\n{ticker} — {TICKERS[ticker]["name"]}', flush=True)
                        collect(ticker, selected, audits[ticker], save, browser=browser,
                                user_agent=user_agent, years=years,
                                ocr_python=os.getenv('PART2_OCR_PYTHON'))
                        print(f'{ticker}: {sum(bool(r["text_file"]) for r in selected)}/9 proxies retained.', flush=True)
        except (SECBlocked, BrowserError, OSError, ValueError) as error:
            print(f'Collection paused: {error}. Progress retained.', flush=True)
            exit_code = 2
        except KeyboardInterrupt:
            print('\nInterrupted; progress retained.', flush=True)
            exit_code = 130
        finally:
            save()

        # Recompute measures for all retained text, including earlier collection runs.
        if not args.collect_only and exit_code != 130:
            print('\nAnalyzing saved narrative locally.', flush=True)
            try:
                analyze(rows, audits, save, dictionary_path=args.dictionary)
            finally:
                save()

        write_report(rows, audits)
        usable = sum(bool(r['text_file']) for r in rows)
        assessed = sum(bool(r['theme_shares']) for r in rows)
        print(f'\nPart 2: {usable}/450 with text; {assessed} with themes. '
              'Saved part2/outputs/dataset.csv.', flush=True)
        return exit_code


if __name__ == '__main__':
    raise SystemExit(main())

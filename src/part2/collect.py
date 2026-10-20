"""Find annual proxies through SEC's browser search and preserve each accepted source."""

from contextlib import contextmanager
import re
import time
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Error as BrowserError, sync_playwright

from .common import WORK_DIR, YEARS, atomic_json, digest, load_json
from .extract import extract
from src.tickers import TICKERS

SEARCH_URL = 'https://www.sec.gov/edgar/search/'
BLOCK_PAGE = re.compile(r'undeclared automated tool|request rate threshold exceeded|'
                        r'your request originates from|automated access denied', re.I)
# Study-period issuers differ from today's holding companies for these firms.
CIKS = {'META': 1326801, 'XOM': 34088, 'BLK': 1364742}
ALIASES = {'IBM': ('International Business Machines',),
           'SLB': ('Schlumberger',), 'XOM': ('Exxon Mobil',)}


class SECBlocked(RuntimeError):
    """Pause a run when SEC denies access, without cycling through more companies."""


def _sec(url):
    host = (urlsplit(url).hostname or '').lower()
    return host == 'sec.gov' or host.endswith('.sec.gov')


def _document_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'www.sec.gov'
            or not re.match(r'^/Archives/edgar/data/\d+/\d{18}/[^/]+$', parsed.path)):
        raise ValueError('Expected a primary SEC Archives document URL.')
    return url


def _cached(url):
    """Reuse original bytes only when both the URL and checksum agree."""
    path = WORK_DIR / 'documents' / f'{digest(url)}.bin'
    try:
        metadata = load_json(path.with_suffix('.json'), {})
        content = path.read_bytes()
        if metadata.get('url') == url and metadata.get('sha256') == digest(content):
            return content
    except (OSError, ValueError):
        pass
    return None


def _cache(url, content):
    _document_url(url)
    if BLOCK_PAGE.search(content[:8000].decode('utf-8', errors='ignore')):
        raise SECBlocked('SEC returned an access-block page; rerun later.')
    if len(content) < 200 or not (content.lstrip().startswith(b'%PDF-')
            or re.search(br'<(?:!doctype\s+html|html|body|div|p|table)\b', content[:8000], re.I)):
        raise ValueError('The selected document is not usable HTML or PDF.')
    path = WORK_DIR / 'documents' / f'{digest(url)}.bin'
    path.parent.mkdir(parents=True, exist_ok=True)
    # A changed response needs review before it can replace an original source.
    if path.exists() and digest(path.read_bytes()) != digest(content):
        raise ValueError('Cached source changed; review before replacing the original.')
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)
    atomic_json(path.with_suffix('.json'), {'url': url, 'sha256': digest(content)})
    return content


def _normalize(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())


def _issuer_named(ticker, result):
    identity = _normalize(result.get('identity_text', ''))
    company = TICKERS[ticker]
    names = [company['name'], company.get('former_name', ''), *ALIASES.get(ticker, ())]
    return any(_normalize(name) in identity for name in names if name)


def _issuers(ticker, filing_year):
    # Broadcom's 2018 redomiciliation split that year's filings across two CIKs.
    if ticker == 'AVGO':
        return [1649338, 1730168] if filing_year == 2018 else [1649338 if filing_year < 2018 else 1730168]
    return [CIKS.get(ticker)]


def _primary(label):
    # A primary DEF 14A has no exhibit or supplementary file-type suffix.
    return bool(re.fullmatch(r'DEF\s+14A(?:\s*\([^)]*\))?', ' '.join(label.split()), re.I))


def _hint_matches(label, ticker, cik):
    match = re.search(r'\(CIK\s+(\d+)\)', label, re.I)
    if not match:
        return False
    if cik is not None:
        return int(match.group(1)) == cik
    symbols = re.findall(r'\(([^()]*)\)', label)
    return any(ticker.replace('.', '-') in re.split(r'[,\s]+', value.upper().replace('.', '-'))
               for value in symbols)


class BrowserSession:
    """One isolated browser profile, shared across the sequential company loop."""

    def __init__(self, context):
        self.context = context
        self.page = context.pages[0] if context.pages else context.new_page()
        self.page.set_default_timeout(25000)
        self.blocked = ''
        self.last_request = 0.0
        self.capture_url = None
        self.search_key = None
        self.sources = []
        context.route('**/*', self._route)
        context.on('response', self._response)

    def _route(self, route):
        request = route.request
        if request.resource_type in {'image', 'media', 'font'}:
            route.abort()
            return
        if self.blocked and _sec(request.url):
            route.abort()
            return
        if request.url == self.capture_url:
            # Preview and Open document can request the same source twice.
            cached = _cached(request.url)
            if cached:
                route.fulfill(body=cached, content_type='application/pdf' if cached.startswith(b'%PDF-') else 'text/html')
                return
        if _sec(request.url):
            # One shared clock spaces SEC page, script and search requests.
            time.sleep(max(0.0, .3 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
        route.continue_()

    def _response(self, response):
        if not _sec(response.url):
            return
        if response.status in {403, 429}:
            # Access denials pause the run instead of consuming more candidates.
            self.blocked = f'SEC access paused (HTTP {response.status}); rerun later.'
        elif response.url == self.capture_url and response.ok:
            try:
                _cache(response.url, response.body())
            except SECBlocked as exc:
                self.blocked = str(exc)
            except (BrowserError, OSError, ValueError):
                pass

    def check(self):
        if self.blocked:
            raise SECBlocked(self.blocked)
        if BLOCK_PAGE.search(self.page.locator('body').inner_text(timeout=5000)[:8000]):
            raise SECBlocked('SEC returned an access-block page; rerun later.')

    def _search_done(self):
        self.check()
        self.page.locator('.searching-overlay').wait_for(state='hidden')
        self.check()
        self.page.wait_for_function("""() => document.querySelector('#hits a.preview-file') ||
            (document.querySelector('#no-results-grid').offsetParent !== null &&
             document.querySelector('#no-results-grid').innerText.trim())""")
        missing = self.page.locator('#no-results-grid')
        if missing.is_visible():
            message = missing.inner_text()
            if re.search(r'timed out|unexpected error|not valid', message, re.I):
                raise RuntimeError(message.strip())

    def _results_response(self, response, year):
        """Ignore autocomplete and responses for an earlier company or date range."""
        query = parse_qs(urlsplit(response.url).query)
        return ('search-index' in response.url and 'keysTyped' not in query
                and query.get('ciks', [''])[0].lstrip('0') == str(self.selected_cik)
                and query.get('startdt') == [f'{year}-01-01']
                and query.get('enddt') == [f'{year}-12-31'])

    def search(self, ticker, filing_year, cik=None, keywords='proxy'):
        key = ticker, filing_year, cik, keywords
        if self.search_key == key:
            return [source.copy() for source in self.sources]
        page = self.page
        self.search_key = None
        # A new document avoids SEC's stale hash/form state between year queries.
        page.goto('about:blank')
        response = page.goto(SEARCH_URL, wait_until='domcontentloaded')
        self.check()
        if response and not response.ok:
            raise RuntimeError(f'SEC search returned HTTP {response.status}.')
        page.locator('#show-full-search-form').click()
        page.locator('#category-select').click()
        with page.expect_response(lambda r: 'search-index' in r.url and 'keysTyped=' not in r.url):
            page.locator('#category-type-grp li[value="custom"]').click()
        # SEC automatically searches and refocuses Filing types after category changes.
        page.locator('.searching-overlay').wait_for(state='hidden')
        self.check()
        page.locator('#filing-types').fill('DEF 14A')
        page.locator('#date-range-select').evaluate("field => field.value = 'custom'")
        self._dates(filing_year)
        page.locator('#keywords').fill(keywords)
        field = page.locator('#entity-full-form')
        query = str(cik) if cik is not None else ticker.replace('.', '-')
        field.fill(query)
        field.press('End')
        # SEC's autocomplete is attached to keyup, which fill() alone does not fire.
        page.locator('table.entity-hints tr.hint').first.wait_for(state='visible')
        hints = page.locator('table.entity-hints tr.hint')
        labels = hints.evaluate_all('(rows) => rows.map(row => row.getAttribute("data"))')
        choices = [i for i, label in enumerate(labels) if _hint_matches(label, ticker, cik)]
        if len(choices) != 1:
            raise ValueError(f'Could not select one exact issuer for {ticker}; autocomplete needs review.')
        selected = labels[choices[0]]
        self.selected_cik = int(re.search(r'\(CIK\s+(\d+)\)', selected).group(1))
        with page.expect_response(lambda r: self._results_response(r, filing_year)):
            hints.nth(choices[0]).click()
        self._search_done()
        self.check()
        rows = page.locator('#hits tbody tr').evaluate_all("""rows => rows.map(row => {
            const a = row.querySelector('a.preview-file');
            return a ? {label: a.innerText, source_url: a.href,
                accession: a.getAttribute('data-adsh'),
                filing_date: row.querySelector('td.filed').innerText.trim()} : null;
        }).filter(Boolean)""")
        candidates = []
        for row in rows:
            if not _primary(row.pop('label')) or row['filing_date'][:4] != str(filing_year):
                continue
            _document_url(row['source_url'])
            cik_in_url = int(urlsplit(row['source_url']).path.split('/')[4])
            if cik_in_url != self.selected_cik:
                continue
            row['cik'] = str(self.selected_cik)
            row['collection_method'] = 'browser-search-preview-open'
            candidates.append(row)
        self.search_key = key
        self.sources = sorted(candidates, key=lambda row: (row['filing_date'], row['accession']))
        return [source.copy() for source in self.sources]

    def _dates(self, year):
        # Change both dates together; SEC otherwise searches on each field's change.
        self.page.locator('#date-from').evaluate('(field, value) => field.value = value', f'{year}-01-01')
        self.page.locator('#date-to').evaluate('(field, value) => field.value = value', f'{year}-12-31')

    def open_document(self, source):
        url = _document_url(source['source_url'])
        content = _cached(url)
        if content is not None:
            source['document_read'] = 'cached raw source'
            return content
        self.capture_url = url
        try:
            self.page.locator(f'a.preview-file[href="{url}"]').filter(
                has_text=re.compile(r'^DEF\s+14A(?:\s*\([^)]*\))?$', re.I)).first.click()
            opening = self.page.locator('#open-file')
            opening.wait_for(state='visible')
            self.page.wait_for_function('(url) => document.querySelector("#open-file").href === url', arg=url)
            with self.context.expect_page() as popup:
                opening.click()
            document = popup.value
            try:
                document.wait_for_load_state('domcontentloaded')
                self.check()
                content = _cached(url)
                if content is None:
                    raise ValueError('The browser opened the document but did not retrieve a usable source.')
                source['document_read'] = 'browser preview and Open document'
                return content
            finally:
                document.close()
        finally:
            self.capture_url = None


@contextmanager
def browser_session(user_agent, headless=False):
    """Use a project-owned profile; never attach to the user's personal browser."""
    profile = WORK_DIR / 'browser' / 'chromium'
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile), headless=headless, service_workers='block', accept_downloads=True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            browser_agent = page.evaluate('navigator.userAgent')
            context.set_extra_http_headers({'User-Agent': f'{browser_agent} {user_agent}'})
            yield BrowserSession(context)
        finally:
            context.close()


def collect(ticker, rows, audit, save, *, user_agent, years=YEARS, browser,
            retry_gaps=True, ocr_python=None):
    """Inspect at most three primary documents per missing annual-meeting year."""
    from .dataset import read_document, store_document

    year_audit = audit.setdefault('years', {})
    for row in sorted(rows, key=lambda item: int(item['year'])):
        year = int(row['year'])
        if year not in years:
            continue
        if row.get('text_file') and read_document(row, audit).get('text'):
            continue
        detail = year_audit.setdefault(str(year), {})
        if not retry_gaps and detail.get('collection', {}).get('attempts'):
            continue
        attempts, errors, tried = [], [], set()
        print(f'{ticker} {year}: checking annual proxies', flush=True)

        def candidates():
            # Re-extract saved candidates before making new browser requests.
            for prior in detail.get('collection', {}).get('attempts', []):
                if not all(prior.get(k) for k in ('source_url', 'filing_date', 'accession')):
                    continue
                if prior['filing_date'][:4] not in {str(year), str(year - 1)}:
                    continue
                try:
                    _document_url(prior['source_url'])
                    content = _cached(prior['source_url'])
                except ValueError:
                    continue
                if content is not None:
                    yield {k: prior[k] for k in ('source_url', 'filing_date', 'accession', 'cik') if k in prior} | {
                        'collection_method': 'cached SEC primary document'}
            # Dataset years follow annual meetings, which may be announced the prior year.
            for filing_year in (year, year - 1):
                for cik in _issuers(ticker, filing_year):
                    if len(tried) >= 3:
                        return
                    choices = browser.search(ticker, filing_year, cik, 'proxy')
                    if not choices:
                        choices = browser.search(ticker, filing_year, cik, '')
                    attempts.append({'filing_year': filing_year, 'cik': cik, 'primary_results': len(choices)})
                    for source in choices:
                        if len(tried) >= 3:
                            return
                        yield source

        try:
            accepted = False
            for source in candidates():
                url = source['source_url']
                if len(tried) >= 3:
                    break
                if url in tried:
                    continue
                tried.add(url)
                attempt = dict(source)
                attempts.append(attempt)
                try:
                    content = browser.open_document(source)
                    result = extract(content, url, ocr_python=ocr_python, work_dir=WORK_DIR)
                    attempt.update(annual=result.get('annual'), meeting_year=result.get('meeting_year'),
                                   quality_issues=result.get('quality_issues', []))
                    if not _issuer_named(ticker, result):
                        raise ValueError('Document issuer did not match the selected company.')
                    if result.get('annual') is not True or result.get('meeting_year') != year:
                        raise ValueError('Document did not verify this annual-meeting year.')
                    if result.get('meeting_date') and source['filing_date'] > result['meeting_date']:
                        raise ValueError('Verified meeting date precedes filing date; source needs review.')
                    if not result.get('text') or not result.get('paragraphs'):
                        raise ValueError('No usable issuer narrative remained after extraction.')
                    source.update(meeting_date=result.get('meeting_date', ''),
                                  document_sha256=digest(content))
                    store_document(row, audit, result, source, content)
                    detail['collection'] = {'attempts': attempts,
                        'selection': 'First complete primary DEF 14A with matching issuer and annual-meeting year.'}
                    accepted = True
                    print(f'{ticker} {year}: saved {result["method"]} annual proxy', flush=True)
                    save()
                    break
                except SECBlocked:
                    raise
                except (BrowserError, OSError, ValueError, RuntimeError) as exc:
                    attempt['error'] = str(exc)
                    errors.append(str(exc))
            if not accepted:
                reason = '; '.join(dict.fromkeys(errors))[:900] or 'No primary annual DEF 14A found in filing year or preceding year.'
                row['analyst_notes'] = f'Missing source: {reason}'
                detail['collection'] = {'attempts': attempts, 'gap_reason': reason}
                save()
        except SECBlocked as exc:
            row['analyst_notes'] = f'Collection paused: {exc}'
            detail['collection'] = {'attempts': attempts, 'gap_reason': str(exc)}
            save()
            raise
        except (BrowserError, OSError, ValueError, RuntimeError) as exc:
            row['analyst_notes'] = f'Collection failed: {exc}'
            detail['collection'] = {'attempts': attempts, 'gap_reason': str(exc)}
            save()
            browser.check()

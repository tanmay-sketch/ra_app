"""Find official About pages and recover their historical URL variants."""

from collections.abc import Callable
from datetime import datetime
import os
import re
from typing import NotRequired, TypedDict
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.part1.common import (ArchiveUnavailable, Audit, Capture, DISCOVERY_BACKEND,
                              MAX_CANDIDATES, MAX_CAPTURES_PER_YEAR, MODEL, YEARS,
                              ArchiveRateLimited, archive_get, archive_source, ask, encoded,
                              source_in_period)
from src.tickers import TICKERS

CDX = 'https://web.archive.org/cdx/search/cdx'
FIELDS = ['timestamp', 'original', 'statuscode', 'mimetype', 'digest']
ABOUT = re.compile(
    r"about|who.we.are|our.(company|firm|story|values|mission|purpose)|"
    r"(?:company|corporate).(?:info|overview|profile)|ethics|business.conduct|"
    r"\b(?:company|values|purpose|vision|mission|principles|credo|culture)\b|owner.?s?.manual", re.I)
EXCLUDED = re.compile(
    r'/(newsroom|news|press(?:release)?s?|blogs?|articles|(?:[a-z0-9]+-)?stories|events|products|support|docs|manuals|ownersmanual|sitemap|site-map|owners)(/|$)', re.I)
REVIEWED_ROOTS = {'abc.xyz'}

# Reviewed corporate identities keep search results grounded to official domains.
OFFICIAL_DOMAINS: dict[str, tuple[str, ...]] = {
    'MSFT': ('microsoft.com',), 'AAPL': ('apple.com',), 'NVDA': ('nvidia.com',),
    'GOOGL': ('abc.xyz',), 'META': ('about.meta.com', 'meta.com', 'about.fb.com',
                                    'newsroom.fb.com', 'about.facebook.com'),
    'AVGO': ('broadcom.com',), 'CRM': ('salesforce.com',), 'ORCL': ('oracle.com',),
    'IBM': ('ibm.com',), 'INTC': ('intel.com',),
    'BRK.B': ('berkshirehathaway.com',), 'JPM': ('jpmorganchase.com',),
    'BAC': ('bankofamerica.com',), 'WFC': ('wellsfargo.com',),
    'GS': ('goldmansachs.com',), 'MS': ('morganstanley.com',),
    'BLK': ('blackrock.com',), 'SCHW': ('aboutschwab.com', 'schwab.com'),
    'AXP': ('americanexpress.com',), 'C': ('citigroup.com', 'citi.com'),
    'LLY': ('lilly.com',), 'UNH': ('unitedhealthgroup.com',), 'JNJ': ('jnj.com',),
    'ABBV': ('abbvie.com',), 'MRK': ('merck.com',),
    'TMO': ('thermofisher.com',), 'ABT': ('abbott.com',), 'PFE': ('pfizer.com',),
    'MDT': ('medtronic.com',), 'BMY': ('bms.com',),
    'AMZN': ('aboutamazon.com',), 'TSLA': ('tesla.com',),
    'HD': ('corporate.homedepot.com', 'homedepot.com'),
    'MCD': ('corporate.mcdonalds.com', 'mcdonalds.com'),
    'NKE': ('about.nike.com', 'nike.com'),
    'SBUX': ('about.starbucks.com', 'starbucks.com'),
    'TGT': ('corporate.target.com', 'target.com'),
    'LOW': ('corporate.lowes.com', 'lowes.com'), 'TJX': ('tjx.com',),
    'F': ('corporate.ford.com', 'ford.com'),
    'XOM': ('corporate.exxonmobil.com', 'exxonmobil.com'), 'CVX': ('chevron.com',),
    'COP': ('conocophillips.com',), 'EOG': ('eogresources.com',),
    'SLB': ('slb.com',), 'MPC': ('marathonpetroleum.com',),
    'PSX': ('phillips66.com',), 'VLO': ('valero.com',),
    'OXY': ('oxy.com',), 'HAL': ('halliburton.com',),
}

# Reviewed historical sources supplement observed homepage links.
REVIEWED_PAGES = {
    'AAPL': [('https://www.apple.com/jobs/us/about.html', 'Historical Apple About and values page')],
    'NVDA': [('https://www.nvidia.com/en-us/about-nvidia/', 'About NVIDIA')],
    'AVGO': [('http://www.broadcom.com/company', 'Historical Broadcom About Us'),
             ('https://www.broadcom.com/company/about-us', 'Broadcom About Us')],
    'META': [('https://about.fb.com/company-info/', 'Facebook company information'),
             ('https://newsroom.fb.com/company-info/', 'Historical Facebook company information')],
    'CRM': [('https://www.salesforce.com/company/', 'Historical Salesforce company overview')],
    'GOOGL': [('https://abc.xyz/', 'Alphabet overview and founder statement')],
    'BRK.B': [('https://www.berkshirehathaway.com/owners.html',
               "HTML owner's manual of corporate operating principles")],
    'ORCL': [('https://www.oracle.com/corporate/', 'Oracle corporate overview')],
    'BAC': [('https://about.bankofamerica.com/en-us/who-we-are/our-company.html',
             'Historical Bank of America company overview'),
            ('https://about.bankofamerica.com/en/our-company', 'Bank of America company overview')],
    'MS': [('https://www.morganstanley.com/about-us/morgan-stanley-core-values',
            'Morgan Stanley core values')],
    'BLK': [('https://www.blackrock.com/corporate/about-us/mission-and-principles',
             'Historical BlackRock mission and principles')],
    'SCHW': [('https://www.aboutschwab.com/our-people', 'Schwab people and values')],
    'LLY': [('https://www.lilly.com/who-we-are', 'Lilly mission, vision and values')],
    'JNJ': [('http://www.jnj.com/about-jnj/jnj-credo', 'Historical Johnson & Johnson Credo')],
    'ABBV': [('https://www.abbvie.com/our-company.html', 'AbbVie company overview')],
    'ABT': [('https://www.abbott.com/about-abbott/who-we-are.html', 'Who we are at Abbott')],
    'PFE': [('https://www.pfizer.com/about', 'About Pfizer')],
    'BMY': [('https://www.bms.com/about-us/our-company/our-mission.html',
             'Bristol Myers Squibb mission, vision and values')],
    'TSLA': [('https://www.tesla.com/about', 'About Tesla')],
    'SBUX': [('https://www.starbucks.com/about-us/company-information/mission-statement',
              'Historical Starbucks mission and values')],
    'LOW': [('https://corporate.lowes.com/who-we-are', "Who we are at Lowe's")],
    'F': [('https://corporate.ford.com/company.html', 'Historical Ford company overview')],
    'EOG': [('https://www.eogresources.com/culture/',
             'Corporate culture and principles (employee-facing)')],
    'HAL': [('https://www.halliburton.com/en/sustainability/guiding-principles',
             'Halliburton corporate guiding principles')],
}


class Page(TypedDict):
    url: str
    reason: str
    captures: list[Capture] | None
    alternatives: NotRequired[list['Page']]


class SearchChoice(BaseModel):
    index: int | None = Field(default=None, ge=0)
    alternatives: list[int] = Field(default_factory=list)
    reason: str = Field(max_length=160)


def page_url(url: str) -> str:
    """Strip tracking parameters and fragments, preserving content query values."""
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Expected an absolute corporate HTTP(S) URL.')
    if parts.hostname == 'web.archive.org':
        raise ValueError('Expected the original corporate URL, not an archive URL.')
    if unquote(parts.path).lower().endswith(('.pdf', '.zip', '.jpg', '.png', '.mp4')):
        raise ValueError('Expected an HTML page.')
    tracking = {'affid', 'icell', 'icid', 'msockid', 'ncid', 'trk', 'gclid', 'fbclid',
                '_sp', 'gnav', 'lnk', 'source', 'inav', 'gclsrc', 'cid'}
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key.lower() not in tracking and not key.lower().startswith('utm_')]
    host = parts.hostname + (f':{parts.port}' if parts.port not in {None, 80, 443} else '')
    return urlunsplit((parts.scheme, host, parts.path or '/', urlencode(query), ''))


def url_key(url: str) -> tuple[str, str, str]:
    parts = urlsplit(page_url(url))
    return (parts.hostname or '').removeprefix('www.'), parts.path.rstrip('/'), parts.query


def page_identity(url: str) -> tuple[str, str, str]:
    """Identify a page across scheme, trailing-slash and default-file variants."""
    archived = re.fullmatch(
        r'https?://web\.archive\.org/web/\d{14}(?:[a-z_]+)?/(https?://.*)', url)
    host, path, query = url_key(archived[1] if archived else url)
    path = re.sub(r'/(?:default|index)(?:\.(?:html?|aspx?))?$', '', path, flags=re.I)
    return host, path.lower(), urlencode(sorted(parse_qsl(query, keep_blank_values=True)))


def official_host(ticker: str, url: str) -> bool:
    host = url_key(url)[0]
    return any(host == domain or host.endswith('.' + domain)
               for domain in OFFICIAL_DOMAINS[ticker])


def rank_links(ticker: str, links: list[dict[str, str]]) -> list[dict[str, str]]:
    """Rank official About links, excluding directories and tracking duplicates."""
    hints = {url_key(url) for url, _ in REVIEWED_PAGES.get(ticker, [])}
    found = {}
    for link in links:
        try:
            url = page_url(link['href'])
            key = url_key(url)
            host, path, _ = key
            reviewed = key in hints
            label = ' '.join(link.get('title', '').split())
            if not official_host(ticker, url):
                continue
            if not path and not reviewed and host not in REVIEWED_ROOTS and not host.startswith('about.'):
                continue
            if not reviewed and (EXCLUDED.search(path)
                                 or re.search(r'/(?:locations|offices|leadership|executives|executive-team|board-directors|reports|annual-reports|contact|legal)(/|$)', path, re.I)
                                 or re.search(r'(?:privacy|cookie|terms-of-use|dmca|proposition-65|analyst-reports)', path, re.I)
                                 or re.search(r'/(careers|jobs)(/|$)', path)
                                 or re.search(r'(^|\.)(careers|jobs|docs|developer|trailhead|news|blog|wp)\.', host)):
                continue
            if not reviewed and not ABOUT.search(f'{label} {unquote(path)}') and not host.startswith('about.'):
                continue
        except (KeyError, ValueError):
            continue
        found.setdefault(key, {'href': url, 'title': label[:200], 'body': link.get('body', '')[:400]})
    def priority(link: dict[str, str]) -> tuple[int, int]:
        path = unquote(urlsplit(link['href']).path).lower()
        label = link['title'].lower()
        if re.search(r'/(?:governance|policy)/', path):
            tier = 3
        elif re.search(r'(?:values|mission|purpose|principles|credo)', path + ' ' + label):
            tier = 0
        elif re.search(r'(?:about[-_/ ]?us|who[-_/ ]?we[-_/ ]?are|our[-_/ ]?(?:company|story)|overview)', path + ' ' + label):
            tier = 1
        elif re.fullmatch(r'/?(?:company|corporate|about)(?:\.(?:html?|aspx?))?/?', path):
            tier = 2
        else:
            tier = 3
        return tier, path.count('/')
    return sorted(found.values(), key=priority)


def extract_homepage_links(ticker: str, html: str | bytes, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    for anchor in soup.select('a[href]'):
        href = str(anchor['href']).strip()
        if not href or href.startswith('#'):
            continue
        url = urljoin(base_url, href)
        archived = re.fullmatch(r'https?://web\.archive\.org/web/\d+(?:[a-z_]+)?/(https?://.*)', url)
        links.append({'href': archived[1] if archived else url,
                      'title': str(anchor.get_text(' ', strip=True) or anchor.get('aria-label')
                                   or anchor.get('title') or '')})
    return rank_links(ticker, links)


def homepage_links(ticker: str, year: int | None = None) -> tuple[list[dict[str, str]], Audit]:
    """Read rendered homepage navigation in a separate headless browser."""
    from playwright.sync_api import Error, sync_playwright

    homepage = f'https://{OFFICIAL_DOMAINS[ticker][0]}/'
    url = f'https://web.archive.org/web/{year}0701/{homepage}' if year else homepage
    detail: Audit = {'url': url, 'mode': 'headless'}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(service_workers='block')
                context.route('**/*', lambda route: route.abort()
                              if route.request.resource_type in {'image', 'media', 'font'}
                              or year and urlsplit(route.request.url).hostname not in
                              {'web.archive.org', 'web-static.archive.org'} else route.continue_())
                view = context.new_page()
                response = view.goto(url, wait_until='domcontentloaded', timeout=20000)
                for _ in range(5):
                    impatient = view.get_by_role('link', name='Impatient?', exact=True)
                    if not year or not impatient.count():
                        break
                    destination = urljoin(view.url, impatient.get_attribute('href') or '')
                    original = archive_source(destination, year)[1]
                    if not official_host(ticker, original):
                        raise ValueError('Archived homepage redirect left the company domains.')
                    detail.setdefault('redirects', []).append(destination)
                    response = view.goto(destination, wait_until='domcontentloaded', timeout=15000)
                if year and view.get_by_role('link', name='Impatient?', exact=True).count():
                    raise ValueError('Archived homepage redirect chain exceeded five hops.')
                if response is not None and response.status == 429 and year:
                    raise ArchiveRateLimited('Archived homepage returned HTTP 429.')
                if response is None or response.status >= 400:
                    raise ValueError(f'Homepage HTTP {response.status if response else "unavailable"}.')
                try:
                    view.wait_for_function("""() => [...document.querySelectorAll('a[href]')]
                        .some(a => /about|who.we.are|our.values|our.company/i.test(a.textContent+' '+a.href))""",
                                           timeout=5000)
                    view.wait_for_load_state('networkidle', timeout=2000)
                except Error:
                    pass
                resolved = view.url
                original = archive_source(resolved, year, response.headers.get('memento-datetime'))[1] if year else resolved
                if not official_host(ticker, original):
                    raise ValueError('Homepage left the reviewed company domains.')
                detail['resolved_url'] = resolved
                links = extract_homepage_links(ticker, view.content(), resolved)
                detail['links'] = links
                return links, detail
            finally:
                browser.close()
    except (Error, ValueError) as error:
        if year:
            raise ValueError(f'Archived homepage discovery failed: {str(error)[:200]}') from error
        detail['browser_error'] = str(error)[:200]
        try:
            response = httpx.get(homepage, follow_redirects=True, timeout=15,
                                 headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            if not official_host(ticker, str(response.url)):
                raise ValueError('Homepage left the reviewed company domains.')
            links = extract_homepage_links(ticker, response.text, str(response.url))
            return links, detail | {'mode': 'static', 'resolved_url': str(response.url), 'links': links}
        except httpx.HTTPError as error:
            raise ValueError(f'Homepage discovery failed ({type(error).__name__}).') from error


def search_links(ticker: str) -> tuple[list[dict[str, str]], Audit]:
    """Search once without logging the API credential."""
    key = os.getenv('SERP_API_KEY') or os.getenv('SERPAPI_API_KEY')
    if not key:
        return [], {'status': 'unconfigured', 'reason': 'SERP_API_KEY is not set.'}
    query = f'site:{OFFICIAL_DOMAINS[ticker][0]} about'
    metadata: Audit = {'provider': 'serpapi', 'query': query}
    try:
        response = httpx.get('https://serpapi.com/search.json', params={
            'engine': 'google', 'q': query, 'hl': 'en', 'gl': 'us', 'api_key': key}, timeout=25)
        if response.status_code != 200:
            return [], metadata | {'status': 'failed', 'reason': f'Search HTTP {response.status_code}.'}
        data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return [], metadata | {'status': 'failed', 'reason': f'Search failed ({type(error).__name__}).'}
    if not isinstance(data, dict) or data.get('error'):
        return [], metadata | {'status': 'failed', 'reason': 'Search provider returned an error.'}
    returned_query = (data.get('search_parameters') or {}).get('q')
    if returned_query:
        metadata['returned_query'] = returned_query
        if returned_query != query:
            return [], metadata | {'status': 'failed', 'reason': 'Search provider returned a different query.'}
    links = [{'href': item['link'], 'title': item.get('title', ''), 'body': item.get('snippet', '')}
             for item in data.get('organic_results', [])
             if isinstance(item, dict) and isinstance(item.get('link'), str)]
    return rank_links(ticker, links), metadata | {'status': 'ok', 'results': links}


def discover(ticker: str, audit: Audit, save: Callable[[], None]) -> Page | None:
    """Inspect current navigation and keep alternatives for missing historical years."""
    previous = audit.get('source_discovery', {})
    years = audit.get('years', {})
    needed = {year for year in YEARS if years.get(str(year), {}).get('status')
              not in {'extracted', 'analyzed', 'analysis_failed'}}
    hints = [{'href': url, 'title': label, 'body': 'Reviewed source hint'}
             for url, label in REVIEWED_PAGES.get(ticker, [])]
    hints += [{'href': detail['candidate_url'], 'title': 'Previously accepted About page'}
              for detail in years.values() if detail.get('candidate_url')]
    hints += [{'href': item['href'], 'title': item.get('title', '')}
              for item in previous.get('choices', []) if item.get('href')]
    entry: Audit = {'backend': DISCOVERY_BACKEND, 'homepages': [], 'choices': []}
    audit['source_discovery'] = entry
    audit['discovery'] = []
    print(f'{ticker}: looking for About pages in headless homepage navigation', flush=True)
    try:
        links, detail = homepage_links(ticker)
        entry['homepages'].append(detail)
    except ValueError as error:
        links = []
        entry['homepages'].append({'error': str(error)})
    if not links:
        links, entry['search'] = search_links(ticker)
        if entry['search'].get('status') != 'unconfigured':
            audit.setdefault('usage', {}).setdefault('search', {'calls': 0})['calls'] += 1
    pool = rank_links(ticker, links + hints)
    indexed: dict[tuple[str, str, str], list[Capture]] = {}
    errors = []

    def check(candidates: list[dict[str, str]]) -> None:
        for candidate in candidates:
            key = page_identity(candidate['href'])
            if key in indexed:
                continue
            record: Audit = dict(candidate)
            entry['choices'].append(record)
            try:
                captures = [capture for capture in index(candidate['href'])
                            if source_in_period(ticker, capture['original'], capture['timestamp'])]
                indexed[key] = captures
                record.update(years=[year for year in YEARS if sample(captures, year)],
                              indexed_captures=len(captures))
            except ArchiveRateLimited:
                raise
            except (ArchiveUnavailable, ValueError) as error:
                record['index_error'] = str(error)
                errors.append(error)
                indexed[key] = []
            save()

    check(pool[:MAX_CANDIDATES])
    covered = {year for record in entry['choices'] for year in record.get('years', [])}
    missing = sorted(needed - covered)
    # Two historical homepages can reveal paths removed from today's navigation.
    for year in dict.fromkeys([missing[-1], missing[0]] if missing else []):
        if needed <= {year for record in entry['choices'] for year in record.get('years', [])}:
            break
        try:
            historical, detail = homepage_links(ticker, year)
            entry['homepages'].append(detail)
            check(rank_links(ticker, historical)[:MAX_CANDIDATES])
        except ArchiveRateLimited:
            raise
        except ValueError as error:
            entry['homepages'].append({'year': year, 'error': str(error)})
        save()
    choices = [record for record in entry['choices'] if record.get('years')]
    selection: Audit = {'url': None, 'reason': 'No eligible archived About page found.'}
    if choices:
        prompt = (
            f'Select the best corporate About page for {TICKERS[ticker]["name"]}. '
            'Choose a company-wide overview, mission, purpose, values or principles page. '
            'Reject product, help, recruiting, news, leadership-only, investor-data and legal pages. '
            'Corporate culture or an owner manual explaining company-wide principles is eligible. '
            'All choices are observed official links or reviewed sources. The years field is index '
            'coverage, not proof of complete text. Prefer broad coverage, then explicit values. '
            'Other suitable URLs may be used only for missing years. Return null if none fits. '
            'List the indexes of any other eligible About pages in alternatives; omit weak matches. '
            f'LINKS (zero-based indexes): {encoded(dict(enumerate(choices)))}')
        choice = ask(prompt, SearchChoice, audit, stage='discovery_selection')
        if choice.index is not None:
            if choice.index >= len(choices):
                raise ValueError('Model selected an index outside the supplied candidate list.')
            positions = list(dict.fromkeys([choice.index, *choice.alternatives]))
            if any(position < 0 or position >= len(choices) for position in positions):
                raise ValueError('Model selected an alternative outside the supplied list.')
            choices = [choices[position] for position in positions]
            selected = choices[0]
            selection['url'] = selected['href']
        selection.update(reason=choice.reason, model=MODEL)
    entry['selection'] = selection
    save()
    if not selection['url']:
        if errors and not choices:
            raise ArchiveUnavailable('About candidates could not be fully indexed; retry later.')
        return None
    pages = [Page(url=record['href'], reason=selection['reason'],
                  captures=indexed[page_identity(record['href'])]) for record in choices]
    pages[0]['alternatives'] = pages[1:]
    print(f'{ticker}: retained {len(pages)} About URL(s); at most 3 total captures per year.', flush=True)
    return pages[0]


def index(url: str) -> list[Capture]:
    """One exact, bounded CDX query; redirects and non-HTML records are excluded."""
    params = {'url': page_url(url), 'matchType': 'exact', 'from': str(YEARS.start),
              'to': str(YEARS.stop - 1), 'output': 'json', 'fl': ','.join(FIELDS),
              'collapse': 'timestamp:6', 'limit': '120',
              'filter': ['statuscode:200', r'mimetype:text/html|application/xhtml\+xml']}
    print(f'CDX: {url} (one monthly index for 2016–2024)', flush=True)
    response = archive_get(CDX, params, attempts=2, timeout=20)
    if response.status_code != 200:
        raise ValueError(f'CDX HTTP {response.status_code}.')
    try:
        data = response.json()
    except ValueError as error:
        raise ValueError('Malformed CDX JSON, not an empty index.') from error
    if not isinstance(data, list) or (data and data[0] != FIELDS):
        raise ValueError('Malformed CDX response, not an empty index.')
    captures = []
    for row in data[1:]:
        if not isinstance(row, list) or len(row) != len(FIELDS):
            raise ValueError('Malformed CDX row.')
        capture = dict(zip(FIELDS, map(str, row)))
        try:
            if len(capture['timestamp']) != 14 or not capture['timestamp'].isdigit():
                raise ValueError('Expected a 14-digit timestamp.')
            datetime.strptime(capture['timestamp'], '%Y%m%d%H%M%S')
        except ValueError as error:
            raise ValueError('Malformed CDX timestamp.') from error
        captures.append(capture)
    return captures


def sample(captures: list[Capture], year: int) -> list[Capture]:
    """Try the nearest July 1 capture, then the earliest and latest that year."""
    eligible = sorted((capture for capture in captures
                       if capture['timestamp'].startswith(str(year))
                       and capture['statuscode'] == '200'
                       and capture['mimetype'] in {'text/html', 'application/xhtml+xml'}),
                      key=lambda capture: capture['timestamp'])
    if not eligible:
        return []
    target = datetime(year, 7, 1)
    middle = min(eligible, key=lambda capture: abs(
        (datetime.strptime(capture['timestamp'], '%Y%m%d%H%M%S') - target).total_seconds()))
    chosen = []
    for capture in [middle, eligible[0], eligible[-1], *eligible]:
        if capture not in chosen:
            chosen.append(capture)
        if len(chosen) == MAX_CAPTURES_PER_YEAR:
            break
    return chosen


def page_captures(page: Page, audit: Audit) -> list[Capture]:
    entry: Audit = {'url': page['url']}
    audit.setdefault('discovery', []).append(entry)
    if page['captures'] is None:
        try:
            page['captures'] = index(page['url'])
        except ValueError as error:
            entry['error'] = str(error)
            raise
    entry['sampled_by_year'] = {str(year): len(sample(page['captures'], year)) for year in YEARS}
    return page['captures']

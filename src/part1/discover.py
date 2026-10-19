"""Choose one official About page, then sample at most three captures per year."""

from collections.abc import Callable
from datetime import datetime
import os
import re
from typing import TypedDict
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.part1.common import (ArchiveUnavailable, Audit, Capture, DISCOVERY_BACKEND,
                              MAX_CANDIDATES, MAX_CAPTURES_PER_YEAR, MODEL, YEARS,
                              archive_get, ask, encoded, source_in_period)
from src.tickers import TICKERS

CDX = 'https://web.archive.org/cdx/search/cdx'
FIELDS = ['timestamp', 'original', 'statuscode', 'mimetype', 'digest']
ABOUT = re.compile(
    r"about|who.we.are|our.(company|firm|story|values|mission|purpose)|"
    r"(?:company|corporate).(?:info|overview|profile)|ethics|business.conduct|"
    r"\b(?:company|values|purpose|vision|mission|principles|credo|culture)\b|owner.?s?.manual", re.I)
EXCLUDED = re.compile(
    r'/(newsroom|news|press(?:release)?s?|blogs?|articles|events|products|support|docs|manuals|ownersmanual|sitemap|site-map|owners)(/|$)', re.I)
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

# Grounded source hints are choices for the model, never extra fallback pages.
REVIEWED_PAGES = {
    'AAPL': [('https://www.apple.com/jobs/us/about.html', 'Historical Apple About and values page')],
    'NVDA': [('https://www.nvidia.com/en-us/about-nvidia/', 'About NVIDIA')],
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


class SearchChoice(BaseModel):
    index: int | None = Field(default=None, ge=0, le=MAX_CANDIDATES - 1)
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
    """Keep observed official About-like URLs and deduplicate tracking variants."""
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
            if not reviewed and (EXCLUDED.search(path)
                                 or re.search(r'/(careers|jobs)(/|$)', path)
                                 or re.search(r'(^|\.)(careers|jobs|docs|developer|trailhead)\.', host)):
                continue
            if not reviewed and not ABOUT.search(f'{label} {unquote(path)}') and not host.startswith('about.'):
                continue
        except (KeyError, ValueError):
            continue
        found.setdefault(key, {'href': url, 'title': label[:200], 'body': link.get('body', '')[:400]})
    return list(found.values())


def extract_homepage_links(ticker: str, html: str | bytes, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, 'html.parser')
    return rank_links(ticker, [
        {'href': urljoin(base_url, str(anchor['href'])),
         'title': str(anchor.get_text(' ', strip=True) or anchor.get('aria-label') or anchor.get('title') or '')}
        for anchor in soup.select('a[href]')])


def homepage_links(ticker: str) -> tuple[list[dict[str, str]], Audit]:
    """One static homepage request, only when search supplies no candidates."""
    homepage = f'https://{OFFICIAL_DOMAINS[ticker][0]}/'
    try:
        response = httpx.get(homepage, follow_redirects=True, timeout=20,
                             headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        if not official_host(ticker, str(response.url)):
            raise ValueError('Homepage redirected outside the reviewed company domains.')
    except httpx.HTTPError as error:
        raise ValueError(f'Homepage request failed ({type(error).__name__}).') from error
    return extract_homepage_links(ticker, response.text, str(response.url)), {
        'url': homepage, 'resolved_url': str(response.url)}


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
    """Check at most three exact indexes, then select one historically usable URL."""
    entry = audit.get('source_discovery', {})
    indexed: dict[str, list[Capture]] = {}
    successful = next((detail['candidate_url']
                       for _, detail in sorted(audit.get('years', {}).items(), reverse=True)
                       if detail.get('candidate_url') and detail.get('status') in
                       {'extracted', 'analyzed', 'analysis_failed'}), None)
    if successful:
        selection = {'url': successful, 'reason': 'Reusing a previously accepted archived source.'}
        entry.update(backend=DISCOVERY_BACKEND, selection=selection)
        audit['source_discovery'] = entry
        save()
    elif entry.get('backend') == DISCOVERY_BACKEND and entry.get('selection', {}).get('url'):
        selection = entry['selection']
    else:
        print(f'{ticker}: selecting one official About page', flush=True)
        links, search = search_links(ticker)
        entry = {'backend': DISCOVERY_BACKEND, 'search': search}
        audit['source_discovery'] = entry
        if search.get('status') != 'unconfigured':
            audit.setdefault('usage', {}).setdefault('search', {'calls': 0})['calls'] += 1
        if not links and not REVIEWED_PAGES.get(ticker):
            try:
                links, entry['homepage'] = homepage_links(ticker)
            except ValueError as error:
                entry['homepage_error'] = str(error)
        hints = [{'href': url, 'title': label, 'body': 'Reviewed source hint'}
                 for url, label in REVIEWED_PAGES.get(ticker, [])]
        candidates = rank_links(ticker, hints + links)[:MAX_CANDIDATES]
        entry['choices'] = []
        choices = []
        for candidate in candidates:
            record: Audit = dict(candidate)
            entry['choices'].append(record)
            try:
                captures = [capture for capture in index(candidate['href'])
                            if source_in_period(ticker, capture['original'], capture['timestamp'])]
            except (ArchiveUnavailable, ValueError) as error:
                record['index_error'] = str(error)
                save()
                raise  # A failed index request is not evidence of missing captures.
            covered = [year for year in YEARS if sample(captures, year)]
            record.update(years=covered, indexed_captures=len(captures))
            indexed[candidate['href']] = captures
            if covered:
                choices.append(record)
            save()
            if len(covered) == len(YEARS) and candidate['body'] == 'Reviewed source hint':
                break  # A reviewed source covering every year needs no more index probes.
        selection = {'url': None, 'reason': 'No official About-equivalent candidates found.'}
        if candidates and not choices:
            selection['reason'] = 'Checked candidates have no eligible study-period captures.'
        if choices:
            prompt = (
                f'Select the single best corporate About page for {TICKERS[ticker]["name"]}. '
                'Choose a company-wide overview, mission, purpose, values, principles or story page. '
                'Reject product, help, careers/recruiting, news, leadership-only, investor-data and legal pages. '
                'A historical About page or owner manual explaining corporate principles is eligible. '
                'A corporate culture page is eligible when it states company-wide principles. '
                'Every choice is an observed official URL or a reviewed source hint. '
                'The years field lists eligible archived years, not proof of a complete page. '
                'Among suitable pages prefer the greatest number of covered study years, '
                'then explicit mission, values or principles over a generic overview or history. '
                'Return null only if none fits. '
                f'LINKS (zero-based indexes): {encoded(dict(enumerate(choices)))}')
            choice = ask(prompt, SearchChoice, audit, stage='discovery_selection')
            if choice.index is not None:
                if choice.index >= len(choices):
                    raise ValueError('Model selected an index outside the supplied candidate list.')
                selection['url'] = choices[choice.index]['href']
            selection['reason'] = choice.reason
        entry['selection'] = selection | {'model': MODEL}
        save()
    url = selection.get('url')
    audit['discovery'] = []
    if not url:
        print(f'{ticker}: {selection["reason"]} Moving on.', flush=True)
        return None
    url = page_url(url)
    if not official_host(ticker, url):
        raise ValueError('Selected source is outside the reviewed company domains.')
    print(f'{ticker}: selected {url}; at most 3 captures per year.', flush=True)
    return Page(url=url, reason=selection.get('reason', ''), captures=indexed.get(url))


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

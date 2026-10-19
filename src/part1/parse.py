"""Extract one About URL from at most three captures per company-year."""

import re
import unicodedata
from collections.abc import Callable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from trafilatura import extract
from playwright.sync_api import Error as BrowserError, Request, Response, Route, sync_playwright
from playwright.sync_api import TimeoutError as BrowserTimeoutError

from src.part1.common import (ArchiveRateLimited, Audit, Capture, CaptureUnavailable,
                              EXTRACTOR_METHOD, MAX_CAPTURES_PER_YEAR, Row, archive_source,
                              diagnostic, replay, same_corporate_host, source_in_period)
from src.part1.discover import ABOUT, EXCLUDED, REVIEWED_ROOTS, Page, page_captures, sample

# Remove only identifiable UI here; Trafilatura handles body selection and boilerplate.
BOILERPLATE = ('nav,footer,[role=navigation],[role=contentinfo],[role=dialog],'
               '[role=search],[aria-modal=true],#wm-ipp,#wm-ipp-base,#wm-ipp-print,#donato,'
               '.cookie-banner,#onetrust-banner-sdk,#onetrust-consent-sdk,'
               'script,style,noscript,svg,template,'
               'video,audio,button,input,select,textarea,[hidden],[aria-hidden=true]')
ERROR_PAGE = re.compile(
    r'\b(access denied|403 forbidden|404 not found|page not found|'
    r'brand config page only|pardon our interruption|verify (?:that )?you are human|'
    r'checking your browser|request (?:has been )?blocked|service unavailable|'
    r'internal server error|server error|something has gone wrong on our end)\b', re.I)
LINK_PROMPT = re.compile(
    r'^(?:[-•*]\s*)?(?:learn (?:more|about|how)|read (?:more|our|the)|find (?:out|information)|'
    r'for (?:the )?latest information\b|'
    r'see (?:how|our)|click |watch |connect and communicate|more\s*$|https?://)', re.I)
# Exact UI labels exclude value headings such as Safety and Integrity.
UI_LABELS = {
    'company', 'careers', 'news', 'events', 'news & events', 'corporate information',
    'industries', 'solutions', 'software', 'products', 'resources',
    'developer resources', 'application frameworks', 'top sdks and libraries',
    'apps and tools', 'use cases', 'nvidia studio', 'selected item',
    'first name', 'last name', 'email', 'phone', 'message', 'job role', 'specialty',
    'hospital or organization', 'hospital postal code', 'confirm country/region',
    'or', 'new products & technology', 'new services', 'education & training',
    'clinical information', 'customer experience surveys',
    'product & technology information', 'education & clinical information',
    'scroll down', 'asset warning',
}
FORM_MESSAGES = {
    'there are items that require your attention.',
    'just to confirm, is this the product or product type that interests you?',
    'before we get started, what best describes you?',
}
TEMPLATE_TEXT = re.compile(r'\{\{[^{}]*\}\}|\{link\}', re.I)
COOKIE_BANNER = re.compile(
    r'^(?:[\w .&-]+ websites? use[sd]? cookies to (?:deliver|improve)|'
    r'(?:we|this (?:site|website)) use[sd]? cookies to (?:improve|enhance) '
    r'(?:your (?:browsing|website) experience|our (?:site|website))|'
    r'(?:by (?:using|continuing to (?:use|browse)) (?:this|our) (?:site|website).{0,100}'
    r'(?:cookies|cookie policy))|(?:accept|reject|manage) (?:all )?cookies\b)', re.I)
COPYRIGHT = re.compile(r'^[*\s]*(?:copyright\b|©\s*(?:copyright\b|\d{4}))', re.I)
FORM_CONTACT = re.compile(r'^(?:hours:|phone:|toll-free:)', re.I)
FORM_CONSENT = re.compile(
    r'^by submitting (?:this|your) information, you agree to receive marketing emails\b', re.I)
SITE_NOTICE = re.compile(
    r'^(?:please be aware that the website (?:that )?you have requested is intended for|'
    r'the website (?:that )?you have requested (?:also )?may not be optimized for|'
    r'links which take you out of .{1,60} websites are not under the control of)\b', re.I)


class NeedsRendering(ValueError):
    """The HTML has insufficient body content; JavaScript may complete it."""


def normalized(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def clean_text(text: str) -> str:
    """Remove identifiable UI lines without rewriting or deduplicating prose."""
    lines = [normalized(line) for line in text.splitlines() if line.strip()]
    form_present = any(line.casefold() in FORM_MESSAGES for line in lines)
    cleaned = []
    for index, line in enumerate(lines):
        label = re.sub(r'^[-•*]\s*', '', line).strip().casefold()
        if (not re.search(r'\w', line) or label in UI_LABELS
                or label in FORM_MESSAGES or TEMPLATE_TEXT.search(line)
                or COPYRIGHT.search(line) or COOKIE_BANNER.search(line)
                or FORM_CONSENT.search(line) or SITE_NOTICE.search(line)):
            continue
        if form_present and (FORM_CONTACT.search(line) or label == 'customer care team'
                             or label == 'united states' and index + 1 < len(lines)
                             and lines[index + 1].casefold() == 'customer care team'):
            continue
        if LINK_PROMPT.search(line) and len(line.split()) <= 12:
            continue
        if line.casefold().startswith('get answers to all your support, sales, and partner questions'):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def unusable_reason(text: str, title: str = '') -> str:
    """Identify explicit error pages and statistics without substantive prose."""
    if ERROR_PAGE.search(title) or ERROR_PAGE.search(text[:600]):
        return 'Error page or configuration placeholder.'
    lines = text.splitlines()
    statistics = sum(bool(re.fullmatch(r'[$€£\d,.%+\s]+', line.strip())) for line in lines)
    narrative = sum(len(line.split()) for line in lines
                    if len(line.split()) >= 6 and not LINK_PROMPT.search(line.strip()))
    if statistics >= 3 and narrative < 25:
        return 'Recovered only statistics and navigation prompts.'
    return ''


def validate_text(text: str) -> None:
    """Reject incomplete captures and link-label collections."""
    if reason := unusable_reason(text):
        raise ValueError(reason)
    if len(text.split()) < 25:
        raise ValueError('Recovered too little substantive body text.')
    narrative = sum(len(line.split()) for line in text.splitlines()
                    if len(line.split()) >= 6 and not LINK_PROMPT.search(line.strip()))
    if narrative < 25:
        raise ValueError('Recovered text contains only short labels or navigation prompts.')
    if narrative < len(text.split()) * .5:
        raise ValueError('Short labels or navigation dominate the recovered text.')


def clean_saved_rows(rows: list[Row], audit: Audit) -> bool:
    """Postprocess retained text locally, keeping its original archive provenance."""
    updated = False
    by_year = {int(row['year']): row for row in rows}
    for row in rows:
        if not row['page_text_clean']:
            continue
        detail = audit['years'].setdefault(row['year'], {})
        before = row['page_text_clean']
        reason = unusable_reason(before, detail.get('extraction', {}).get('title', ''))
        current = (detail.get('extraction', {}).get('method') == EXTRACTOR_METHOD
                   or detail.get('text_cleanup', {}).get('method') == EXTRACTOR_METHOD)
        if current and not reason:
            continue
        after = clean_text(before)
        reason = reason or unusable_reason(after)
        detail['text_cleanup'] = {'method': EXTRACTOR_METHOD, 'before_words': len(before.split()),
                                  'after_words': 0 if reason else len(after.split()),
                                  'text_changed': bool(reason) or before != after}
        updated = True
        if before == after and not reason:
            continue
        if not reason:
            try:
                validate_text(after)
            except ValueError as error:
                detail['text_cleanup'].update(
                    after_words=len(before.split()), text_changed=False,
                    warning=f'Cleanup failed validation; original text retained. {error}')
                continue
        row.update(page_text_clean=after if not reason else '', theme_categories='', analyst_notes='')
        detail.pop('analysis', None)
        detail.pop('analysis_error', None)
        detail.pop('analysis_pending_method', None)
        detail['status'] = 'extracted' if not reason else 'gap'
        if reason:
            detail['text_cleanup'].update(reason=reason, rejected_snapshot=row['snapshot_url'])
            detail['reason'] = reason
            row.update(snapshot_url='', analyst_notes=diagnostic('Saved text rejected after cleanup: ' + reason))
        for affected_year in (int(row['year']), int(row['year']) + 1):
            if affected := by_year.get(affected_year):
                affected.update(changed_from_prior='', page_similarity_to_prior_year='')
                comparison = audit['years'].setdefault(str(affected_year), {})
                for key in ('comparison_texts', 'comparison_method', 'comparison_embedding_model', 'similarity_error'):
                    comparison.pop(key, None)
    return updated


def choose_parser(raw: bytes | str, url: str) -> tuple[str, Audit]:
    """Extract with Trafilatura after checking page scope and obvious error content."""
    soup = BeautifulSoup(raw, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    if EXCLUDED.search(urlsplit(url).path):
        raise ValueError('News/product/support page is outside corporate About scope.')
    host = (urlsplit(url).hostname or '').removeprefix('www.')
    # Some CMS forms wrap the whole page; remove controls while keeping prose.
    for form in list(soup.select('form')):
        if form.attrs is None:
            continue
        if form.get('role') == 'search':
            form.decompose()
        else:
            form.unwrap()
    for node in soup.select(BOILERPLATE):
        node.decompose()
    for label in soup.select('label'):
        if normalized(label.get_text(' ', strip=True)).casefold() in UI_LABELS:
            label.decompose()
    for node in soup.select('[style]'):
        if node.attrs is None:
            continue
        if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', str(node.get('style')), re.I):
            node.decompose()
    main = soup.find('main') or soup.select_one('[role=main]') or soup.find('article')
    body = main or soup.body or soup
    body_text = body.get_text(' ', strip=True)
    if ERROR_PAGE.search(title) or ERROR_PAGE.search(body_text[:600]):
        raise ValueError('Error page or configuration placeholder.')
    headings = ' '.join(h.get_text(' ', strip=True) for h in body.select('h1,h2,h3'))
    if (not ABOUT.search(title + ' ' + headings + ' ' + urlsplit(url).path)
            and not host.startswith('about.') and host not in REVIEWED_ROOTS):
        if len(body_text.split()) < 25:
            raise NeedsRendering('No substantive body or About scope in static HTML.')
        raise ValueError('No About/mission/principles scope in page title, headings or path.')
    words = len(body_text.split())
    link_words = sum(len(a.get_text(' ', strip=True).split()) for a in body.select('a'))
    link_fraction = link_words / max(words, 1)
    text = extract(str(soup), url=url, output_format='txt',
                   include_comments=False, include_tables=False, include_links=False,
                   with_metadata=False, deduplicate=False)
    extractor = 'trafilatura'
    if not text or len(text.split()) < 25:
        # Trafilatura can miss short mission pages; use a substantive main region.
        if main is not None and words >= 25 and link_fraction <= .5:
            text = main.get_text('\n', strip=True)
            extractor = 'semantic-main'
        else:
            raise NeedsRendering('Recovered too little substantive body text.')
    text = clean_text(text)
    validate_text(text)
    # Check extracted text for directories; linked prose can still be valid content.
    substantive = [line for line in text.splitlines() if len(line.split()) >= 12]
    if link_fraction > .5 and sum(len(line.split()) for line in substantive) < 25:
        raise ValueError('Directory/navigation dominates the recovered text.')
    return text, {'extractor': extractor, 'method': EXTRACTOR_METHOD, 'title': title,
                  'link_word_fraction': round(link_fraction, 3)}


def render(capture: Capture, year: int, detail: Audit) -> tuple[str, str]:
    """Try one short browser replay; accept only complete, same-year archive content."""
    url = f"https://web.archive.org/web/{capture['timestamp']}/{capture['original']}"
    resources: list[Audit] = []
    blocked: list[str] = []
    failed: list[str] = []
    pending: set[Request] = set()
    content_types = {'document', 'xhr', 'fetch'}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = None
        try:
            context = browser.new_context(service_workers='block')
            page = context.new_page()

            def content(request: Request) -> bool:
                parts = urlsplit(request.url)
                return ((request.resource_type in content_types
                         or request.resource_type == 'script' and parts.path.startswith('/web/'))
                        and not parts.path.startswith(('/__wb/', '/services/wayback-data/'))
                        and not (parts.hostname == 'archive.org' and parts.path == '/includes/donate.php')
                        and not any('prefetch' in request.headers.get(key, '') for key in ('purpose', 'sec-purpose')))

            def route_request(route: Route) -> None:
                request = route.request
                parts = urlsplit(request.url)
                if (parts.hostname == 'web-static.archive.org' and parts.path.startswith('/_static/')
                        and request.resource_type in {'script', 'stylesheet'}):
                    route.continue_()
                elif (parts.hostname != 'web.archive.org' or parts.path.startswith(
                        ('/__wb/', '/services/wayback-data/'))
                        or any('prefetch' in request.headers.get(key, '') for key in ('purpose', 'sec-purpose'))):
                    if content(request):
                        blocked.append(request.url)
                    route.abort()
                elif request.resource_type in {'image', 'media', 'font'}:
                    route.abort()
                else:
                    # Reject out-of-year content before scripts can insert it.
                    if content(request):
                        try:
                            archive_source(request.url, year)
                        except ValueError:
                            blocked.append(request.url)
                            route.abort()
                            return
                    route.continue_()

            def record(response: Response) -> None:
                if content(response.request):
                    resources.append({'url': response.url, 'status': response.status,
                                      'type': response.request.resource_type,
                                      'memento': response.headers.get('memento-datetime')})

            context.route('**/*', route_request)
            page.on('request', lambda request: pending.add(request) if content(request) else None)
            page.on('requestfinished', lambda request: pending.discard(request))
            page.on('requestfailed', lambda request: pending.discard(request))
            page.on('requestfailed', lambda request: failed.append(request.url) if content(request) else None)
            page.on('response', record)
            response = page.goto(url, wait_until='domcontentloaded', timeout=15000)
            if response is not None and response.status == 429:
                raise ArchiveRateLimited('Archive browser replay returned HTTP 429; retry after the cooldown.')
            if response is None or response.status != 200:
                raise ValueError('Browser replay did not return HTTP 200.')
            try:
                page.wait_for_load_state('networkidle', timeout=4000)
            except BrowserTimeoutError:
                pass
            memento = next((r['memento'] for r in reversed(resources)
                            if r['type'] == 'document' and r['url'] == page.url), None)
            source, original = archive_source(page.url, year, memento)
            if not same_corporate_host(original, capture['original']):
                raise ValueError('Browser redirected to an unverified corporate host.')
            if any(resource['status'] == 429 for resource in resources):
                raise ArchiveRateLimited('Archive browser content returned HTTP 429; retry after the cooldown.')
            if blocked or failed or pending:
                raise ValueError('Partial render: live, out-of-year, failed or pending content requests.')
            for resource in resources:
                if 300 <= resource['status'] < 400:
                    continue
                if resource['status'] != 200:
                    raise ValueError('Partial render: archived content request failed.')
                archive_source(resource['url'], year, resource['memento'])
            html = page.evaluate("""() => {
                const copy = document.documentElement.cloneNode(true);
                const originals = [...document.documentElement.querySelectorAll('*')];
                const clones = [...copy.querySelectorAll('*')];
                originals.forEach((node, i) => {
                    const style = getComputedStyle(node);
                    if (style.display === 'none' || style.visibility === 'hidden') clones[i]?.remove();
                });
                return copy.outerHTML;
            }""")
            return str(html), source
        except BrowserError as error:
            raise ValueError(f'Browser replay failed: {error.message[:300]}') from error
        finally:
            detail.update(resources=resources, blocked_content=blocked, failed_requests=failed,
                          pending_requests=[request.url for request in pending])
            try:
                if context is not None:
                    context.close()
            finally:
                browser.close()


def parse(ticker: str, page: Page | None, rows: list[Row], audit: Audit,
          save: Callable[[], None]) -> None:
    """Keep successful text; try three captures of one URL, then record a gap."""
    years = audit.setdefault('years', {})
    pending = [row for row in rows if not row['page_text_clean']
               and years.get(row['year'], {}).get('status') != 'gap']
    if not pending:
        return
    captures = page_captures(page, audit) if page else []
    captures = [capture for capture in captures
                if source_in_period(ticker, capture['original'], capture['timestamp'])]
    by_year = {int(row['year']): row for row in rows}
    for row in sorted(pending, key=lambda item: item['year'], reverse=True):
        year = int(row['year'])
        detail: Audit = {'status': 'pending', 'attempts': []}
        years[str(year)] = detail
        browser_tried = False
        for capture in sample(captures, year)[:MAX_CAPTURES_PER_YEAR]:
            requested = f"https://web.archive.org/web/{capture['timestamp']}id_/{capture['original']}"
            attempt: Audit = {'requested_url': requested}
            detail['attempts'].append(attempt)
            print(f'{ticker} {year}: trying {capture["timestamp"]} at {capture["original"]}', flush=True)
            try:
                raw, source = replay(capture, year)
                _, original = archive_source(source, year)
                mode = 'html'
                try:
                    text, extraction = choose_parser(raw, original)
                except NeedsRendering as error:
                    attempt['static_error'] = str(error)
                    if browser_tried or b'<script' not in raw.lower():
                        raise
                    browser_tried = True
                    print(f'{ticker} {year}: trying one browser replay', flush=True)
                    raw, source = render(capture, year, attempt)
                    _, original = archive_source(source, year)
                    text, extraction = choose_parser(raw, original)
                    mode = 'browser'
                timestamp = source.split('/web/', 1)[1][:14]
                if not same_corporate_host(original, capture['original']):
                    raise ValueError('Replay left the selected corporate host.')
                if not source_in_period(ticker, original, timestamp):
                    raise ValueError('Capture predates the documented corporate identity.')
                row.update(page_text_clean=text, snapshot_url=source, analyst_notes='',
                           theme_categories='', changed_from_prior='', page_similarity_to_prior_year='')
                detail.update(status='extracted', mode=mode, extraction=extraction,
                              candidate_url=page['url'], text_validation=EXTRACTOR_METHOD)
                attempt.update(outcome='accepted', source=source, words=len(text.split()))
                if following := by_year.get(year + 1):
                    following.update(changed_from_prior='', page_similarity_to_prior_year='')
                save()
                break
            except ArchiveRateLimited as error:
                attempt.update(outcome='interrupted', error=str(error))
                save()
                raise
            except (CaptureUnavailable, BrowserError, ValueError) as error:
                attempt.update(outcome='failed', error=str(error))
                print(f'{ticker} {year}: capture failed: {diagnostic(str(error))}', flush=True)
                save()
        if not row['page_text_clean']:
            reason = (detail['attempts'][-1]['error'] if detail['attempts'] else
                      'No eligible in-year captures for the selected About URL.' if page else
                      'No usable About URL selected.')
            row['analyst_notes'] = diagnostic(
                f'Text unavailable after {len(detail["attempts"])} sampled captures. {reason}')
            detail.update(status='gap', reason=reason)
        save()

"""Extract About text from at most three captures per company-year."""

import asyncio
import re
import time
import unicodedata
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from trafilatura import extract
from playwright.async_api import (Error as BrowserError, Request, Response, Route,
                                  TimeoutError as BrowserTimeoutError, async_playwright)

from src.part1.common import (ArchiveRateLimited, Audit, Capture, CaptureUnavailable,
                              EXTRACTOR_METHOD, MAX_CAPTURES_PER_YEAR, Row, archive_source,
                              diagnostic, replay, same_corporate_host, source_in_period)
from src.part1.discover import ABOUT, EXCLUDED, REVIEWED_ROOTS, Page, page_captures, sample

# Remove only identifiable UI here; Trafilatura handles body selection and boilerplate.
BOILERPLATE = ('nav,footer,[role=navigation],[role=contentinfo],[role=dialog],'
               '[role=search],[aria-modal=true],#wm-ipp,#wm-ipp-base,#wm-ipp-print,#donato,'
               '#donate_banner_desktop,#donate_banner_mobile,.js-donate-banner,#topnav,ia-topnav,'
               '.social-feed,.social_feed,.social_feed_wrapper,.twitter-timeline,'
               '.cookie-banner,#onetrust-banner-sdk,#onetrust-consent-sdk,'
               'script,style,noscript,svg,template,'
               'video,audio,button,input,select,textarea,[hidden],[aria-hidden=true]')
ERROR_PAGE = re.compile(
    r'\b(access denied|403 forbidden|404 not found|page not found|'
    r'brand config page only|pardon our interruption|verify (?:that )?you are human|'
    r'checking your browser|request (?:has been )?blocked|service unavailable|'
    r'internal server error|server error|page can ?not render|'
    r'something (?:went|has gone) wrong on our end)\b', re.I)
ARCHIVE_UI = re.compile(
    r'Got an HTTP \d{3} response at crawl time|'
    r'Please Don[’\x27]t Scroll Past This', re.I)
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
    if ARCHIVE_UI.search(text):
        return 'Wayback interface or unresolved redirect, not corporate body text.'
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
    if re.match(r'^Loading\b', title) and soup.find('a', string=re.compile(r'^Impatient\?$')):
        raise NeedsRendering('Wayback redirect interstitial has not resolved.')
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
    """Keep the pipeline synchronous while browser resources load concurrently."""
    return asyncio.run(_render(capture, year, detail))


async def _render(capture: Capture, year: int, detail: Audit) -> tuple[str, str]:
    """Render one dated capture, following archived redirects and waiting for body text."""
    url = f"https://web.archive.org/web/{capture['timestamp']}/{capture['original']}"
    resources: list[Audit] = []
    blocked: list[str] = []
    failed: list[str] = []
    pending: set[Request] = set()
    redirect_hops = 0
    deadline = time.monotonic() + 20
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = None
        try:
            context = await browser.new_context(service_workers='block')
            page = await context.new_page()

            def content(request: Request) -> bool:
                parts = urlsplit(request.url)
                return ((request.resource_type in {'document', 'xhr', 'fetch', 'script'})
                        and not (parts.hostname == 'web.archive.org' and (
                            parts.path.startswith(('/__wb/', '/services/wayback-data/', '/screenshot/'))
                            or re.search(r'/https?://web\.archive\.org/screenshot/', parts.path)))
                        and not (parts.hostname == 'web-static.archive.org'
                                 and parts.path.startswith('/_static/'))
                        and not any('prefetch' in request.headers.get(key, '')
                                    for key in ('purpose', 'sec-purpose')))

            async def route_request(route: Route) -> None:
                request = route.request
                parts = urlsplit(request.url)
                if (parts.hostname == 'web-static.archive.org' and parts.path.startswith('/_static/')
                        and request.resource_type in {'script', 'stylesheet'}):
                    await route.continue_()
                    return
                if (parts.hostname != 'web.archive.org'
                        or parts.path.startswith(('/__wb/', '/services/wayback-data/', '/screenshot/'))
                        or re.search(r'/https?://web\.archive\.org/screenshot/', parts.path)
                        or '/api/ixf/' in parts.path
                        or request.resource_type in {'image', 'media', 'font'}
                        or any('prefetch' in request.headers.get(key, '')
                               for key in ('purpose', 'sec-purpose'))):
                    if content(request):
                        blocked.append(request.url)
                    await route.abort()
                    return
                if not content(request):
                    await route.continue_()
                    return
                try:
                    archive_source(request.url, year)
                    if request.resource_type == 'document' and redirect_hops > 5:
                        raise ValueError('Archive redirect loop or more than five hops.')
                    await route.continue_()
                except ValueError as error:
                    blocked.append(request.url)
                    resources.append({'url': request.url, 'type': request.resource_type,
                                      'blocked': True, 'reason': str(error)})
                    await route.abort()

            def record(response: Response) -> None:
                nonlocal redirect_hops
                if content(response.request):
                    if response.request.resource_type == 'document' and 300 <= response.status < 400:
                        redirect_hops += 1
                    resources.append({'url': response.url, 'status': response.status,
                                      'type': response.request.resource_type,
                                      'memento': response.headers.get('memento-datetime')})

            await context.route('**/*', route_request)
            page.on('request', lambda request: pending.add(request) if content(request) else None)
            page.on('requestfinished', lambda request: pending.discard(request))
            page.on('requestfailed', lambda request: pending.discard(request))
            page.on('requestfailed', lambda request: failed.append(request.url) if content(request) else None)
            page.on('response', record)
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            except BrowserTimeoutError:
                detail['navigation_warning'] = 'Navigation timed out; checking the rendered body.'
            last_error = 'Browser replay did not produce substantive corporate body text.'
            previous_text = ''
            redirects: list[str] = []
            while time.monotonic() < deadline:
                if any(resource.get('status') == 429 for resource in resources):
                    raise ArchiveRateLimited('Archive browser returned HTTP 429; retry after the cooldown.')
                impatient = page.get_by_role('link', name='Impatient?', exact=True)
                if await impatient.count():
                    destination = urljoin(page.url, await impatient.get_attribute('href') or '')
                    _, original = archive_source(destination, year)
                    if not same_corporate_host(original, capture['original']):
                        raise ValueError('Browser redirect left the verified corporate host.')
                    redirect_hops += 1
                    if destination in redirects or redirect_hops > 5:
                        raise ValueError('Wayback redirect loop or more than five redirect hops.')
                    redirects.append(destination)
                    detail['browser_redirects'] = redirects
                    try:
                        await page.goto(destination, wait_until='domcontentloaded',
                                  timeout=max(1, min(15000, int((deadline - time.monotonic()) * 1000))))
                    except BrowserTimeoutError:
                        pass
                    continue
                documents = [resource for resource in resources
                             if resource['type'] == 'document' and resource['url'] == page.url]
                if not documents:
                    last_error = 'Archived document did not load within browser timeout.'
                    await page.wait_for_timeout(min(500, max(1, int((deadline - time.monotonic()) * 1000))))
                    continue
                if documents and documents[-1].get('status') != 200:
                    raise ValueError(f"Browser replay HTTP {documents[-1].get('status', 'blocked')}.")
                memento = documents[-1].get('memento') if documents else None
                source, original = archive_source(page.url, year, memento)
                if not same_corporate_host(original, capture['original']):
                    raise ValueError('Browser redirected to an unverified corporate host.')
                snapshot_url = page.url
                html = await page.evaluate("""() => {
                    const copy = document.documentElement.cloneNode(true);
                    const originals = [...document.documentElement.querySelectorAll('*')];
                    const clones = [...copy.querySelectorAll('*')];
                    originals.forEach((node, i) => {
                        const style = getComputedStyle(node);
                        if (style.display === 'none' || style.visibility === 'hidden') clones[i]?.remove();
                    });
                    return copy.outerHTML;
                }""")
                if page.url != snapshot_url:
                    previous_text = ''
                    continue
                try:
                    text, _ = choose_parser(html, original)
                    if text == previous_text:
                        if redirect_hops > 5:
                            raise ValueError('Archive redirect chain exceeded five hops.')
                        for resource in resources:
                            if 200 <= resource.get('status', 0) < 300:
                                archive_source(resource['url'], year, resource.get('memento'))
                        return str(html), source
                    previous_text = text
                except ValueError as error:
                    previous_text = ''
                    last_error = str(error)
                    if 'Error page or configuration placeholder' in last_error:
                        raise
                await page.wait_for_timeout(min(500, max(1, int((deadline - time.monotonic()) * 1000))))
            raise ValueError(last_error)
        except BrowserError as error:
            raise ValueError(f'Browser replay failed: {error.message[:300]}') from error
        finally:
            detail.update(resources=resources, blocked_content=list(dict.fromkeys(blocked)),
                          failed_requests=list(dict.fromkeys(failed)),
                          pending_requests=[request.url for request in pending])
            try:
                if context is not None:
                    await context.unroute_all(behavior='ignoreErrors')
                    await context.close()
            finally:
                await browser.close()


def parse(ticker: str, page: Page | None, rows: list[Row], audit: Audit,
          save: Callable[[], None]) -> None:
    """Keep saved text; share three annual capture attempts across eligible About URLs."""
    years = audit.setdefault('years', {})
    pending = [row for row in rows if not row['page_text_clean']
               and years.get(row['year'], {}).get('status') != 'gap']
    if not pending:
        return
    pages = [page, *page.get('alternatives', [])] if page else []
    sources = [(source, [capture for capture in page_captures(source, audit)
                        if source_in_period(ticker, capture['original'], capture['timestamp'])])
               for source in pages]
    by_year = {int(row['year']): row for row in rows}
    for row in sorted(pending, key=lambda item: item['year'], reverse=True):
        year = int(row['year'])
        detail: Audit = {'status': 'pending', 'attempts': []}
        years[str(year)] = detail
        samples = [(source, sample(captures, year)) for source, captures in sources]
        attempts = [(source, captures[number]) for number in range(MAX_CAPTURES_PER_YEAR)
                    for source, captures in samples if number < len(captures)]
        for source_page, capture in attempts[:MAX_CAPTURES_PER_YEAR]:
            requested = f"https://web.archive.org/web/{capture['timestamp']}id_/{capture['original']}"
            attempt: Audit = {'requested_url': requested}
            detail['attempts'].append(attempt)
            print(f'{ticker} {year}: trying {capture["timestamp"]} at {capture["original"]}', flush=True)
            try:
                mode = 'html'
                try:
                    raw, source = replay(capture, year)
                    _, original = archive_source(source, year)
                    text, extraction = choose_parser(raw, original)
                except (CaptureUnavailable, ValueError) as error:
                    attempt['static_error'] = str(error)
                    print(f'{ticker} {year}: static capture unusable; trying browser replay', flush=True)
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
                              candidate_url=source_page['url'], text_validation=EXTRACTOR_METHOD)
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
                      'About URL indexing was incomplete; retry discovery.' if any(
                          item.get('index_error') for item in audit.get('source_discovery', {}).get('choices', [])) else
                      'No eligible in-year captures for the discovered About URLs.' if page else
                      'No usable About URL selected.')
            row['analyst_notes'] = diagnostic(
                f'Text unavailable after {len(detail["attempts"])} sampled captures. {reason}')
            detail.update(status='gap', reason=reason)
        save()

"""Retain issuer narrative with source locations; never accept partial scanned proxies."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

from bs4 import BeautifulSoup, NavigableString, Tag

from .common import SECTIONS, WORDS, word_count as _words

OCR_MODEL = "deepseek-ai/DeepSeek-OCR-2"
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DATE = re.compile(rf"\b({MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(20\d{{2}})\b", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00ad", "")).strip()


def proxy_identity(text: str) -> dict:
    """Read the annual-meeting year from its date or an explicit meeting title."""
    cover = _clean(text[:40000])
    # Small-cap PDF/HTML headings commonly split 'A NNUAL M EETING' into separate runs.
    cover = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", r"\1\2", cover)
    annual = list(re.finditer(r"\bannual(?:\s+and\s+special)?\s+(?:general\s+)?meeting\b", cover, re.I))
    special = re.search(r"\bspecial\s+meeting\b", cover[:12000], re.I)
    if special and (not annual or special.start() < annual[0].start()):
        annual = []
    candidates, title_years = [], []
    for anchor in annual:
        before = cover[max(0, anchor.start() - 65):anchor.start()]
        after = cover[anchor.end():anchor.end() + 240]
        notice = bool(re.search(r"notice of (?:the |our )?(?:20\d\d )?$", before, re.I))
        title_year = re.search(r"\b(20\d\d)\s*$", before) or re.match(r"\s*(?:of (?:shareholders|stockholders|members)\s+)?(?:for\s+)?(20\d\d)\b", after, re.I)
        if title_year:
            title_years.append((3 if notice else 1, int(title_year.group(1))))
        match = DATE.search(after)
        if not match:
            continue
        prefix = after[:match.start()]
        # Submission deadlines and signature dates near meeting references are not meeting dates.
        if re.search(r"\b(?:before|advance|submit|prior|record|sincerely|postponements|adjournments)\b", prefix, re.I):
            continue
        explicit = bool(re.search(r"\bheld\b|\b(?:date|time|when)\b", prefix, re.I))
        if re.search(r"\bproxy statement\b", prefix, re.I) and not explicit:
            continue
        if not explicit and _words(prefix) > 15:
            continue
        score = 2 if explicit else 1
        if notice:
            score += 3
        try:
            date = datetime.strptime(" ".join(match.groups()), "%B %d %Y").date().isoformat()
            candidates.append((score, date))
        except ValueError:
            pass
    best_score = max((score for score, _ in candidates), default=0)
    ordered = sorted({date for score, date in candidates if score == best_score})
    date = ordered[0] if len(ordered) == 1 else ""
    years = {int(value[:4]) for value in ordered}
    # A clear meeting title can establish the year without inventing an exact date.
    if not years:
        title_score = max((score for score, _ in title_years), default=0)
        years = {year for score, year in title_years if score == title_score}
    year = next(iter(years)) if len(years) == 1 else None
    issues = []
    if not annual:
        issues.append("No explicit annual-meeting identity found in the cover text.")
    elif year is None:
        issues.append("Annual-meeting year is missing or ambiguous; review required.")
    elif not date:
        issues.append("Annual-meeting year confirmed; exact meeting date is missing or ambiguous.")
    return {
        "annual": bool(annual), "meeting_date": date,
        "meeting_year": year,
        "quality_issues": issues,
    }


def _numeric_table(table: Tag) -> bool:
    cells = table.find_all(["td", "th"], recursive=True)
    texts = [_clean(cell.get_text(" ", strip=True)) for cell in cells]
    if len(texts) < 6 or any(_words(text) >= 30 for text in texts):
        return False
    numeric = sum(bool(re.search(r"\d", text)) and _words(text) <= 3 for text in texts)
    return numeric >= 3 and numeric / len(texts) >= 0.3


def _html(content: bytes) -> tuple[list[dict], str, list[str]]:
    soup = BeautifulSoup(content, "html.parser")
    for element in soup.select("script, style, noscript, nav, footer, form, button, select, input, [hidden], [aria-hidden='true']"):
        element.decompose()
    for element in list(soup.find_all(style=True)):
        if element.parent is not None and re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", element.get("style", ""), re.I):
            element.decompose()
    for element in soup.find_all("ix:hidden"):
        element.decompose()
    identity = soup.get_text(" ", strip=True)
    # SEC filings use tables for page layout; remove only numeric leaf tables.
    for table in list(soup.find_all("table")):
        if table.parent is not None and not table.find("table") and _numeric_table(table):
            table.decompose()
    blocks, index = [], 0
    containers = {"html", "body", "main", "article", "section", "div", "table", "tbody", "thead", "tr", "td", "th", "ul", "ol", "blockquote"}
    paragraph_tags = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd"}

    # Walk nested layout containers once, keeping inline text in its parent paragraph.
    def visit(node: Tag) -> None:
        nonlocal index
        if node.name in paragraph_tags and not node.find(containers | paragraph_tags):
            value = _clean(node.get_text(" ", strip=True))
            internal_links = node.find_all("a", href=re.compile(r"^#"))
            if internal_links and _words(value) < 25 and _clean(" ".join(link.get_text(" ", strip=True) for link in internal_links)) == value:
                return
            if value:
                index += 1
                bold_style = re.compile(r"font-weight\s*:\s*(?:bold|[6-9]00)", re.I)
                bold = node.find(["b", "strong"]) or bold_style.search(node.get("style", "")) or node.find(style=bold_style)
                blocks.append({"text": value, "locator": f"html:block:{index}", "heading": node.name.startswith("h") or (len(value) < 180 and bool(bold))})
            return
        pending = []

        def flush() -> None:
            nonlocal index
            value = _clean(" ".join(pending))
            pending.clear()
            if value:
                index += 1
                blocks.append({"text": value, "locator": f"html:block:{index}", "heading": len(value) < 150})

        for child in node.children:
            if isinstance(child, NavigableString):
                pending.append(str(child))
            elif isinstance(child, Tag):
                if child.name in containers | paragraph_tags or child.find(containers | paragraph_tags) or child.name == "br":
                    flush()
                    if child.name != "br":
                        visit(child)
                else:
                    pending.append(child.get_text(" ", strip=True))
        flush()

    visit(soup.body or soup)
    repeated = Counter(block["text"] for block in blocks if _words(block["text"]) < 8)
    blocks = [block for block in blocks if repeated[block["text"]] < 8]
    return blocks, identity, []


def _ocr_page(page, raw_hash: str, number: int, python: str | None, work_dir: Path) -> str:
    key = hashlib.sha256(f"{raw_hash}:{number}:{OCR_MODEL}".encode()).hexdigest()
    folder = work_dir / "ocr" / key
    folder.mkdir(parents=True, exist_ok=True)
    record_path, image_path = folder / "review.json", folder / "page.png"
    if not image_path.exists():
        page.get_pixmap(dpi=180, alpha=False).save(str(image_path))
    if not record_path.exists() and python:
        result = subprocess.run(
            [python, str(Path(__file__).with_name("ocr.py")), str(image_path), str(record_path)],
            capture_output=True, text=True, timeout=600, check=False,
        )
        if result.returncode:
            raise ValueError(f"DeepSeek OCR failed on PDF page {number}: {result.stderr[-600:]}")
    if not record_path.exists():
        raise ValueError(f"PDF page {number} requires OCR; configure PART2_OCR_PYTHON. Image: {image_path}")
    record = json.loads(record_path.read_text())
    # OCR text enters the dataset only after review against the rendered source page.
    if not record.get("approved") or record.get("model") != OCR_MODEL:
        raise ValueError(f"Review OCR against PDF page {number}, then set approved=true in {record_path}")
    text = _clean(str(record.get("text", "")))
    tokens = WORDS.findall(text.lower())
    if len(tokens) < 20 or (len(tokens) > 80 and len(set(tokens)) / len(tokens) < 0.1):
        raise ValueError(f"Unusable OCR on PDF page {number}: {record_path}")
    return str(record["text"])


def _pdf(content: bytes, python: str | None, work_dir: Path) -> tuple[list[dict], str, list[str], str]:
    import pymupdf

    pages, raw_hash, ocr_count = [], hashlib.sha256(content).hexdigest(), 0
    with pymupdf.open(stream=content, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("Encrypted PDF requires a password.")
        for number, page in enumerate(document, 1):
            blocks = page.get_text("blocks", sort=True)
            native = [block for block in blocks if len(block) >= 7 and block[6] == 0]
            text = "\n".join(block[4] for block in native)
            area = max(1, page.rect.width * page.rect.height)
            image_area = sum(pymupdf.Rect(item["bbox"]).get_area() for item in page.get_image_info())
            broken = text.count("\ufffd") > max(3, len(text) * .01)
            scanned = image_area / area >= .45 and _words(text) < 120
            if scanned or broken:
                text = _ocr_page(page, raw_hash, number, python, work_dir)
                ocr_count += 1
                page_blocks = [{"text": _clean(part), "locator": f"pdf:page:{number}:ocr:{i}", "heading": _words(part) < 15} for i, part in enumerate(re.split(r"\n\s*\n|\n(?=#{1,6}\s)", text), 1) if _clean(part)]
            else:
                page_blocks = [{"text": _clean(block[4]), "locator": f"pdf:page:{number}:block:{i}", "heading": _words(block[4]) < 15, "margin": block[1] < 50 or block[3] > page.rect.height - 45} for i, block in enumerate(native, 1) if _clean(block[4])]
            pages.append(page_blocks)
    # Normalize page numbers so repeated margin headers and footers can be removed.
    def header_key(block: dict) -> str:
        return re.sub(r"\d+", "#", block["text"].lower())

    repeated = Counter(key for page in pages for key in {header_key(block) for block in page if block.get("margin")})
    flattened = [block for page in pages for block in page if not (block.get("margin") and repeated[header_key(block)] >= 3)]
    identity = "\n".join(block["text"] for page in pages[:8] for block in page)
    method = "mixed" if ocr_count and ocr_count < len(pages) else "deepseek_ocr" if ocr_count else "pdf_native"
    issues = [f"{ocr_count} PDF page(s) use manually approved DeepSeek OCR."] if ocr_count else []
    return flattened, identity, issues, method


def _section(text: str) -> str | None:
    if re.search(r"\b(?:compensation|remuneration|pay versus performance|pay.for.performance|incentive|equity award|pension|salary)\b", text, re.I):
        return "compensation"
    if re.search(r"\b(?:human capital|workforce|employee|diversity|inclusion|talent|workplace)\b", text, re.I):
        return "workforce"
    if re.search(r"\b(?:sustainab|environment|climate|community|communities|social responsibility|citizenship|ESG)\w*", text, re.I):
        return "responsibility"
    if re.search(r"\b(?:governance|board|director|ethics|risk oversight|audit committee)\b", text, re.I):
        return "governance"
    if re.search(r"\b(?:message from|business highlights|our business|proxy statement summary|[\w’]+ values|other information)\b", text, re.I):
        return "other"
    return None


def _meeting_logistics(text: str, words: int) -> bool:
    if re.match(r"(?:proxy statement pursuant to section|\(name of registrant as specified)", text, re.I):
        return True
    if words > 200:
        return False
    return bool(re.match(
        r"(?:we (?:are pleased to )?invite you to (?:attend|join)|"
        r"only (?:share|stock)holders of record|"
        r"this booklet includes the formal notice|"
        r"this proxy statement (?:explains more about|tells you about)|"
        r"financial information is provided separately)", text, re.I,
    ))


def _narrative(blocks: list[dict], meeting_year: int | None = None) -> tuple[list[dict], dict, list[str]]:
    paragraphs, section, shareholder, instructions, omitted = [], "other", False, False, 0
    voting_tail = False
    for position, block in enumerate(blocks):
        text = block["text"].strip("# *")
        words = _words(text)
        title = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", r"\1\2", text)
        short_title = _words(title) <= 22 and len(title) <= 200
        heading = block.get("heading", False) and short_title
        future_proposals = (
            short_title
            and re.search(r"(?:shareholder|stockholder) proposals?", title, re.I)
            and (re.search(r"next year", title, re.I)
                 or meeting_year and re.search(rf"\b{meeting_year + 1}\b", title))
        )
        meeting_tail = short_title and re.match(
            r"(?:\d[.\s]+)?(?:annual meeting information|shareholders entitled to vote|information about (?:the|our) meeting|voting procedures)", title, re.I,
        )
        # Late meeting instructions and next-year submission rules end the narrative.
        if position > len(blocks) * .7 and (future_proposals or meeting_tail):
            voting_tail = True
        if voting_tail:
            continue
        response_heading = re.search(r"(?:statement\s+(?:in\s+)?opposition|(?:board|company|our)\S*\s+(?:of directors\s+)?(?:response|recommendation)|\bboard\b.{0,45}\brecommends?\b.{0,35}\bagainst\b|reasons\s+(?:for\s+)?(?:voting\s+)?against)", text, re.I)
        if heading and position > len(blocks) * .4 and re.fullmatch(r"(?:shareholder|stockholder) proposals?(?:\s+\d+)?\s*:?", text, re.I):
            instructions, section = False, "governance"
        numbered = bool(re.match(r"(?:proposal|item)\s*(?:no\.?\s*)?[0-9]+", text, re.I))
        proponent = re.search(
            r"\b(?:this|following) (?:shareholder |stockholder )?proposal (?:was |has been )?submitted\b|"
            r"\b(?:has|have) (?:been )?advised\b.{0,1000}\b(?:introduce|present|submit) the following (?:resolution|proposal)\b|"
            r"\b(?:has|have) notified (?:the company|us)\b.{0,80}\bpresent the following proposal\b", text, re.I,
        )
        resolution = re.match(r"[\s\"“‘']*resolved\s*[:,].{0,40}\b(?:shareholders|stockholders)\b.{0,60}\b(?:request|urge|ask)\b", text, re.I)
        # Exclude proponent demands until an issuer response or a new section begins.
        if heading and re.match(r"(?:shareholder|stockholder) proposal\b", text, re.I) and (len(blocks) < 100 or position > len(blocks) * .4):
            shareholder = True
        elif heading and numbered:
            shareholder = False
        if proponent or resolution:
            shareholder = True
        if response_heading and heading:
            shareholder = False
        elif heading and re.fullmatch(r"(?:corporate governance|compensation discussion and analysis|executive compensation|audit committee report|other matters)", text, re.I):
            shareholder = False
        if shareholder:
            omitted += words
            continue
        if heading:
            recognized = _section(title)
            if re.search(r"(?:questions and answers|information about (?:the|our) annual meeting|voting (?:information|instructions|procedures)|general (?:meeting )?information|attending the annual meeting|items of business|board voting recommendation)", title, re.I):
                instructions = True
            elif recognized and not re.match(r"(?:how|who|when|what|where|why|can|may|is|are|do|does|will|which)\b", text, re.I):
                instructions = False
            section = recognized or section
        if instructions:
            continue
        if _meeting_logistics(text, words):
            continue
        if words < 10 or (words < 18 and not re.search(r"[A-Za-z][.!?](?:\s|$)", text)) or sum(character.isalpha() for character in text) / max(1, len(text)) < .5:
            continue
        numbers = re.findall(r"\b\d[\d,.%]*", text)
        if len(numbers) >= 6 and len(numbers) > words * .4:
            continue
        if re.search(r"\b(?:table of contents|how (?:do|can) i vote|vote (?:by|via) (?:telephone|phone|internet|mail)|voting instructions|instructions for voting|proxy card|directions to the annual meeting)\b", text, re.I):
            continue
        if re.match(r"(?:important notice regarding|approval of proposal|this proposal requires)", text, re.I):
            continue
        if re.search(r"\.{4,}\s*\d+\b", text):
            continue
        paragraphs.append({"id": f"p{len(paragraphs) + 1:05d}", "text": text, "section": section, "locator": block["locator"], "words": words})
    coverage = {name: {"present": any(p["section"] == name for p in paragraphs), "paragraphs": sum(p["section"] == name for p in paragraphs), "words": sum(p["words"] for p in paragraphs if p["section"] == name)} for name in SECTIONS}
    issues = []
    if omitted:
        issues.append(f"Excluded {omitted} words in shareholder proposals; issuer responses retained when identified.")
    if shareholder and not instructions:
        issues.append("Shareholder-proposal boundary reaches document end; inspect issuer-response coverage.")
    if coverage["other"]["words"] > sum(p["words"] for p in paragraphs) / 2:
        issues.append("Over half the narrative has no recognized section heading.")
    return paragraphs, coverage, issues


def extract(content: bytes, url: str, *, ocr_python: str | None = None, work_dir: Path | None = None) -> dict:
    """Extract one complete proxy; unresolved OCR pages cause an explicit gap."""
    if not content:
        raise ValueError("Empty document.")
    if content.lstrip().startswith(b"%PDF"):
        blocks, identity, issues, method = _pdf(content, ocr_python, work_dir or Path(".cache/part2"))
    else:
        blocks, identity, issues = _html(content)
        method = "html"
    if re.search(r"(?:your request originates from an undeclared automated tool|request rate threshold exceeded|access denied|temporarily unavailable)", identity[:5000], re.I) and _words(identity) < 1000:
        raise ValueError("Source returned an access/block page.")
    details = proxy_identity(identity)
    paragraphs, coverage, narrative_issues = _narrative(blocks, details["meeting_year"])
    text = "\n\n".join(paragraph["text"] for paragraph in paragraphs)
    if sum(paragraph["words"] for paragraph in paragraphs) < 300:
        raise ValueError("Fewer than 300 retained narrative words; extraction is incomplete or unusable.")
    return {
        "text": text, "paragraphs": paragraphs, "method": method,
        "identity_text": identity[:40000], "source_url": url,
        "annual": details["annual"], "meeting_date": details["meeting_date"],
        "meeting_year": details["meeting_year"],
        "quality_issues": details["quality_issues"] + issues + narrative_issues,
        "section_coverage": coverage,
    }

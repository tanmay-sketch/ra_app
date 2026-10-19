"""Classify stated values and compare adjacent years' retained page text."""

import hashlib
import re
from collections.abc import Callable, Sequence

import numpy as np
from pydantic import BaseModel, Field

from src.part1.common import (
    ANALYSIS_METHOD,
    CATEGORIES,
    COMPARISON_METHOD,
    EMBED_MODEL,
    EMBEDDING_TOKEN_LIMIT,
    MODEL,
    NOTE_WORD_LIMIT,
    Audit,
    Category,
    Row,
    ask,
    client,
    diagnostic,
    encoded,
    model_call,
    tokenizer,
)
from src.part1.discover import page_identity
from src.tickers import TICKERS

LINK_PROMPT = re.compile(
    r"^(?:learn (?:more|how|about|why)|read more|find (?:out|information)|"
    r"see (?:how|our)|click|watch|search jobs|a message from|"
    r"connect and communicate)\b|^(?:more|learn more)[.!\s]*$",
    re.I,
)


class Theme(BaseModel):
    category: Category
    line_index: int = Field(ge=0)


class Interpretation(BaseModel):
    themes: list[Theme] = Field(max_length=len(CATEGORIES))
    analyst_notes: str = Field(min_length=1, max_length=300)


def normalized(text: str) -> str:
    return " ".join(text.split())


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def is_link_prompt(line: str) -> bool:
    return bool(LINK_PROMPT.search(line.lstrip(" -•\t")))


def check_evidence(themes: list[Theme], lines: dict[int, str]) -> tuple[Audit, Audit, list[Audit]]:
    evidence, quotes, rejected = {}, {}, []
    for theme in themes:
        line = lines.get(theme.line_index)
        if line is None:
            reason = "Evidence index is outside the supplied substantive lines."
        else:
            evidence.setdefault(theme.category, line)
            quotes.setdefault(
                theme.category, {"line_index": theme.line_index, "quote": line}
            )
            continue
        rejected.append({**theme.model_dump(), "reason": reason})
    return evidence, quotes, rejected


def interpret(ticker: str, row: Row, audit: Audit) -> Audit:
    lines = {
        index: line
        for index, line in enumerate(row["page_text_clean"].splitlines())
        if line.strip() and not is_link_prompt(line)
    }
    if not lines:
        raise ValueError("No substantive lines remain after excluding link prompts.")
    company = TICKERS[ticker]
    identity = company["name"]
    if company.get("former_name"):
        identity += f" (formerly {company['former_name']}; {company['history_source']})"
    prompt = (
        f"Classify the {row['year']} corporate About text for {identity}. "
        "Return explicitly stated corporate commitments/priorities from the category definitions, "
        "each with the original line_index of a line that states the commitment. "
        "Select the substantive statement's index, not its heading. Do not generate quotations. "
        "Links, headings, product capabilities, statistics, awards and news alone do not qualify. "
        "Historical innovation alone does not state a current Innovation commitment. "
        "Follow the category boundaries: community quality of life is not product/service Quality; "
        "safe housing is not organizational Safety; generic corporate responsibility or available "
        "retail careers do not establish Inclusion. An empty category list is valid. "
        f"Write one observational note of at most {NOTE_WORD_LIMIT} words about this page's scope. "
        "Exclude dates, legal-name suffixes, historical comparisons, claims about actual conduct "
        "and repetition of the category list. "
        f"SOURCE: {row['snapshot_url']}\nCATEGORIES: {encoded(CATEGORIES)}\n"
        f"PAGE (original zero-based line indexes): {encoded(lines)}"
    )
    response = ask(prompt, Interpretation, audit, max_output_tokens=2000)
    evidence, quotes, rejected = check_evidence(response.themes, lines)
    note = normalized(response.analyst_notes)
    result = {
        "theme_evidence": evidence,
        "supporting_quotes": quotes,
        "page_note": note,
        "text_key": text_key(row["page_text_clean"]),
        "model": MODEL,
        "method": ANALYSIS_METHOD,
        "assessment_complete": bool(evidence) or not rejected,
    }
    if rejected:
        result["excluded_evidence"] = rejected
    if not result["assessment_complete"]:
        result["page_note"] = (
            "No category had valid evidence; review the page and excluded labels in the audit."
        )
    if len(note.split()) > NOTE_WORD_LIMIT:
        result.update(
            model_note=note, note_error="Analyst note exceeded the word limit and was excluded."
        )
        if result["assessment_complete"]:
            result["page_note"] = (
                "Page text was classified; the model's note exceeded the word limit."
            )
    return result


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    left, right = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if left.ndim != 1 or right.ndim != 1 or not left.size or left.shape != right.shape:
        raise ValueError("Embedding dimensions differ or are empty.")
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("Nonfinite embedding.")
    denominator = np.linalg.norm(left) * np.linalg.norm(right)
    if not denominator or not np.isfinite(denominator):
        raise ValueError("Zero or nonfinite embedding norm.")
    return float(np.clip(np.dot(left, right) / denominator, -1, 1))


def embedding(text: str, vectors: dict[str, list[float]], audit: Audit) -> list[float]:
    text = normalized(text)
    if text not in vectors:
        count = len(tokenizer().encode(text, disallowed_special=()))
        if count > EMBEDDING_TOKEN_LIMIT:
            raise ValueError(
                f"Whole page has {count} tokens; limit is {EMBEDDING_TOKEN_LIMIT}. "
                "Text retained without truncation."
            )
        response = model_call(
            audit,
            "embeddings",
            EMBED_MODEL,
            lambda: client().embeddings.create(
                model=EMBED_MODEL, input=text, encoding_format="float"
            ),
        )
        vector = response.data[0].embedding
        if not vector or not np.isfinite(vector).all() or not np.linalg.norm(vector):
            raise ValueError("Invalid embedding response.")
        vectors[text] = vector
    return vectors[text]


def saved_assessments(rows: list[Row], audit: Audit, save: Callable[[], None]) -> dict[str, Audit]:
    cache = {}
    refreshed = False
    for row in rows:
        if not row["page_text_clean"]:
            continue
        detail = audit["years"].setdefault(row["year"], {})
        result = detail.get("analysis", {})
        key = text_key(row["page_text_clean"])
        lines = row["page_text_clean"].splitlines()
        evidence = result.get("theme_evidence", {})
        quotes = result.get("supporting_quotes", {})
        # Reuse v4 results when their saved evidence still matches this page.
        compatible = (
            result.get("model") == MODEL
            and result.get("method") in {ANALYSIS_METHOD, "supported_statement_evidence_v4"}
            and result.get("text_key") == key
            and result.get("assessment_complete") is True
            and isinstance(evidence, dict) and isinstance(quotes, dict)
            and evidence.keys() == quotes.keys()
            and all(
                category in CATEGORIES
                and isinstance(quote, dict)
                and type(index := quote.get("line_index")) is int
                and 0 <= index < len(lines)
                and lines[index].strip() and not is_link_prompt(lines[index])
                and evidence[category] == lines[index]
                and isinstance(quote.get("quote"), str) and quote["quote"].strip()
                and quote["quote"] in lines[index]
                for category, quote in quotes.items()
            )
        )
        if compatible:
            if key not in cache or not cache[key].get("source_review"):
                cache[key] = result
            continue
        if result.get("method"):
            detail["previous_analysis_method"] = result["method"]
        detail.pop("analysis", None)
        detail.pop("analysis_error", None)
        detail.update(status="extracted", analysis_pending_method=ANALYSIS_METHOD)
        row.update(
            theme_categories="",
            analyst_notes="Analysis pending: current source requires a refreshed assessment.",
        )
        refreshed = True
    if refreshed:
        # Persist invalidated labels before a model request can fail.
        save()
    return cache


def classify(ticker: str, rows: list[Row], audit: Audit, save: Callable[[], None]) -> None:
    cache = saved_assessments(rows, audit, save)
    failures = {}
    for row in sorted(rows, key=lambda row: row["year"]):
        if not row["page_text_clean"]:
            continue
        detail = audit["years"].setdefault(row["year"], {})
        key = text_key(row["page_text_clean"])
        try:
            if key in failures:
                raise ValueError(failures[key])
            if key not in cache:
                cache[key] = interpret(ticker, row, audit)
            result = cache[key]
            detail["analysis"] = result
            detail.pop("analysis_pending_method", None)
            if not result["assessment_complete"]:
                raise ValueError(
                    "All model category labels lacked valid supporting evidence; "
                    "see excluded_evidence in audit."
                )
            row.update(
                theme_categories=encoded(
                    [category for category in CATEGORIES if category in result["theme_evidence"]]
                ),
                analyst_notes=result["page_note"],
            )
            detail.update(status="analyzed")
            detail.pop("analysis_error", None)
        except ValueError as error:
            if key not in cache:
                failures[key] = str(error)
            detail.update(status="analysis_failed", analysis_error=str(error))
            row.update(
                theme_categories="", analyst_notes=diagnostic("Analysis incomplete: " + str(error))
            )
        save()


def compare(rows: list[Row], audit: Audit, save: Callable[[], None]) -> None:
    vectors = {}
    by_year = {int(row["year"]): row for row in rows}
    for year, row in sorted(by_year.items()):
        detail = audit["years"].setdefault(str(year), {})
        prior = by_year.get(year - 1, {})
        before, text = prior.get("page_text_clean", ""), row["page_text_clean"]
        prior_detail = audit["years"].get(str(year - 1), {})
        current_source = detail.get("candidate_url") or row["snapshot_url"]
        prior_source = prior_detail.get("candidate_url") or prior.get("snapshot_url", "")
        same_page = (
            current_source and prior_source
            and page_identity(current_source) == page_identity(prior_source)
        )
        detail.pop("source_page_changed", None)
        detail.pop("comparison_skipped", None)
        if not (before and text and same_page):
            row.update(changed_from_prior="", page_similarity_to_prior_year="")
            for key in (
                "comparison_texts", "comparison_method",
                "comparison_embedding_model", "similarity_error",
            ):
                detail.pop(key, None)
            if before and text:
                detail["comparison_skipped"] = "Adjacent years use different source pages."
            save()
            continue
        keys = [text_key(normalized(before)), text_key(normalized(text))]
        row["changed_from_prior"] = str(int(keys[0] != keys[1]))
        if keys[0] == keys[1]:
            row["page_similarity_to_prior_year"] = "1.00000000"
            if row["theme_categories"]:
                row["analyst_notes"] = "No wording change."
        elif (
            detail.get("comparison_texts") != keys
            or detail.get("comparison_method") != COMPARISON_METHOD
            or detail.get("comparison_embedding_model") != EMBED_MODEL
            or not row["page_similarity_to_prior_year"]
        ):
            try:
                previous_vector = embedding(before, vectors, audit)
                current_vector = embedding(text, vectors, audit)
                similarity = cosine(previous_vector, current_vector)
                row["page_similarity_to_prior_year"] = f"{similarity:.8f}"
            except ValueError as error:
                row["page_similarity_to_prior_year"] = ""
                detail["similarity_error"] = str(error)
                save()
                continue
        detail.update(
            comparison_texts=keys,
            comparison_method=COMPARISON_METHOD,
            comparison_embedding_model=EMBED_MODEL,
        )
        detail.pop("similarity_error", None)
        save()


def analyze(ticker: str, rows: list[Row], audit: Audit, save: Callable[[], None]) -> None:
    classify(ticker, rows, audit, save)
    compare(rows, audit, save)
    for row in sorted(rows, key=lambda row: row["year"]):
        print(
            f"{ticker} {row['year']}: {row['theme_categories'] or 'unassessed'}; "
            f"changed={row['changed_from_prior'] or 'unavailable'}",
            flush=True,
        )

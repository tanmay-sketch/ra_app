"""Local phrase-based themes, financial tone and adjacent-year wording similarity."""

import csv
import gzip
import json
import os
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from spacy.matcher import PhraseMatcher

from .common import OUTPUT_DIR, THEMES, WORDS, WORK_DIR, digest, encoded, word_count
from .dataset import read_document
from .themes import PHRASES

METHOD = 'proxy-local-v2'
TONE_GROUPS = ('positive', 'negative', 'uncertainty')
TFIDF_SETTINGS = {'lowercase': True, 'sublinear_tf': True, 'ngram_range': [1, 2]}
TOPIC_SETTINGS = {
    'method': 'spacy-phrase-lower-v1', 'vocabulary_sha256': digest(encoded(PHRASES)),
    'spacy_version': spacy.__version__,
    'unit': 'nonoverlapping paragraph', 'denominator': 'all retained narrative words',
}


@lru_cache(maxsize=1)
def phrase_matcher():
    """Build a case-insensitive phrase matcher without a downloaded language model."""
    nlp = spacy.blank('en')
    matcher = PhraseMatcher(nlp.vocab, attr='LOWER')
    if set(PHRASES) != set(THEMES):
        raise ValueError('Part 2 phrase vocabulary must cover the ten shared themes.')
    for theme, phrases in PHRASES.items():
        matcher.add(theme, [nlp.make_doc(phrase) for phrase in phrases])
    return nlp, matcher


def classify(paragraphs: list[dict]) -> tuple[dict[str, float], list[dict]]:
    """Count each paragraph's words once per matched theme; themes may overlap."""
    nlp, matcher = phrase_matcher()
    assigned = dict.fromkeys(THEMES, 0)
    evidence, total = [], 0
    for paragraph in paragraphs:
        text = paragraph['text']
        words = word_count(text)
        # Unmatched paragraphs remain in the denominator.
        total += words
        doc = nlp.make_doc(text)
        matches = {}
        for match_id, start, end in matcher(doc):
            theme = nlp.vocab.strings[match_id]
            matches.setdefault(theme, set()).add(doc[start:end].text.lower())
        for theme in matches:
            assigned[theme] += words
        if matches:
            evidence.append({'paragraph_id': paragraph['id'], 'words': words,
                             'matches': {key: sorted(value) for key, value in sorted(matches.items())}})
    if not total:
        raise ValueError('No narrative words available for theme shares.')
    return {theme: round(words / total, 8) for theme, words in assigned.items()}, evidence


def lexicon(path: Path | None) -> tuple[dict[str, set[str]], dict]:
    if path is None or not path.is_file():
        raise ValueError('Loughran–McDonald dictionary unavailable; tone was not recomputed.')
    groups = {name: set() for name in TONE_GROUPS}
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = {name.strip().lower(): name for name in reader.fieldnames or []}
        if not {'word', *groups} <= columns.keys():
            raise ValueError('Dictionary needs Word, Positive, Negative and Uncertainty columns.')
        for row in reader:
            for group in groups:
                # Negative flags identify words removed from the official category.
                if float(row[columns[group]] or 0) > 0:
                    groups[group].add(row[columns['word']].strip().upper())
    if any(not words for words in groups.values()):
        raise ValueError('Dictionary has an empty tone category; check the master CSV.')
    return groups, {'filename': path.name, 'sha256': digest(path.read_bytes()),
                    'membership': 'positive flags only', 'word_counts': {k: len(v) for k, v in groups.items()}}


def tone(text: str, dictionary: dict[str, set[str]]) -> dict[str, float]:
    """Return matching word occurrences per 1,000 analyzed words."""
    tokens = [match[0].upper() for match in WORDS.finditer(text)]
    return {name: round(sum(token in words for token in tokens) * 1000 / len(tokens), 6)
            for name, words in dictionary.items()} if tokens else {}


def fixed_tfidf(texts: list[str], fit_dir: Path) -> tuple[TfidfVectorizer, dict]:
    """Reuse one vocabulary and IDF so new documents do not shift earlier scores."""
    path = fit_dir / 'tfidf.json.gz'
    exists = path.exists()
    saved = json.loads(gzip.decompress(path.read_bytes())) if exists else None
    vectorizer = TfidfVectorizer(**{**TFIDF_SETTINGS, 'ngram_range': (1, 2)})
    if exists:
        if (not isinstance(saved, dict) or saved.get('method') != METHOD
                or saved.get('settings') != TFIDF_SETTINGS):
            raise ValueError('Frozen TF–IDF method/settings differ; review before explicitly replacing the fit.')
        if saved.get('fit_sha256') != digest(encoded({k: v for k, v in saved.items() if k != 'fit_sha256'})):
            raise ValueError('Frozen TF–IDF checksum mismatch; restore the committed fit.')
        vectorizer.set_params(vocabulary=saved['vocabulary'])
        vectorizer.idf_ = np.asarray(saved['idf'], dtype=float)
    else:
        vectorizer.fit(texts)
        saved = {'method': METHOD, 'settings': TFIDF_SETTINGS,
                 'vocabulary': vectorizer.vocabulary_, 'idf': vectorizer.idf_.tolist(),
                 'fit_documents': len(texts),
                 'fit_corpus_sha256': digest(encoded(sorted(digest(text) for text in texts)))}
        saved['fit_sha256'] = digest(encoded(saved))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f'.{path.name}.tmp')
        try:
            with temporary.open('wb') as stream:
                # A fixed gzip timestamp keeps an unchanged fit byte-for-byte stable.
                stream.write(gzip.compress((encoded(saved) + '\n').encode(), mtime=0))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return vectorizer, {key: value for key, value in saved.items() if key not in {'vocabulary', 'idf'}}


def _notes(row: dict, previous: dict | None, problems: list[str], issues: list[str]) -> str:
    notes = []
    if previous is None:
        notes.append('No adjacent usable meeting year for comparison.')
    else:
        if row['similarity_to_prior']:
            notes.append(f"Wording cosine versus {previous['year']}: {float(row['similarity_to_prior']):.3f}.")
        before = load_values(previous.get('theme_shares', ''))
        now = load_values(row.get('theme_shares', ''))
        shifts = sorted(((key, now[key] - before[key]) for key in THEMES if key in before and key in now),
                        key=lambda item: abs(item[1]), reverse=True)
        if shifts and abs(shifts[0][1]) >= .01:
            notes.append('Largest theme-share changes: ' + ', '.join(
                f'{key} {difference * 100:+.1f} pp' for key, difference in shifts[:2]
                if abs(difference) >= .01) + '.')
        before_tone, now_tone = load_values(previous.get('tone_rates', '')), load_values(row.get('tone_rates', ''))
        tone_changes = [(key, now_tone[key] - before_tone[key]) for key in TONE_GROUPS
                        if key in before_tone and key in now_tone]
        if tone_changes:
            key, difference = max(tone_changes, key=lambda item: abs(item[1]))
            if abs(difference) >= .1:
                notes.append(f'{key.capitalize()} tone {difference:+.1f} matches per 1,000 words.')
    notes.extend(problems)
    warnings = [issue for issue in issues if not re.fullmatch(
        r'Excluded \d+ words in shareholder proposals; issuer responses retained when identified\.', issue)]
    if warnings:
        notes.append('Extraction review: ' + ' '.join(warnings))
    return ' '.join(notes)


def load_values(value: str) -> dict:
    return json.loads(value) if value else {}


def analyze(rows: list[dict], audits: dict[str, dict], save: Callable[[], None], *,
            fit_dir: Path = OUTPUT_DIR, dictionary_path: Path | None = None) -> None:
    """Validate saved narratives, compute local measures and record comparison notes."""
    usable = []
    for row in rows:
        if not row.get('text_file'):
            for field in ('theme_shares', 'tone_rates', 'similarity_to_prior'):
                row[field] = ''
            continue
        detail = audits[row['ticker']].setdefault('years', {}).setdefault(str(row['year']), {})
        try:
            document = read_document(row, audits[row['ticker']])
            paragraphs, text = document['paragraphs'], document['text']
            if (not paragraphs or len({p['id'] for p in paragraphs}) != len(paragraphs)
                    or '\n\n'.join(p['text'] for p in paragraphs) != text):
                raise ValueError('Saved paragraph boundaries do not match retained text.')
            usable.append((row, detail, document))
        except (OSError, ValueError, KeyError) as error:
            for field in ('theme_shares', 'tone_rates', 'similarity_to_prior'):
                row[field] = ''
            row['analyst_notes'] = f'Analysis unavailable: {error}'
            detail['analysis'] = {'method': METHOD, 'errors': [str(error)]}
    if not usable:
        save()
        return

    # A similarity or dictionary failure affects only its own measure.
    try:
        vectorizer, fit = fixed_tfidf([document['text'] for _, _, document in usable], fit_dir)
        matrix = vectorizer.transform([document['text'] for _, _, document in usable])
        fit_error = ''
    except (ValueError, OSError, KeyError) as error:
        matrix, fit, fit_error = None, {}, f'Wording similarity unavailable: {error}'
    dictionary_path = dictionary_path or WORK_DIR / 'Loughran-McDonald_MasterDictionary_1993-2025.csv'
    try:
        dictionary, dictionary_meta = lexicon(dictionary_path)
        dictionary_error = ''
    except (ValueError, OSError) as error:
        dictionary, dictionary_meta, dictionary_error = {}, {}, str(error)
    positions = {(row['ticker'], int(row['year'])): index for index, (row, _, _) in enumerate(usable)}
    pending_notes = []
    for index, (row, detail, document) in enumerate(usable):
        text, paragraphs = document['text'], document['paragraphs']
        text_key = digest(text)
        old = detail.get('analysis', {})
        shares, evidence = classify(paragraphs)
        row['theme_shares'] = encoded(shares)
        problems = []
        analysis = {'method': METHOD, 'text_sha256': text_key, 'words': word_count(text),
                    'topics': {**TOPIC_SETTINGS, 'evidence': evidence},
                    'tokenization': WORDS.pattern, 'tfidf': fit}

        # Reuse tone during a dictionary outage only when text and method still match.
        if dictionary:
            values = tone(text, dictionary)
            row['tone_rates'] = encoded(values)
            analysis['tone'] = {'dictionary': dictionary_meta, 'values': values}
        elif (old.get('method') == METHOD and old.get('text_sha256') == text_key
              and old.get('tokenization') == WORDS.pattern and old.get('tone')):
            analysis['tone'] = old['tone']
            row['tone_rates'] = encoded(old['tone']['values'])
            problems.append(dictionary_error + ' Previous tone retained.')
        else:
            row['tone_rates'] = ''
            problems.append(dictionary_error)

        # Compare adjacent meeting years only; never bridge an uncollected year.
        prior_index = positions.get((row['ticker'], int(row['year']) - 1))
        previous = usable[prior_index][0] if prior_index is not None else None
        row['similarity_to_prior'] = ''
        if fit_error:
            problems.append(fit_error)
            if (previous is not None and old.get('method') == METHOD
                    and old.get('text_sha256') == text_key
                    and old.get('prior_text_sha256') == digest(usable[prior_index][2]['text'])
                    and old.get('similarity_to_prior') is not None):
                row['similarity_to_prior'] = f"{old['similarity_to_prior']:.6f}"
                analysis['tfidf'] = old.get('tfidf', {})
                analysis['prior_text_sha256'] = old['prior_text_sha256']
                problems[-1] += ' Previous cosine retained.'
        elif previous is not None:
            if matrix[index].nnz and matrix[prior_index].nnz:
                row['similarity_to_prior'] = f'{cosine_similarity(matrix[index], matrix[prior_index])[0, 0]:.6f}'
                analysis['prior_text_sha256'] = digest(usable[prior_index][2]['text'])
            else:
                problems.append('No terms match the fixed TF–IDF vocabulary; similarity unavailable.')
        if row['similarity_to_prior']:
            analysis['similarity_to_prior'] = float(row['similarity_to_prior'])
        analysis['errors'] = problems
        detail['analysis'] = analysis
        issues = list(detail.get('extraction', {}).get('quality_issues', []))
        review = detail.get('collection', {}).get('review_required')
        if review:
            issues.append(str(review))
        pending_notes.append((row, previous, problems, issues))

    # Notes use this run's metrics even when callers supply rows out of year order.
    for row, previous, problems, issues in pending_notes:
        row['analyst_notes'] = _notes(row, previous, problems, issues)
        save()

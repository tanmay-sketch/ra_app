"""Part 2 paths, disclosure themes and small serialization helpers."""

import hashlib
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
OUTPUT_DIR = ROOT / 'part2' / 'outputs'
WORK_DIR = ROOT / 'part2' / 'work'
YEARS = range(2016, 2025)
METHOD_VERSION = 'annual-proxy-spacy-v2'
SECTIONS = ('governance', 'compensation', 'workforce', 'responsibility', 'other')
# Shared categories allow later comparisons with Part 1's stated values.
THEMES = {
    'Integrity': 'Ethics, compliance, transparency, accountability and responsible corporate conduct.',
    'Innovation': 'Research, invention, scientific discovery and development of new technology or capabilities.',
    'Quality': 'Product and service reliability, quality standards, craftsmanship and performance excellence.',
    'Safety': 'Protecting people, operational safety, cybersecurity, data security and privacy.',
    'Customers': 'Customer or patient needs, experiences, access, satisfaction and outcomes.',
    'Employees': 'Employee wellbeing, working conditions, compensation, training and career development.',
    'Inclusion': 'Diversity, equity, inclusion, accessibility and equal opportunity.',
    'Environment': 'Emissions, energy, natural resources, climate and environmental impacts.',
    'Community': 'Philanthropy, volunteering, community investment and societal benefit.',
    'Shareholders': 'Shareholder returns, capital allocation, profitability and financial discipline.',
}
WORDS = re.compile(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*")


def word_count(text: str) -> int:
    """Use the same word-count rule for theme shares and tone denominators."""
    return len(WORDS.findall(text))


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def encoded(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def load_json(path: Path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, encoded(value) + '\n')


def atomic_text(path: Path, value: str) -> None:
    """Replace a complete file so an interrupted write cannot leave partial output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

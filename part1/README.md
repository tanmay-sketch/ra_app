# Part 1: Stated Values

## Scope and findings

Archived English About Us, mission, values or equivalent pages represent stated
values for 2016–2024. The supplied 50-company roster contains ten companies per
sector. Fixed membership and sector labels support comparisons across years and
parts; January 2024 membership and market-cap rankings were not independently
reconstructed.

**Usable text covers 220 of 450 company-years (48.9%) and 45 companies.** Six
companies have all nine years. Coverage rises from 14 companies in 2016 to 38 in
2024, so sample changes can distort trends. Of 171 comparable adjacent-year pairs,
106 differ in wording and 65 are unchanged.

Morgan Stanley's page expands from four named values in [2020][ms-2020] to five
in [2021][ms-2021], adding “Commit to Diversity & Inclusion.” Diversity and
belonging already appeared in 2020: the change formalizes an existing emphasis
without establishing changed conduct. Part 2 comparisons therefore require
matched observations and inspection of the statements.

## Research decisions

**One official page per company.** Official-domain searches, reviewed historical
links and homepage links supply up to three candidates for Wayback CDX checks.
An LLM selects a company-wide overview, mission, values or principles page,
preferring broader historical coverage. Product, support, news and
recruitment-only pages are excluded. Reusing an accepted URL improves consistency
but can miss historical URL migrations.

**A bounded annual sample.** Successful HTML captures are indexed monthly. The
capture nearest July 1 is tried first, then distinct earliest/latest captures,
with at most three attempts per year. The midpoint gives a consistent target;
alternatives allow recovery without exhaustive retries. One browser replay per
year can recover JavaScript content. Bounded failure does not prove archive
absence.

**Comparable archived text.** Redirects allow five hops, ending within the target
year on the same corporate host or a reviewed rebrand host. Live content, errors
and navigation- or statistics-only captures are rejected. Trafilatura removes
navigation, footers, cookie notices and boilerplate, with a main-content fallback.
At least 25 substantive words are required to exclude empty page shells.
Accepted text survives reruns unless a quality rejection is recorded.

**Contextual classification.** `gpt-4o-mini-2024-07-18` assigns categories and a
short page note. Compared with keywords, contextual classification accommodates
paraphrases and distinguishes commitments from headings, statistics or historical
achievements. Source lines supporting labels are copied into the audit, allowing
inspection without guaranteeing correct interpretation.

Ten categories span conduct, capabilities, stakeholders and wider
responsibilities, supporting comparison across sectors and with disclosures:

| Category | Stated commitment |
| --- | --- |
| Integrity | Ethics, honesty and accountability |
| Innovation | Research, invention and new capabilities |
| Quality | Reliable, excellent products and services |
| Safety | Protection of people, data and privacy |
| Customers | Customer or patient needs and outcomes |
| Employees | Wellbeing, fair conditions and development |
| Inclusion | Diversity, equity and accessibility |
| Environment | Emissions, resources and environmental protection |
| Community | Philanthropy, volunteering and social contribution |
| Shareholders | Long-term shareholder value and financial discipline |

## Measures and calculations

Comparisons require usable text in consecutive years **from the same source
page**. Missing years and page substitutions are not bridged. Let `A` and `B`
denote the previous and current texts after collapsing whitespace:

```text
changed_from_prior = 0 if A = B; 1 otherwise
```

Unavailable comparisons stay blank. This reproducible rule records small edits
as changes without judging their importance or identifying changed values.

For nonidentical texts, `text-embedding-3-small` supplies vectors `a` and `b`:

```text
similarity = dot(a, b) / (length(a) × length(b))
```

Cosine ranges from −1 to 1; higher scores indicate closer semantic content.
Identical texts receive 1 directly. Separating similarity from the change flag
distinguishes an exact edit from its semantic size; redesigns and extraction
loss can affect both.

## Dataset columns

[`outputs/dataset.csv`](outputs/dataset.csv) contains one row per company-year,
including missing observations.

| Column | Meaning and reason for inclusion |
| --- | --- |
| `ticker` | Fixed company identifier for matching across parts. |
| `company_name` | Readable company label from the roster. |
| `sector` | Fixed sector label for group comparisons. |
| `year` | Target archive year, 2016–2024. |
| `page_text_clean` | Retained body text supporting analysis and inspection. |
| `changed_from_prior` | Exact adjacent-year wording-change flag defined above. |
| `theme_categories` | JSON list of supported categories; `[]` means none assigned, blank means unassessed. |
| `analyst_notes` | Short current-page observation, unchanged-text note or reason analysis/text is unavailable. |
| `snapshot_url` | Accepted Wayback replay URL for source verification. |
| `page_similarity_to_prior_year` | Whole-page cosine similarity; blank when unavailable. |

The local audit records page selection, capture attempts, extraction checks,
category evidence and request usage.

## Limitations and next steps

The **230 gaps** comprise 170 observations without eligible in-year captures for
the selected URL, 45 without a selected URL and 15 rejected during extraction or
rendering. AVGO, INTC, MDT, COP and VLO have no usable observations. Gap reasons
remain in the CSV and audit; no text or year is imputed.

One capture represents a year; public statements describe priorities rather than
behavior. Paired linguistic shifts were examined illustratively. Further work
would verify the roster, map historical URLs, independently review labels and
compare matched mission/values sections to separate substantive shifts from
redesigns.

## Reproduction

Code is in [`../src/part1/`](../src/part1/) and [`../main.py`](../main.py).
Execution requires `OPENAI_API_KEY` in the root `.env`. From the repository root:

```sh
uv sync
uv run playwright install chromium  # First setup
uv run python main.py               # Resume, preserving accepted text
uv run python main.py AVGO           # Retry gaps for an explicit ticker
```

[ms-2020]: https://web.archive.org/web/20200624220438id_/https://www.morganstanley.com/about-us/morgan-stanley-core-values
[ms-2021]: https://web.archive.org/web/20210731180301id_/https://www.morganstanley.com/about-us/morgan-stanley-core-values/

# Part 2: Lived Values

## Scope and findings

This part examines reported priorities in annual **DEF 14A proxy statements** for
Part 1's 50-company roster, 2016–2024. As of **20 October 2026**, the
[dataset](outputs/dataset.csv) contains **421 of 450 company-years (93.6%)**,
covering **49 companies**, with **360 adjacent-year comparisons**.

Retained observations, each out of 90 possible per sector: Technology 86,
Financials 86, Healthcare 88, Consumer Discretionary 75 and Energy 86.
The 29 gaps comprise nine Target issuer-selection failures, ten browser timeouts
and ten identity/extraction failures. These are collection outcomes, not proof
that the underlying filings are unavailable.

The calculated measures show several descriptive differences:

- Microsoft's Safety share increased from **3.94% in 2023 to 10.01% in 2024**;
  wording similarity was **0.758**.
- In 2024, Environment shares averaged **9.09% in Energy versus 2.04% in
  Healthcare**, with ten companies in each sector.
- Across 44 adjacent filing pairs spanning the
  [11 March 2020 pandemic announcement][covid], mean Safety emphasis increased
  **0.57 percentage points** and negative tone increased **0.43 matches/1,000 words**.
- Across 44 pairs spanning the [25 August 2022 pay-versus-performance rule
  adoption][pay-rule], Shareholders emphasis increased **0.12 points** and
  uncertainty increased **0.31 matches/1,000 words**. Applicable disclosures concern
  fiscal years ending on or after 16 December 2022, so adoption and application
  dates differ.

## Research decisions

**One recurring disclosure type.** Proxy statements were selected for their annual
cadence, common regulatory structure and discussion of governance and incentives.
This provides a consistent basis for comparison, while narrowing the meaning of
“lived values” to disclosed priorities rather than independently verified conduct.
The company roster and sector assignments remain fixed to Part 1.

**Traceable sources and years.** [SEC EDGAR][edgar] provides primary filings,
issuer identifiers and publication dates. Browser searches use the exact issuer
and `DEF 14A` form, followed by **preview → Open document**. The first complete
filing confirming the issuer and annual-meeting year is retained; exhibits,
supplements and special-meeting-only filings are excluded. Meeting year is used
because fiscal-year labels do not consistently identify the annual proxy cycle.
The preceding filing year is also checked for early publications.

**Bounded collection and explicit gaps.** At most three candidate documents are
checked per missing year, keeping runtime predictable. Accepted sources survive
reruns. Missing rows remain in the panel with explanations; adjacent years are
not substituted, which would conceal gaps and distort measured changes.

**Company narrative as the comparison unit.** HTML/native PDF text is cleaned of
navigation, voting instructions, repeated margins and numeric tables. Identified
shareholder proposals are separated from company responses to avoid attributing
outside investors' requests to management. Nonoverlapping paragraphs preserve
context without repeatedly counting the same passage. Scanned pages require
reviewed OCR.

**Transparent local analysis.** spaCy phrase matching was selected for inspectable
labels and low cost across long filings. The ten themes follow Part 1: Integrity,
Innovation, Quality, Safety, Customers, Employees, Inclusion, Environment,
Community and Shareholders. The [vocabulary](../src/part2/themes.py) distinguishes
product quality from audit controls and environmental policy from financial
sustainability. Financial dictionary tone and TF–IDF wording measures complement
these themes without paid LLM calls.

## Measures and calculations

The [implementation](../src/part2/analyze.py) uses the following rules. Missing
measures are blank; a computed zero is valid.

### Theme emphasis

A case-insensitive phrase match assigns the whole paragraph to a theme:

```text
theme share = words in paragraphs matching the theme / total analyzed words
```

Each paragraph counts once per theme; unmatched paragraphs remain in the
denominator. Multiple labels are allowed because one passage can discuss several
priorities, so shares may sum above 1. The measure describes paragraph emphasis,
not the fraction of individual words expressing a value.

### Tone

The 1993–2025 [Loughran–McDonald dictionary][dictionary] was selected because
financial disclosures use specialized language. Positive, negative and uncertainty
categories include active membership flags and exclude removed entries.

```text
tone rate = matching word occurrences / total analyzed words × 1,000
```

Occurrences are counted rather than distinct words, capturing repeated emphasis.
Themes and tone share an alphabetic word-count rule allowing internal apostrophes
and hyphens. Dictionary matching does not interpret negation or context.

### Wording similarity

TF–IDF was selected to track wording through an inspectable term representation.
Lowercase single words and two-word sequences use scikit-learn's default tokens
of at least two characters, including numeric tokens; stopwords are retained.
For each term occurring in a document:

```text
TF = 1 + ln(term count)
IDF = 1 + ln((1 + fitted document count) / (1 + fitted documents containing term))
term weight = TF × IDF

similarity = dot(current vector, prior vector) /
             (length(current vector) × length(prior vector))
```

`ln` is the natural logarithm. TF reduces the influence of repetition; IDF gives
less weight to terms common across the fitted documents. Absent terms have zero
weight. Vocabulary/IDF remain frozen from the initial 32 proxies so later additions
do not change earlier scores; this also excludes unseen vocabulary. Higher cosine
means more similar wording. Missing adjacent meeting years or empty vectors leave
similarity blank. This tokenization differs from theme/tone counting.

### Changes, sectors and events

```text
theme change (percentage points) = 100 × (current share − prior share)
tone change = current rate − prior rate
sector mean = sum of available company values / number of companies
sector change = average within-company change for firms present in both years
```

Equal company weights prevent longer filings from dominating sector results.
Matched year pairs reduce changes caused solely by sample composition, although
membership can still vary across pairs. Notes report up to two theme changes of
at least one percentage point and the largest tone change of at least 0.1
matches/1,000 words. These are display cutoffs, not significance tests.

Event comparisons include adjacent filings when:

```text
prior filing date < event date ≤ current filing date
```

Filing dates establish publication timing. The intervals may contain unrelated
changes or text prepared before the event, so the results describe coincidence
rather than causality.

## Dataset columns

Each row represents a company–meeting-year; uncollected source fields remain blank.

| Column | Definition and purpose |
| --- | --- |
| `ticker` | Roster identifier and join key to Part 1. |
| `company_name` | Readable company identity. |
| `sector` | Fixed roster sector for group comparisons. |
| `year` | Annual-meeting year; verified when a proxy is retained. |
| `filing_date` | SEC publication date for event alignment. |
| `meeting_date` | Confirmed exact meeting date, supporting year selection. |
| `accession` | SEC filing identifier for source verification. |
| `source_url` | Direct primary-document URL for traceability. |
| `text_file` | Clean-text path relative to `part2/outputs/`, keeping documents outside the CSV. |
| `theme_shares` | JSON paragraph shares for the ten themes. |
| `tone_rates` | JSON positive, negative and uncertainty occurrences per 1,000 words. |
| `similarity_to_prior` | Adjacent-year TF–IDF cosine, from 0 to 1. |
| `analyst_notes` | Calculated shifts, extraction warnings or gap explanations. |

## Limitations and next steps

Phrase labels lack independent validation and can miss paraphrases or overlabel
long paragraphs. **51 retained rows carry extraction warnings**; each event sample
includes five flagged pairs. Governance/pay content, changing disclosure rules,
coverage gaps and the restricted TF–IDF vocabulary affect comparability. Shared
theme names do not make Part 1's commitment labels equivalent to paragraph shares.

Further work would review flagged passages and gaps, independently validate labels,
and compare consistent sections and company samples. These checks are needed
before interpreting language alignment as organizational authenticity.

## Reproduction

Code is in [`src/part2/`](../src/part2/). Only `outputs/dataset.csv` is tracked;
cleaned text, audit evidence and the frozen TF–IDF fit remain local. Exact cosine
reproduction requires that fit. Collection requires `SEC_USER_AGENT` in `.env`;
tone requires the dictionary path documented in the CLI.

```sh
uv sync
uv run playwright install chromium
uv run python -m src.part2
uv run python -m src.part2 --analyze-only
```

[edgar]: https://www.sec.gov/edgar/search/
[dictionary]: https://sraf.nd.edu/loughranmcdonald-master-dictionary/
[covid]: https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020
[pay-rule]: https://www.sec.gov/newsroom/press-releases/2022-149

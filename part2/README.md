# Part 2: Lived Values

Collect annual **DEF 14A proxy statements** for the same 50 companies as Part 1,
2016–2024. Proxies provide comparable disclosures about governance, incentives
and corporate priorities. They describe reported priorities, not verified conduct.

## Run

From the repository root:

```sh
uv sync
uv run playwright install chromium
uv run python -m src.part2 --pilot        # Six companies, four years
uv run python -m src.part2 META --years 2020 2024
uv run python -m src.part2                # All 50 companies, all nine years
uv run python -m src.part2 --analyze-only # Saved text; no browser or API calls
```

Set `SEC_USER_AGENT="Researcher Name contact@example.com"` in the root `.env`.
Collection opens an isolated, visible Chromium window. `--headless` is optional;
headless Chromium was blocked in the earlier browser test. `--collect-only`
skips analysis. Existing successful documents are retained; missing selected
years are retried, with at most three candidate documents per meeting year.

Tone uses the official [Loughran–McDonald master dictionary][lm], 1993–2025 edition.
The file checksum is recorded in the audit. Download its CSV to `part2/work/Loughran-McDonald_MasterDictionary_1993-2025.csv`,
or pass `--dictionary /path/to/master.csv`. No paid models or API keys are needed.
A missing dictionary leaves tone blank, with an explanation; themes and wording
similarity still run.

## Collection and extraction

The collector follows [SEC full-text search][search] in the browser:

1. Enter the ticker or historical CIK in the company field and select the exact
   autocomplete issuer.
2. Set January 1–December 31 filing dates and the exact `DEF 14A` filing type.
   Search with `proxy`; retry with blank keywords if no primary results appear.
3. Select a primary filing result, open its preview, then click **Open document**.
4. Verify the issuer and annual-meeting year from the document. Exclude exhibits,
   preliminary/supplemental filings and special-meeting-only proxies.
5. If needed, check the preceding filing year, then record a specific gap.

`year` means **annual-meeting year**, not fiscal year or the search's “Reporting
for” field. Exact meeting dates may be blank when only the year is unambiguous.
The first complete matching annual proxy is retained. Historical issuer overrides
cover Broadcom's redomiciliation and Exxon/BlackRock holding-company changes.
The supplied company roster and sector assignments are inherited from Part 1.

One browser worker spaces SEC requests by at least 0.3 seconds, below the
[SEC's aggregate limit of 10 requests/second][access]. HTTP 403/429 pauses collection
and saves progress. There is no submissions-API discovery fallback.

HTML uses its body text; PDFs use embedded text first. Remove navigation, voting
logistics, repeated margins, numeric tables and identified shareholder-proposal
text; retain identifiable company responses. Nonoverlapping paragraphs retain
source locators and section labels for review. Optional [DeepSeek-OCR-2][ocr]
handles scanned PDF pages in a separate CUDA environment via `PART2_OCR_PYTHON`.
OCR pages require source review before use; this GPU path is untested on this Mac.

## Measures

All measures use retained issuer narrative and the same alphabetic word-count
rule. Vocabulary and matched paragraph references are saved for inspection.

- **Themes:** local spaCy phrase matching using the reviewed vocabulary in
  [`themes.py`](../src/part2/themes.py). The ten shared categories cover Integrity
  (ethics), Innovation, Quality (products/services), Safety (including privacy),
  Customers, Employees, Inclusion, Environment, Community and Shareholders
  (returns/capital allocation). These connect stated values to disclosure emphasis.
  Specific phrases avoid conflating executive pay with employee welfare or
  financial sustainability with environmental policy. Paragraphs may have multiple
  themes or none.
- **`theme_shares[k]`** = words in paragraphs matching theme k / all analyzed words.
  Shares range from 0 to 1 and may sum above 1 because themes overlap.
- **`tone_rates[k]`** = dictionary word occurrences / all analyzed words × 1,000,
  for `positive`, `negative` and `uncertainty`. Removed dictionary entries are
  excluded. Negation and legal context are not interpreted.
- **`similarity_to_prior`:** TF–IDF unigram/bigram cosine against the immediately
  preceding meeting year. Vocabulary and IDF are frozen on the first analyzed
  corpus. Gaps are never bridged; unavailable comparisons stay blank.
- **Notes:** observed theme/tone shifts, wording similarity, extraction issues or
  specific collection gaps. These are descriptive calculations, without LLM claims
  about motives or causality.

A computed zero is valid; an unavailable measure is blank. Sector means weight
companies equally and report sample counts. Adjacent changes use the same
companies in both years. Dated COVID-19 and SEC pay-versus-performance reference
points support descriptive comparisons, not causal claims.

## Outputs and schema

`outputs/dataset.csv` has one row for each of the 450 company-years, including
documented gaps. Text is stored separately; there is no `status` column.

| Column | Meaning and purpose |
| --- | --- |
| `ticker` | Company join key shared with Part 1. |
| `company_name` | Human-readable company identity. |
| `sector` | Supplied sector for comparisons. |
| `year` | Verified annual-meeting year. |
| `filing_date` | Publication date for event comparisons. |
| `meeting_date` | Exact meeting date when confirmed. |
| `accession` | Unique SEC filing identifier. |
| `source_url` | Direct original-document URL. |
| `text_file` | Clean-text path relative to `part2/outputs/`. |
| `theme_shares` | JSON word-weighted paragraph shares for the ten themes. |
| `tone_rates` | JSON positive/negative/uncertainty occurrences per 1,000 words. |
| `similarity_to_prior` | Adjacent-year wording cosine, from 0 to 1. |
| `analyst_notes` | Measured shifts, limitations or gap explanation. |

`outputs/text/` contains cleaned documents. Compact `audit.jsonl` records source
hashes, extraction locators, matched phrases and method settings without duplicating
full text. `summary.json` contains coverage, sector means, balanced changes and
event-spanning pairs; figures visualize available coverage and themes.
`tfidf.json.gz` preserves the frozen vocabulary and IDF so the published
comparisons can be reproduced. Original HTML/PDF files, the dictionary and browser
profile remain in ignored `part2/work/`. The old CSV/audit are preserved there as
a migration backup.

## Findings and limitations

The dataset currently contains **33 usable proxies across eight companies**, all
with theme and tone measures, and **10 adjacent-year comparisons**. The six-company,
four-year pilot is complete (24/24). Four previously rejected cached proxies were
recovered, and all 27 earlier sources were preserved. The remaining 417 rows are
unfilled and retain their collection explanations.

Live browser tests verified Meta's 2020 and 2024 primary proxies, including preview
→ Open document and sequential year searches. Source checks corrected meeting
dates, procedural boilerplate and shareholder-proposal attribution. Coverage is
too sparse and uneven for population or sector-trend conclusions.

Phrase matching is transparent and inexpensive but misses paraphrases and may
label an entire paragraph from a brief mention. Executive-pay-heavy proxies,
changing document composition, extraction artifacts and incomplete coverage limit
interpretation. Cross-part comparisons must account for these genre differences.
The dictionary is financial rather than contextual sentiment analysis. Browser
access can be blocked even below the SEC rate limit.

Before substantive authenticity conclusions, finish collection and source-review
gaps. With more time, independently label a balanced passage sample, measure
classification errors, improve verified historical-issuer coverage, and check
results within comparable sections and a constant company sample.

[search]: https://www.sec.gov/edgar/search/
[access]: https://www.sec.gov/about/developer-resources
[lm]: https://sraf.nd.edu/loughranmcdonald-master-dictionary/
[ocr]: https://github.com/deepseek-ai/DeepSeek-OCR-2

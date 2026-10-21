# Part 2: Lived Values in Proxy Disclosures

## Research objective and key findings

This part asks what companies emphasize in formal disclosures and how that emphasis shifts over time. I use **DEF 14A proxy statements** for the same 50 companies and 2016-2024 period as Part 1. Proxies provide recurring disclosures on governance, compensation, board oversight, and shareholder matters. They offer a reproducible view of *disclosed priorities*, but not direct proof of corporate behavior.

The dataset contains **421 of 450 company-years (93.6%) across 49 companies**, including 360 valid adjacent-year comparisons. Coverage by sector is Healthcare 88/90, Technology 86/90, Financials 86/90, Energy 86/90, and Consumer Discretionary 75/90. Twenty-nine observations remain unresolved, including all nine years for Target.

I examined changes across filing pairs bracketing five external events. These results are exploratory associations, not estimated causal effects:

| Event | Matched pairs | Illustrative change in disclosure emphasis |
|---|---:|---|
| U.S. government transition, Jan. 2017 | 47 | Environment: -0.03 percentage points overall; Energy -0.53, Financials +0.51 |
| COVID-19 declaration, Mar. 2020 | 44 | Employees +0.75 pp and Safety +0.57 pp; negative tone +0.43 matches per 1,000 words |
| U.S. government transition, Jan. 2021 | 43 | Environment +0.79 pp overall, including Energy +2.62 pp; Employees +1.50 pp |
| Invasion of Ukraine, Feb. 2022 | 44 | Environment +1.35 pp overall, including Energy +4.29 pp |
| SEC pay-versus-performance rule, Aug. 2022 | 44 | Shareholders +0.12 pp; uncertainty +0.31 matches per 1,000 words |

Sector differences are more informative than overall averages. Healthcare's Employees emphasis rose 1.21 pp around COVID-19, while Energy's Environment emphasis moved particularly strongly around the 2021 and 2022 events. However, the analysis does not show that particular passages refer to those events. Filing dates also differ from drafting dates, and events overlap.

## Sources and analytical method

- **Collection:** SEC EDGAR supplies document identifiers, filings, and dates. Candidates are checked for issuer and annual meeting year; supplements and special-meeting-only statements are excluded. At most three candidates are examined for each missing observation. No year is substituted or silently imputed.
- **Preparation:** HTML or native PDF text is cleaned of repeated margins, voting instructions, navigation, and numeric tables. Nonoverlapping paragraphs form the analysis unit. Shareholder proposals are distinguished from management responses where possible. Scanned PDFs require reviewed OCR.
- **Theme emphasis:** spaCy phrase matching uses the same ten categories as Part 1. A paragraph is counted once for each theme it matches. `theme_share = words in paragraphs matching a theme / all analyzed words`. Overlapping categories mean shares need not sum to 1.
- **Tone and wording:** The 1993-2025 Loughran-McDonald dictionary produces positive, negative, and uncertainty matches per 1,000 analyzed words. Adjacent filings are also compared by TF-IDF cosine similarity using lowercase unigrams/bigrams and fixed vocabulary and IDF from an initial set of 32 proxies. Freezing the representation aids consistency but misses later vocabulary.
- **Event comparisons:** A filing pair is included if `prior filing date < event date <= current filing date`. Changes are computed within companies before equal-weight sector aggregation; missing comparisons stay blank and observed zeros remain zero.

These choices favor transparent, reproducible measurement over treating theme-matching output as a validated interpretation of intent.

## Limitations and next steps

The most serious validity risk is **context-insensitive matching**. A theme can be triggered by negation, procedural wording, director biographies, or shareholder proposals rather than a company's affirmative commitment. A targeted review of Berkshire Hathaway's 2016 and 2024 filings, pursued in Part 4, shows exactly this problem for Inclusion and Community. Differences in proxy templates, section lengths, duplicated passages, and regulatory requirements can further drive measured change.

Fifty-one retained filings have extraction warnings. The 29 missing observations reflect nine Target issuer-selection failures, ten browser timeouts, and ten filing-verification or extraction problems, not confirmed absence of filings. With more time, I would recover missing proxies, validate theme labels against human-coded passages, isolate comparable proxy sections, and separately examine event-specific text. The descriptive event comparisons do not include causal controls or significance tests.

## Output schema and reproduction

[`outputs/dataset.csv`](outputs/dataset.csv) retains all 450 company-years. `ticker`, `company_name`, `sector`, and `year` identify each observation; `filing_date`, `meeting_date`, `accession`, and `source_url` document provenance; `text_file` identifies the extraction; `theme_shares` and `tone_rates` are JSON measures; `similarity_to_prior` records adjacent-year wording similarity; and `analyst_notes` documents changes, warnings, and gaps.

The pipeline is in [`src/part2/`](../src/part2/). Set `SEC_USER_AGENT` and `PART2_LM_DICTIONARY` (path to the [Loughran-McDonald dictionary](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)):

```sh
uv sync
uv run playwright install chromium
uv run python -m src.part2 --dictionary "$PART2_LM_DICTIONARY"
# Analyze previously collected documents without collecting again:
uv run python -m src.part2 --analyze-only --dictionary "$PART2_LM_DICTIONARY"
```

# Part 2: Lived Values in Proxy Disclosures

## Research objective and key findings

This part asks what companies emphasize in formal disclosures and how that emphasis shifts over time. I use **DEF 14A proxy statements** for the same 50 companies and 2016-2024 period as Part 1. Proxies provide recurring disclosures on governance, compensation, board oversight, and shareholder matters. They offer a reproducible view of *disclosed priorities*, but not direct proof of corporate behavior.

The dataset contains **421 of 450 company-years (93.6%) across 49 companies**, including 360 valid adjacent-year comparisons. Coverage by sector is Healthcare 88/90, Technology 86/90, Financials 86/90, Energy 86/90, and Consumer Discretionary 75/90. Twenty-nine observations remain unresolved, including all nine years for Target.

I examined changes across filing pairs bracketing five external events. These results are exploratory associations, not estimated causal effects. The current report command lists filing pairs spanning COVID-19 and SEC rule adoption and summarizes calendar-year changes. It does not reproduce the five-event numerical summaries below:

| Event | Matched pairs | Illustrative change in disclosure emphasis |
|---|---:|---|
| U.S. government transition, Jan. 2017 | 47 | Environment: -0.03 percentage points overall; Energy -0.53, Financials +0.51 |
| COVID-19 declaration, Mar. 2020 | 44 | Employees +0.75 pp and Safety +0.57 pp; negative tone +0.43 matches per 1,000 words |
| U.S. government transition, Jan. 2021 | 43 | Environment +0.79 pp overall, including Energy +2.62 pp; Employees +1.50 pp |
| Invasion of Ukraine, Feb. 2022 | 44 | Environment +1.35 pp overall, including Energy +4.29 pp |
| SEC pay-versus-performance rule, Aug. 2022 | 44 | Shareholders +0.12 pp; uncertainty +0.31 matches per 1,000 words |

Sector differences are more informative than overall averages. Healthcare's Employees emphasis rose 1.21 pp around COVID-19, while Energy's Environment emphasis moved particularly strongly around the 2021 and 2022 events. However, the analysis does not show that particular passages refer to those events. Filing dates also differ from drafting dates, and events overlap.

## Sources and analytical method

- **Collection:** An isolated Chromium browser searches SEC EDGAR for the exact issuer, DEF 14A, and calendar-year filing dates, then opens the primary document through its preview. Each dataset year is the **annual-meeting year**: the search checks filings from that year and the preceding year, first with the keyword `proxy`, then without it if no candidates appear. At most three documents are examined per missing observation; the first with matching issuer, meeting year, and usable narrative is retained. Only primary DEF 14A results are considered; special-meeting-only statements are rejected. Accepted sources are preserved across runs; missing years remain blank. SEC requests are spaced at least 0.3 seconds apart, and access denials pause collection.
- **Preparation:** HTML or native PDF text is cleaned heuristically of repeated margins, voting instructions, navigation, and numeric tables. Nonoverlapping paragraphs form the analysis unit. Identified shareholder-proposal text is excluded, while identified issuer responses are retained. PDF pages flagged as scanned or broken require DeepSeek-OCR-2 and manual approval; unresolved pages prevent acceptance of the document. At least 300 narrative words must remain.
- **Theme emphasis:** Case-insensitive spaCy phrase matching uses the same ten categories as Part 1, without a trained language model. A paragraph is counted once for each theme it matches. `theme_share = words in paragraphs matching a theme / all analyzed words`. Unmatched paragraphs remain in the denominator; overlapping categories mean shares need not sum to 1.
- **Tone and wording:** The 1993-2025 Loughran-McDonald dictionary produces exact positive, negative, and uncertainty word matches per 1,000 analyzed words. Adjacent meeting years are compared by TF-IDF cosine similarity using lowercase unigrams/bigrams and sublinear term frequency; missing years are not bridged. Vocabulary and IDF are fitted on all retained proxies at the first analysis and reused afterward. The existing fit used 32 proxies, so it misses later vocabulary; a fresh fit can yield different similarities.
- **Event comparisons:** A filing pair is included if `prior filing date < event date <= current filing date`. The reporting code computes within-company adjacent-year changes and equal-weight company averages within sectors; its event section identifies spanning pairs rather than estimating event effects. Missing comparisons stay blank and observed zeros remain zero.

These choices favor transparent, reproducible measurement over treating theme-matching output as a validated interpretation of intent.

## Limitations and next steps

The most serious validity risk is **context-insensitive matching**. A theme can be triggered by negation, procedural wording, director biographies, or shareholder proposals rather than a company's affirmative commitment. A targeted review of Berkshire Hathaway's 2016 and 2024 filings, pursued in Part 4, shows exactly this problem for Inclusion and Community. Differences in proxy templates, section lengths, duplicated passages, and regulatory requirements can further drive measured change.

Fifty-one retained filings have extraction warnings. The 29 missing observations reflect nine Target issuer-selection failures, ten browser timeouts, and ten filing-verification or extraction problems, not confirmed absence of filings. With more time, I would recover missing proxies, validate theme labels against human-coded passages, isolate comparable proxy sections, and separately examine event-specific text. The descriptive event comparisons do not include causal controls or significance tests.

## Output schema and reproduction

[`outputs/dataset.csv`](outputs/dataset.csv) retains all 450 company-years. `ticker`, `company_name`, `sector`, and `year` identify each observation, with `year` following the annual meeting; `filing_date`, `meeting_date`, `accession`, and `source_url` document provenance; `text_file` identifies the extraction; `theme_shares` and `tone_rates` are JSON measures; `similarity_to_prior` records adjacent-year wording similarity; and `analyst_notes` documents changes, warnings, and gaps.

The pipeline is in [`src/part2/`](../src/part2/). Set `SEC_USER_AGENT` to a research identity and contact email, and `PART2_LM_DICTIONARY` to the path to the [Loughran-McDonald dictionary](https://sraf.nd.edu/loughranmcdonald-master-dictionary/). Chromium is visible by default; add `--headless` to keep it hidden. The commands below resume a retained local collection; the published CSV alone is insufficient to rerun Part 2. Analysis recomputes all retained observations, even when collection is restricted to selected tickers or years.

```sh
uv sync
uv run playwright install chromium
uv run python -m src.part2 --dictionary "$PART2_LM_DICTIONARY"
# Analyze previously collected documents without collecting again:
uv run python -m src.part2 --analyze-only --dictionary "$PART2_LM_DICTIONARY"
```

OCR, when required, uses `PART2_OCR_PYTHON` pointing to a separate CUDA environment; `uv sync` does not install that environment.

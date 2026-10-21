# Part 1: Stated Values

## Research objective and key findings

This part constructs a longitudinal record of what 50 S&P 500 companies publicly say they value. It examines English-language About Us, mission, values, and equivalent corporate pages archived between 2016 and 2024. The output is a company-year dataset designed for comparison with the proxy-statement disclosures in Part 2.

**Coverage is 269 of 450 company-years (59.8%), with at least one usable page for every company.** Ten companies have complete nine-year histories. Coverage rises from 18 companies in 2016 to 44 in 2024, so observed trends are affected by changing archival availability.

| Sector | Usable company-years | Coverage |
|---|---:|---:|
| Technology | 69/90 | 76.7% |
| Healthcare | 61/90 | 67.8% |
| Financials | 48/90 | 53.3% |
| Energy | 48/90 | 53.3% |
| Consumer Discretionary | 43/90 | 47.8% |
| **Total** | **269/450** | **59.8%** |

Innovation appears in 147 usable pages, Community in 119, and Employees in 110. Inclusion appears in 79 and Environment in 51. These counts describe recovered pages, not sector-wide prevalence. Of 207 adjacent-year pairs with comparable source URLs, 140 (67.6%) have different wording and 67 (32.4%) are identical. A wording change does not necessarily imply a change in organizational priorities; semantic similarity provides context for its magnitude.

## Collection and measurement decisions

1. **Identify relevant pages.** Headless current-homepage navigation, reviewed URLs, and optional official-domain searches identify corporate overview or mission/values pages. CDX queries each candidate URL for monthly HTTP-200 HTML records. If indexed coverage leaves gaps, up to two archived homepages are checked for historical links. An LLM selects the preferred page and eligible alternatives from their URLs, labels, and indexed years. Product pages, locations, and reports are excluded unless specifically reviewed.
2. **Select annual captures.** Each URL supplies up to three distinct in-year captures, prioritizing the capture nearest July 1, then the earliest and latest. Attempts rotate across eligible URLs, sharing a limit of three captures per company-year in a collection run. Missing years are not filled using another year's text.
3. **Extract substantive text.** Accepted captures must be in-year, attributable to an appropriate company or reviewed rebrand domain, and free of archive/error-page artifacts. Redirect chains longer than five hops are rejected. Trafilatura and a main-content fallback remove navigation, footers, and boilerplate; at least 25 substantive words are required. Headless replay is used when static replay or extraction fails.
4. **Classify and compare.** `gpt-4o-mini-2024-07-18` labels explicit commitments using ten shared categories: Integrity, Innovation, Quality, Safety, Customers, Employees, Inclusion, Environment, Community, and Shareholders. Supporting source lines are required. For consecutive years with the same normalized source URL, text equality after whitespace normalization produces `changed_from_prior`. Identical text receives similarity 1; otherwise, `text-embedding-3-small` cosine similarity describes semantic continuity. For unequal texts, similarity stays blank if either page exceeds the 8,192-token embedding limit; text is not truncated.

The fixed ten-category scheme enables Parts 1 and 2 to be joined, but it also compresses nuanced corporate language into broad labels. Neither the labels nor the embedding score independently establish that an organization's values changed.

## Missingness, interpretation, and limitations

Of 181 unresolved company-years, 164 lack an eligible in-year capture among checked About-page URLs; 17 failed capture replay, rendering, or extraction. A targeted recovery pass added 49 observations without replacing 220 previously accepted texts. The search remains deliberately bounded: an unrecovered page is **not** evidence that the organization lacked a values statement.

Historical URL migrations, page redesigns, incomplete archived scripts, and changing page scope threaten comparability. Boilerplate may survive extraction, and LLM theme assignments have not been independently validated against a broad human-labeled sample. Because coverage is especially sparse in earlier years and differs by sector, the appropriate interpretation is descriptive and conditional on observed pages, not a representative trend for all 450 expected observations.

With more time, I would reconstruct historical URLs by year, search archived sitemaps, manually inspect unresolved captures, validate a stratified sample of theme labels, and examine concrete examples of substantive linguistic change separately from website redesigns.

## Output schema and reproduction

[`outputs/dataset.csv`](outputs/dataset.csv) retains all 450 company-years, including missing observations. The fields are `ticker`, `company_name`, `sector`, `year` (panel keys); `page_text_clean` (extracted text); `theme_categories` (JSON list, where `[]` is an assessed empty list and blank means unassessed); `changed_from_prior` and `page_similarity_to_prior_year` (comparable annual changes); `snapshot_url` (archival provenance); and `analyst_notes` (source decisions and gaps).

Code is under [`src/part1/`](../src/part1/) and [`main.py`](../main.py). Set `OPENAI_API_KEY`, then run:

```sh
uv sync
uv run playwright install chromium
uv run python main.py
# Retry missing years for one company while retaining accepted data:
uv run python main.py AVGO
```

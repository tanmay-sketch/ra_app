# Part 1: Stated Values

## Scope and findings

Part 1 examines how companies publicly describe their organizational values over time. I collected archived English-language About Us, mission, values, and equivalent pages for the supplied 50 companies across 2016–2024.

The [dataset](outputs/dataset.csv) contains **220 usable company-years out of 450 (48.9%)**, covering 45 companies. Six companies have complete nine-year histories. Coverage increases from 14 companies in 2016 to 38 in 2024, indicating substantially better recovery of recent pages.

| Sector | Usable / Expected | Coverage |
|---|---:|---:|
| Healthcare | 52 / 90 | 57.8% |
| Financials | 48 / 90 | 53.3% |
| Technology | 46 / 90 | 51.1% |
| Consumer Discretionary | 43 / 90 | 47.8% |
| Energy | 31 / 90 | 34.4% |
| **Total** | **220 / 450** | **48.9%** |

Among **171 comparable adjacent-year pairs**, 106 (62.0%) differ in wording and 65 (38.0%) are identical.

Across the 220 usable pages, the most frequently identified themes are Innovation (117 pages), Community (103), and Employees (101). Environment appears in 46 pages and Inclusion in 66. These are frequencies among successfully collected pages, not representative estimates for the entire roster. Missingness and differences in page content limit interpretation.

The results establish an initial longitudinal dataset of stated values, but uneven coverage limits conclusions about sector-wide trends or shifts across the full 2016–2024 period.

## Research decisions and methodology

### Page discovery and archival collection

The [Wayback Machine CDX API](https://web.archive.org/cdx/search/cdx) was used to retrieve historical corporate pages. Official-domain searches, reviewed historical links, and homepage references generate up to three candidate URLs per company. An LLM selects a company-wide About Us, mission, values, or principles page, prioritizing historical coverage and excluding product, news, support, and recruitment-only pages.

For each selected URL, the pipeline searches for annual captures, prioritizing the snapshot nearest July 1, followed by distinct earliest and latest captures. At most three captures are attempted per year, with one browser replay where necessary.

The July midpoint provides a consistent annual reference, while bounded retries make collection feasible across 450 observations. However, these limits may exclude recoverable historical material.

### Extraction and quality controls

Archived pages present several complications: URL migrations, corporate rebranding, JavaScript-dependent content, redirect chains, and incomplete Wayback captures.

Redirects are followed for up to five hops and accepted only when they resolve to an appropriate corporate or reviewed rebrand host within the target year. Live pages, archive errors, and captures containing only navigation or statistics are rejected.

Trafilatura (python library) extracts substantive body text, with a main-content fallback. At least 25 substantive words are required. Accepted observations are preserved across reruns unless a quality problem is identified.

These rules prioritize reliable source attribution over maximizing the number of accepted pages.

### Theme classification and wording changes

I use `gpt-4o-mini-2024-07-18` to identify ten categories, consistent with the conceptual framework used in Part 2:

| Theme | Organizational commitment |
|---|---|
| Integrity | Ethics, honesty, accountability |
| Innovation | Research, invention, new capabilities |
| Quality | Product and service reliability |
| Safety | People, data, and privacy protection |
| Customers | Customer and patient needs |
| Employees | Wellbeing, fair treatment, development |
| Inclusion | Diversity, equity, accessibility |
| Environment | Environmental protection and resources |
| Community | Social contribution and philanthropy |
| Shareholders | Long-term value and financial discipline |

Contextual LLM classification accommodates paraphrases and distinguishes explicit commitments from incidental references. Supporting source lines are retained in the local audit for review.

Adjacent-year comparisons require usable text from consecutive years and the same selected source page. After whitespace normalization:

```text
changed_from_prior =
    0 if current text equals prior text
    1 otherwise
```

For nonidentical texts, `text-embedding-3-small` computes semantic similarity:

```text
Similarity = dot(current vector, prior vector)
             / (norm(current) × norm(prior))
```

The norm is Euclidean vector length. Cosine similarity ranges from −1 to 1, with higher values indicating more similar semantic content. Identical text receives a similarity of 1 directly.

The change flag identifies any wording difference, while cosine similarity helps distinguish minor edits from larger semantic changes. Neither independently establishes that organizational values changed.

## Collection gaps and challenges

The central limitation is **historical data recovery**, rather than text classification.

Of the 450 expected observations, **230 (51.1%) remain unavailable**:

| Failure category | Company-years |
|---|---:|
| No eligible in-year capture for selected URL | 170 |
| No usable About Us URL selected | 45 |
| Extraction or rendering failures | 15 |
| **Total** | **230** |

Five companies, AVGO, INTC, MDT, COP, and VLO, have no usable observations.

The largest challenge is that corporate websites are not historically stable. Companies redesign their websites, move values statements between pages, change domains, and sometimes consolidate or discontinue older URLs. A selected modern About Us URL may have no archived captures even when equivalent content existed elsewhere.

The current pipeline searches a limited number of candidate URLs and captures. It does not exhaustively reconstruct each company's historical website architecture. Consequently, **failure to recover a page is not evidence that the page or its values statement did not exist**.

Extraction introduces further difficulties. Some archived HTML references scripts or resources that were never preserved, while other captures replay incomplete content or redirect to live pages. Browser rendering improves recovery in some cases but cannot reconstruct missing archival resources.

### Why these gaps remain

A more comprehensive recovery strategy is feasible but was not fully implementable within the assignment's time constraints. It would involve:

- Searching historical URLs independently for each year, rather than relying primarily on a selected URL.
- Exploring archived site navigation, sitemaps, and redirect histories to reconstruct changes in page location.
- Expanding capture attempts and browser-based recovery for difficult websites.
- Manually reviewing unresolved observations and using archived equivalent pages where justified.

These improvements would increase collection time and require additional verification to ensure that recovered pages remain comparable.

I therefore chose **bounded, auditable collection with explicit missingness** rather than accepting weakly matched pages, using adjacent-year substitutions, or silently filling gaps.

This decision preserves data integrity but introduces selection bias. More recent years have substantially better coverage, and sector differences may partly reflect archival accessibility rather than differences in corporate values.

## Dataset schema

The [output CSV](outputs/dataset.csv) retains one row per company-year, including unsuccessful observations.

| Column | Purpose |
|---|---|
| `ticker`, `company_name`, `sector` | Fixed company identity and sector, enabling comparisons across parts |
| `year` | Target archive year |
| `page_text_clean` | Extracted substantive page text |
| `changed_from_prior` | Exact adjacent-year wording-change indicator |
| `theme_categories` | JSON list of identified themes; `[]` means none assigned, blank means unassessed |
| `analyst_notes` | Page observations and collection-gap explanations |
| `snapshot_url` | Accepted Wayback source for verification |
| `page_similarity_to_prior_year` | Adjacent-year semantic cosine similarity |

A local audit additionally records page selection, capture attempts, extraction checks, supporting evidence for categories, and model usage.

## Limitations and next steps

**Coverage and selection bias.** With only 48.9% coverage, the sample cannot support unrestricted longitudinal or sector-level generalizations. Comparisons should use matched observations and report sample sizes.

**Page comparability.** A website redesign or shift in the location of mission statements can produce apparent changes without any substantive change in corporate priorities.

**Classification validity.** LLM categorization supports contextual interpretation but remains subject to errors. Independent human annotation  along with more robust category matching algorithms from NLP would be needed to evaluate consistency and accuracy.

**Stated values versus conduct.** Public-facing pages reflect organizational communication, not verified behavior. Part 2 provides a separate disclosure-based perspective, but the two sources cannot be treated as interchangeable evidence.

Further work would prioritize historical URL reconstruction, targeted recovery of missing observations, manual validation of theme assignments, and robustness checks on a consistent sample of company pages.

For Part 3, the dataset provides an initial measure of stated priorities, with **missingness and source comparability treated explicitly rather than assumed away**.

## Reproduction

Code is available in [`src/part1/`](../src/part1/) and [`main.py`](../main.py). Execution requires `OPENAI_API_KEY` in the root `.env`.

```sh
uv sync
uv run playwright install chromium

# Resume collection, retaining accepted observations
uv run python main.py

# Retry a selected company's missing observations
uv run python main.py AVGO
```

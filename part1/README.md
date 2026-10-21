# Part 1: Stated Values

## Scope and findings

Part 1 examines how companies publicly describe their organizational values through archived English-language About Us, mission, values, and equivalent pages from 2016–2024. Company identities and sector labels follow the fixed [50-company roster](../src/tickers.py).

The [dataset](outputs/dataset.csv) contains **269 usable company-years out of 450 (59.8%)**, covering all 50 companies. Ten companies have complete nine-year histories. Coverage increases from 18 companies in 2016 to 44 in 2024, indicating substantially better recovery of recent pages.

| Sector | Usable / Expected | Coverage |
|---|---:|---:|
| Healthcare | 61 / 90 | 67.8% |
| Financials | 48 / 90 | 53.3% |
| Technology | 69 / 90 | 76.7% |
| Consumer Discretionary | 43 / 90 | 47.8% |
| Energy | 48 / 90 | 53.3% |
| **Total** | **269 / 450** | **59.8%** |

Among **207 comparable adjacent-year pairs**, 140 (67.6%) differ in wording and 67 (32.4%) are identical.

Across the 269 usable pages, the most frequently identified themes are Innovation (147 pages), Community (119), and Employees (110). Environment appears in 51 pages and Inclusion in 79. These are frequencies among successfully collected pages, not representative estimates for the entire roster. Missingness and differences in page content limit interpretation.

The results establish an initial longitudinal dataset of stated values, but uneven coverage limits conclusions about sector-wide trends or shifts across the full 2016–2024 period.

A targeted headless recovery run for Salesforce and the five previously empty companies added **49 observations**, retaining all 220 previously collected texts and their source URLs. The rest of the dataset retains earlier collection results. Remaining gaps have not been exhaustively searched.

## Research decisions and methodology

### Page discovery and archival collection

The [Wayback Machine CDX API](https://web.archive.org/cdx/search/cdx) locates historical captures, keeping HTTP 200 HTML records and at most one indexed capture per month. A headless Chromium browser reads official homepage navigation, including links added by JavaScript. These links are ranked alongside reviewed historical sources. Static homepage retrieval and optional official-domain search provide fallbacks. Corporate overview, mission, and values pages take priority over reports, locations, and product pages.

Up to three candidate URLs are indexed initially. If years remain uncovered, at most two archived homepages are inspected for historical paths, with up to three observed candidates checked from each. An LLM selects the preferred About page and any eligible alternatives. Previously successful URLs remain useful evidence but do not prevent discovery of pages used in other years.

For each year, captures nearest July 1 are tried first across the eligible URLs. Distinct earliest and latest captures are tried if the remaining budget allows. All eligible URLs share a limit of **three total capture attempts per company-year in each collection run**. Each selected capture can use headless replay when static extraction fails. The browser waits for substantive body text and follows archived redirects; a navigation bar or loading screen does not count as a successful scrape.

Browser sessions run headlessly and separately from the normal browser window, allowing collection to continue while the laptop is in use.

The July midpoint provides a consistent annual reference, while bounded retries make collection feasible across 450 observations. However, these limits may exclude recoverable historical material.

### Extraction and quality controls

Archived pages present several complications: URL migrations, corporate rebranding, JavaScript-dependent content, redirect chains, and incomplete Wayback captures.

Captures are accepted only when redirects resolve to an appropriate corporate or reviewed rebrand host within the target year; chains exceeding five hops are rejected. Browser request guards and final response checks reject live or out-of-year corporate document, script, and data content. Failed ancillary requests are audited without automatically rejecting usable corporate text. Archive donation banners, preview services, redirect screens, corporate errors, and captures containing only navigation or statistics are rejected.

Trafilatura extracts substantive body text, with a main-content fallback. Navigation, footers, archive overlays, and identifiable social-feed widgets are removed. At least 25 substantive words are required. Accepted observations are preserved across reruns unless a quality problem is identified.

These rules prioritize reliable source attribution over maximizing the number of accepted pages.

### Theme classification and wording changes

Classification uses `gpt-4o-mini-2024-07-18` to identify ten categories, consistent with the conceptual framework used in Part 2:

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

Adjacent-year comparisons require usable text from consecutive years and the same normalized source URL. HTTP/HTTPS, www, trailing slashes, and default filenames are treated as equivalent. Both comparison fields remain blank when the prior year is missing or the source page changes. After whitespace normalization:

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

Of the 450 expected observations, **181 (40.2%) remain unavailable**:

| Failure category | Company-years |
|---|---:|
| No eligible in-year capture for checked About URLs | 164 |
| Capture replay, extraction, or rendering failures | 17 |
| **Total** | **181** |

All 50 companies have at least one usable observation. The targeted recovery produced nine-year histories for Salesforce, Intel, Medtronic, and Valero, seven years for Broadcom, and eight for ConocoPhillips.

The largest challenge is that corporate websites are not historically stable. Companies redesign their websites, move values statements between pages, change domains, and sometimes consolidate or discontinue older URLs. A selected modern About Us URL may have no archived captures even when equivalent content existed elsewhere.

The pipeline searches a bounded number of candidate URLs, historical homepages, and captures. It does not exhaustively reconstruct each company's historical website architecture. Consequently, **failure to recover a page is not evidence that the page or its values statement did not exist**.

Extraction introduces further difficulties. Some archived HTML references scripts or resources that were never preserved, while other captures replay incomplete content or redirect to live pages. Browser rendering improves recovery in some cases but cannot reconstruct missing archival resources.

### Why these gaps remain

A broader recovery strategy could extend the current discovery checks through:

- Reconstructing URLs independently for every missing year, beyond the two historical homepage probes.
- Exploring archived sitemaps and more extensive redirect histories.
- Reviewing alternative capture dates within the three-attempt annual budget.
- Manually reviewing unresolved observations and using archived equivalent pages where justified.

These improvements would increase collection time and require additional verification to ensure that recovered pages remain comparable.

Collection remains **bounded and auditable**, with a recorded reason for each missing company-year. Missing years stay blank; adjacent-year text is not substituted.

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

**Coverage and selection bias.** With 59.8% coverage, the sample cannot support unrestricted longitudinal or sector-level generalizations. Comparisons should use matched observations and report sample sizes.

**Extraction.** Identifiable navigation, archive overlays, and social-feed widgets are removed, but some contact prompts or layout fragments can remain. These may affect classifications or wording-change flags.

**Page comparability.** A website redesign or shift in the location of mission statements can produce apparent changes without any substantive change in corporate priorities.

**Classification validity.** LLM categorization supports contextual interpretation but remains subject to errors. Independent human annotation and comparisons with alternative NLP methods are needed to evaluate consistency and accuracy.

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

The default command resumes the roster and skips unchanged completed companies. Explicit tickers retry their saved gaps while retaining accepted text. A change to the discovery method also reopens earlier gaps.

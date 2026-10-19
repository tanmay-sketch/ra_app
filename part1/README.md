# Part 1: Stated Values

## Findings and nontechnical summary

**220 of 450 company-years (48.9%) have usable text**, covering **45 companies**;
six have all nine years. Coverage rises from 14 companies in 2016 to 38 in 2024,
limiting historical comparisons. Of 171 comparable adjacent-year pairs, 106 differ
in wording and 65 are unchanged. Page changes need not indicate changed values.

Morgan Stanley's page expands from four named values in [2020][ms-2020] to five
in [2021][ms-2021], adding “Commit to Diversity & Inclusion.” Diversity and
belonging already appeared in 2020; this formalizes an existing emphasis rather
than proving changed conduct.

Compare matched company-years against Part 2 disclosures; inspect changed passages
before interpreting similarity scores or sector-wide trends.

## What was done and why

**Scope.** Target one English About Us, mission, values or equivalent page per year,
2016–2024, for the supplied 50-company roster: ten each in Technology, Financials,
Healthcare, Consumer Discretionary and Energy. The roster and sector labels are
treated as fixed; January 2024 S&P 500 membership and market-cap rankings were not
independently reconstructed.

### Collection

1. **Select the page.** Search official domains, reviewed historical links and,
   when needed, the homepage. Check up to three candidates with the Wayback CDX
   API. The LLM prefers company-wide commitments and broader archived coverage.
   Exclude pages limited to product, support, news or recruitment content.
   Reuse accepted URLs.

2. **Choose annual captures.** From successful HTML records, collapsed monthly,
   try the capture nearest July 1, then the earliest/latest distinct captures:
   **at most three per year**, stopping at the first usable result. Allow one
   browser replay per year for incomplete JavaScript pages. This bounds runtime.

3. **Validate and clean.** Follow at most five redirect hops; require a same-year
   archived response on the same corporate host or a reviewed rebrand host.
   Reject live/out-of-year content, errors and statistics/navigation-only pages.
   Trafilatura extracts visible body text, removing navigation, footers, controls,
   cookie notices and boilerplate. Main content is a fallback; require at least
   25 substantive words.

### Analysis

`gpt-4o-mini-2024-07-18` assigns categories and a short current-page note, citing
source-line indexes; code copies the evidence directly. Categories cover ethical
conduct, capabilities, stakeholders and wider responsibilities, using one
vocabulary across sectors:

| Category | Meaning |
| --- | --- |
| Integrity | Ethics |
| Innovation | Invention |
| Quality | Product/service excellence |
| Safety | Organizational safety/security |
| Customers | Customer/patient needs |
| Employees | Employee support |
| Inclusion | Diversity, equity and accessibility |
| Environment | Environmental impact |
| Community | Societal contribution |
| Shareholders | Shareholder value |

Labels require stated commitments, not isolated keywords or statistics.
`changed_from_prior` is **0** for identical whitespace-normalized text, **1**
for different text, and blank without comparable adjacent years. This rule is
reproducible. `text-embedding-3-small` cosine measures whole-page similarity
between comparable adjacent years.

## Gaps, assumptions and limitations

- **230 missing observations:** 170 have no eligible in-year captures for the
  selected URL, 45 have no selected URL, and 15 failed extraction/rendering checks.
  AVGO, INTC, MDT, COP and VLO are entirely missing. Each gap has a CSV reason and
  audit details. Bounded failure does not prove archive absence. No years are
  imputed.
- One capture represents a year, and equivalent pages represent stated values.
  One URL per company improves consistency but misses historical URL migrations.
  Saved text survives reruns unless an explicit quality rejection is recorded.
- Redesigns, incomplete captures, histories and video transcripts can distort
  similarity. Labels are provisional; source references verify attribution, not
  semantic correctness. `[]` means no categories assigned; blank means unavailable
  or unassessed.
- Notes summarize current pages. Paired linguistic shifts were checked
  illustratively, not comprehensively. Public statements and similarity do not
  establish actual behavior or authenticity.

## With more time

Verify the January 2024 roster/rankings; map historical URL changes for missing
years; independently review category assignments; and compare matched mission and
values sections to separate linguistic shifts from redesigns and extraction loss.

## Code, outputs and reproduction

- Code: [`../src/part1/`](../src/part1/) and [`../main.py`](../main.py).
- [`outputs/dataset.csv`](outputs/dataset.csv): one row per company-year, including
  `ticker`, `company_name`, `sector`, `year`, `page_text_clean`,
  `changed_from_prior`, `theme_categories`, `analyst_notes`, plus `snapshot_url`
  and `page_similarity_to_prior_year`.
- [`outputs/audit.jsonl`](outputs/audit.jsonl): source choices, capture attempts,
  gap reasons, extraction checks, category evidence and request counts.

Set `OPENAI_API_KEY` in the root `.env`, then run from the root:

```sh
uv sync
uv run playwright install chromium  # Once
uv run python main.py               # Resume; preserve accepted text
uv run python main.py AVGO           # Explicitly retry this company's gaps
```

[ms-2020]: https://web.archive.org/web/20200624220438id_/https://www.morganstanley.com/about-us/morgan-stanley-core-values
[ms-2021]: https://web.archive.org/web/20210731180301id_/https://www.morganstanley.com/about-us/morgan-stanley-core-values/

# Part 2: Lived Values

## Scope and coverage

Part 1 examines what companies state they value; Part 2 examines what they emphasize in recurring disclosures. I selected **DEF 14A proxy statements** because their annual regulatory structure provides comparable information on governance, executive compensation, board oversight, and shareholder matters. However, disclosed priorities are only an indirect indicator of organizational behavior.

The [dataset](outputs/dataset.csv) covers **421 of 450 company-years (93.6%)**, representing 49 companies across 2016–2024, with **360 adjacent-year comparisons**.

| Sector | Collected / Expected |
|---|---:|
| Healthcare | 88 / 90 |
| Technology | 86 / 90 |
| Financials | 86 / 90 |
| Energy | 86 / 90 |
| Consumer Discretionary | 75 / 90 |

Of 29 missing observations, nine concern Target due to SEC issuer-selection failures, ten resulted from browser timeouts, and ten from filing-verification or extraction problems. These are unresolved collection gaps, not confirmed absences of filings.

## Research decisions and measures

**Collection.** [SEC EDGAR][edgar] supplies primary documents, identifiers, and publication dates. Searches verify issuer and annual-meeting year, excluding supplements and special-meeting-only filings. At most three candidate documents are checked per missing observation. Missing years are retained rather than substituted.

**Text preparation.** HTML and native PDF text is cleaned of navigation, voting instructions, repeated margins, and numeric tables. Shareholder proposals are distinguished from company responses to avoid attributing investor demands to management. Analysis uses nonoverlapping paragraphs; scanned documents require reviewed OCR.

**Theme emphasis.** spaCy phrase matching identifies the ten Part 1 categories: Integrity, Innovation, Quality, Safety, Customers, Employees, Inclusion, Environment, Community, and Shareholders. The [vocabulary](../src/part2/themes.py) distinguishes ambiguous concepts such as product quality and audit controls.

```text
Theme share =
  words in paragraphs matching the theme
  / total analyzed words
```

A paragraph is counted once per matching theme. Themes can overlap, so shares need not sum to 100%.

**Tone.** The 1993–2025 [Loughran–McDonald dictionary][dictionary] measures positive, negative, and uncertainty vocabulary using active entries.

```text
Tone rate =
  matching word occurrences
  / total analyzed words × 1,000
```

**Wording similarity.** Adjacent proxies are compared using TF–IDF weighted cosine similarity (0–1). Lowercase unigrams and bigrams, including numbers, retain stopwords. Weights use sublinear term frequency, `1 + ln(count)`, and smoothed inverse document frequency, `1 + ln((1 + N)/(1 + df))`. The vocabulary and IDF are frozen from the initial 32 proxies to stabilize scores, at the cost of excluding unseen terms.

These methods prioritize transparent, reproducible measures over more expensive LLM-based interpretation.

## Findings: shifts around external events

I examined five events with plausible implications for corporate disclosure. An adjacent-year pair is included when:

```text
prior filing date < event date ≤ current filing date
```

For themes, changes are measured in percentage points; tone changes are differences in matches per 1,000 words. Sector averages weight each company equally.

### 1. US government transition, January 20, 2017

Across **47 matched pairs**, overall Environment emphasis declined by just 0.03 pp. Energy fell 0.53 pp, while Financials increased 0.51 pp.

The opposite sector movements suggest that a change in government did not correspond to a uniform shift in environmental disclosure. Industry-specific conditions appear important, and these small averages do not establish a policy response.

### 2. COVID-19 pandemic, March 11, 2020

Across **44 matched pairs**, Safety emphasis increased 0.57 pp, Employees increased 0.75 pp, and negative tone increased 0.43 matches per 1,000 words.

Healthcare companies showed a **1.21 pp increase in Employees emphasis**, compared with 0.43 pp in Technology and 0.58 pp in Energy. Safety increased 0.70 pp in Healthcare and 0.90 pp in Technology.

The stronger Healthcare employee-language shift is consistent with heightened workforce concerns during the pandemic. However, the measures do not establish whether the relevant passages explicitly discuss COVID-19 or whether employee protections improved.

### 3. US government transition, January 20, 2021

Across **43 matched pairs**, Environment emphasis rose 0.79 pp overall, with a particularly large **2.62 pp increase in Energy**. Consumer Discretionary increased 0.91 pp, while Healthcare and Financials showed little change (+0.07 and +0.02 pp).

Employees emphasis also increased 1.50 pp overall, reaching 3.13 pp in Consumer Discretionary.

These patterns are consistent with changing environmental and workforce disclosure priorities. However, the transition coincided with continued pandemic disruption, making it impossible to isolate government-related effects.

### 4. Russia's invasion of Ukraine, February 24, 2022

Across **44 matched pairs**, Environment emphasis rose 1.35 pp overall. The increase was especially pronounced in **Energy (+4.29 pp)** and Financials (+2.13 pp), compared with Technology (+0.13 pp).

Energy's negative-tone rate actually declined by 1.37 matches per 1,000 words, illustrating that greater thematic emphasis need not coincide with more negative language.

The sector differences are compatible with changing discussions of energy supply, environmental priorities, and geopolitical exposure. However, the Environment label does not directly measure energy security or references to the war. Passage-level review is required before making that connection.

### 5. SEC pay-versus-performance rule, August 25, 2022

Across **44 matched pairs**, Shareholders emphasis increased only **0.12 pp** overall, while uncertainty increased 0.31 matches per 1,000 words.

Energy showed the largest sector-level Shareholders increase (+0.63 pp), followed by Financials (+0.27 pp). Healthcare (-0.21 pp) and Technology (-0.12 pp) showed declines.

Despite the regulation's direct relevance to proxy statements, the theme measure shows no uniform increase. This may reflect the vocabulary's breadth, differences in disclosure composition, or the distinction between rule adoption and implementation. Applicable disclosures concern fiscal years ending on or after December 16, 2022.

### Interpretation

Across the five comparisons, **responses appear more sector-specific than universal**. Environment emphasis changed especially strongly in Energy around the 2021 transition and 2022 invasion, while Healthcare's employee-language increase around COVID was more pronounced than in several other sectors.

The findings are exploratory, not causal. Events overlap, publication dates do not identify when text was drafted, and the categories measure broad disclosure themes rather than direct references to individual events.

## Dataset schema

The [CSV](outputs/dataset.csv) contains one company–meeting-year per row, retaining missing observations with blank measures and documented explanations.

| Column | Purpose |
|---|---|
| `ticker`, `company_name`, `sector` | Company identity, fixed sector, Part 1 linkage |
| `year`, `filing_date`, `meeting_date` | Annual-meeting year and verified dates |
| `accession`, `source_url` | SEC source verification |
| `text_file` | Cleaned-text path relative to `part2/outputs/` |
| `theme_shares` | JSON shares for ten themes |
| `tone_rates` | JSON positive, negative, uncertainty rates |
| `similarity_to_prior` | Adjacent-year TF–IDF cosine |
| `analyst_notes` | Major changes, extraction warnings, missing-data reasons |

The [implementation](../src/part2/analyze.py) calculates within-company theme and tone differences before aggregation. Equal company weights prevent longer filings from dominating results. Missing comparisons remain blank, while computed zeros are preserved.

## Limitations and next steps

**Measurement validity.** Proxy statements capture governance disclosures rather than verified conduct. Phrase matching may miss context or overlabel paragraphs, and the theme categories lack independent human validation. Part 1 commitment labels are not directly equivalent to Part 2 paragraph shares.

**Comparability.** Regulatory requirements, document composition, and the frozen TF–IDF vocabulary can influence observed changes. Event windows may overlap, and no causal controls or significance tests have been applied.

**Data quality.** Fifty-one retained filings have extraction warnings, including five flagged pairs in each event comparison. Coverage is uneven across sectors, particularly Consumer Discretionary.

With additional time, I would recover missing filings, manually review flagged passages and event-related paragraphs, validate theme assignments against human annotations, and test whether findings persist within comparable proxy sections.

For Part 3, these measures provide evidence about **alignment between stated values and disclosed priorities**, rather than proof of organizational authenticity. Sector norms and measurement reliability should inform any resulting index.

## Reproduction

Code resides in [`src/part2/`](../src/part2/), with [`outputs/dataset.csv`](outputs/dataset.csv) as the tracked output. Cleaned text, audit evidence, and the frozen TF–IDF fit remain local. Exact cosine reproduction requires the original fit.

Collection requires `SEC_USER_AGENT` in `.env`. The financial dictionary is expected at `part2/work/Loughran-McDonald_MasterDictionary_1993-2025.csv`, or specified through `--dictionary`.

```sh
uv sync
uv run playwright install chromium
uv run python -m src.part2
uv run python -m src.part2 --analyze-only
```

[edgar]: https://www.sec.gov/edgar/search/
[dictionary]: https://sraf.nd.edu/loughranmcdonald-master-dictionary/

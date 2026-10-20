# Part 2 — Lived Values: Proxy Statement Analysis

## Scope, sourcing and coverage

Analyze annual **DEF 14A proxy statements** for Part 1's 50 companies, 2016–2024.
This consistent document type describes governance, incentives and reported
priorities; it does not verify conduct.

SEC provides dated primary filings and stable identifiers. Search
[EDGAR](https://www.sec.gov/edgar/search/) by issuer, filing year and form, then
follow **preview → Open document**. Retain the first complete proxy
confirming the issuer and meeting year; exclude exhibits, supplements and
special-meeting-only filings. Check the preceding filing year if needed, with
at most three candidates per missing year. Preserve successful sources on reruns.

As of **20 October 2026**, [dataset.csv](outputs/dataset.csv) contains **450 rows,
421 retained proxies (93.6%), 49 represented companies and 360 adjacent-year
comparisons**. Retained company-years by sector, each out of 90: Technology 86,
Financials 86, Healthcare 88, Consumer Discretionary 75 and Energy 86.

The 29 gaps are nine Target issuer-selection failures, ten browser timeouts and
ten document-identity/extraction failures. Reasons appear in `analyst_notes`;
failure does not establish that a filing is unavailable.

## Text preparation and method choice

Extract HTML/native PDF text; scanned pages require reviewed OCR. Remove navigation,
voting instructions, repeated margins, numeric tables and identified shareholder
proposals, retaining company responses. Use nonoverlapping narrative paragraphs.

Local spaCy phrases, financial dictionary tone and TF–IDF provide inexpensive,
inspectable measures. Ten themes align with Part 1 for later comparison:
**Integrity, Innovation, Quality, Safety, Customers, Employees, Inclusion,
Environment, Community and Shareholders**. The [phrase vocabulary](../src/part2/themes.py)
distinguishes product quality from audit controls and environmental policy from
financial sustainability.

## Dataset columns

One row represents a company–meeting-year. Uncollected source fields remain blank.

| Column | Definition and reason for inclusion |
| --- | --- |
| `ticker` | Roster identifier; joins companies to Part 1. |
| `company_name` | Readable company identity. |
| `sector` | Roster sector; supports group comparisons. |
| `year` | Annual-meeting year, verified when a proxy is retained; panel time key. |
| `filing_date` | SEC filing date; places disclosures relative to events. |
| `meeting_date` | Exact meeting date when confirmed; supports year verification. |
| `accession` | SEC filing identifier; enables source verification. |
| `source_url` | Direct primary-document URL; makes the source traceable. |
| `text_file` | Clean-text path relative to `part2/outputs/`; keeps document text outside the CSV. |
| `theme_shares` | JSON shares for all ten themes; measures paragraph-level emphasis. |
| `tone_rates` | JSON positive, negative and uncertainty occurrences per 1,000 words; adjusts for document length. |
| `similarity_to_prior` | TF–IDF cosine against the preceding meeting year; measures wording continuity. |
| `analyst_notes` | Calculated shifts, extraction warnings or gap reasons; supports interpretation and review. |

## Calculations

As implemented in [analyze.py](../src/part2/analyze.py), let $w_p$ be paragraph p's
word count and $W=\sum_p w_p$. Theme/tone words are
alphabetic sequences allowing internal apostrophes or hyphens. Missing measures
are blank; a calculated zero is valid.

**Theme shares.** A case-insensitive phrase match labels the entire paragraph:

$$
S_k=\frac{\sum_p w_p\,\mathbf{1}(p\text{ matches theme }k)}{W}.
$$

Each paragraph counts once per theme; unmatched paragraphs remain in W. Overlapping
themes can sum above 1. Shares measure paragraph emphasis, not individual value words.

**Tone rates.** Use the 1993–2025 [Loughran–McDonald dictionary](https://sraf.nd.edu/loughranmcdonald-master-dictionary/),
retaining positive membership flags and excluding removed entries. For each
category c ∈ {positive, negative, uncertainty}:

$$
R_c=1000\times\frac{\text{matching word occurrences in category }c}{W}.
$$

Count occurrences, not distinct words; negation and context are not interpreted.

**Wording similarity.** Lowercase unigrams/bigrams use scikit-learn's default
word tokens of at least two characters, including numeric tokens, without stopword
removal. This differs from theme/tone tokenization. For term j in document d:

$$
v_{dj}=(1+\ln f_{dj})\left[\ln\frac{1+N}{1+df_j}+1\right],\qquad
C_{it}=\frac{v_{it}\cdot v_{i,t-1}}{\|v_{it}\|_2\|v_{i,t-1}\|_2}.
$$

Here f is term frequency, df document frequency and N fit-corpus size; absent
terms have zero weight. Vocabulary/IDF remain frozen from the initial 32 proxies;
unseen terms are ignored. Cosine ranges from 0 to 1; higher means more similar
wording. Missing adjacent years or empty vectors leave cosine blank.

**Changes and aggregation.** Theme changes are $100(S_{itk}-S_{i,t-1,k})$
percentage points; tone changes are $R_{itc}-R_{i,t-1,c}$. Notes list up to two
largest theme changes reaching 1 point and the largest tone change reaching 0.1
matches/1,000 words. These are reporting cutoffs, not significance tests.

For measure m, sector means give each available company equal weight:

$$
\bar m_{st}=\frac{1}{|A_{st}|}\sum_{i\in A_{st}}m_{it},\qquad
\Delta\bar m_{st}=\frac{1}{|B_{st}|}\sum_{i\in B_{st}}(m_{it}-m_{i,t-1}).
$$

A contains available companies; B contains those available in both adjacent years.
Sample counts are reported; membership may change across year pairs.

## Observed differences and event comparisons

- **Within company:** Microsoft's Safety share rose from 3.94% in 2023 to 10.01%
  in 2024; wording cosine was 0.758.
- **Across sectors:** 2024 Environment shares averaged 9.09% in Energy versus
  2.04% in Healthcare, with ten companies in each sector.
- **COVID-19:** 44 adjacent filing pairs spanning the
  [11 March 2020 pandemic announcement](https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020)
  showed mean Safety emphasis +0.57 percentage points and negative tone
  +0.43 matches/1,000 words.
- **Disclosure regulation:** 44 pairs spanning the
  [25 August 2022 pay-versus-performance rule adoption](https://www.sec.gov/newsroom/press-releases/2022-149)
  showed Shareholders emphasis +0.12 points and uncertainty +0.31 matches/1,000.
  The rule applies to relevant disclosures for fiscal years ending on or after
  16 December 2022; adoption and application dates differ.

Event pairs satisfy `prior_filing_date < event_date <= current_filing_date`.
Intervals include unrelated changes and potentially text prepared before the event;
coincidence does not establish causality.

## Limitations and next steps

Phrase labels lack independent validation and may miss paraphrases or overlabel
long paragraphs. Proxies emphasize governance/pay, while redesigns and disclosure
rules affect comparability. **51 retained rows carry extraction warnings**; each
event sample includes five flagged pairs. Gaps and the fixed vocabulary also limit
interpretation.

Only the CSV is tracked; text, audit evidence and the frozen fit remain local.
Exact cosine reproduction requires that fit. Next: review flagged passages/gaps,
validate labels independently, and compare consistent sections and company samples.

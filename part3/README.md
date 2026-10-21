# Part 3: Organizational Authenticity Index

## Research objective and findings

This part develops an **annual Organizational Authenticity Index** to examine how closely companies' stated values match the priorities discussed in their proxy statements.

The index combines two measures:

- **Value Alignment:** Does a company give attention to the values it publicly claims to prioritize?
- **Identity Coherence:** Does the company maintain a reasonably consistent mix of priorities over time, or repeatedly return to earlier patterns?

Together, these measures capture consistency in corporate communication. They do not prove that a company behaves according to its stated values.

The [dataset](outputs/dataset.csv) includes all **450 company-year observations** from 2016 to 2024, including missing data.

| Available evidence | Company-years |
|---|---:|
| Both components (complete index) | **153** |
| Alignment only | 58 |
| Coherence only | 95 |
| Neither | 144 |

The **153 complete scores cover 44 companies**. Complete coverage increases from 20 companies in 2019 to 30 in 2024. Earlier years cannot receive complete scores because coherence requires at least four consecutive years of proxy data.

Across the complete observations, the index has a **mean of 68.59**, median of **70.38**, standard deviation of **10.14**, and range of **20.32–90.00**. These statistics describe company-year observations, so companies appearing in multiple years are counted more than once. Differences in data availability also limit direct comparisons between years.

## How the index is calculated

### 1. Value Alignment

Part 1 identifies the values each company publicly states. Part 2 measures how much attention those themes receive in its annual proxy statement.

For each stated value, the company's proxy theme share is compared with the average share among other companies in the same sector and year.

```text
Benchmark = max(peer average theme share, 0.005)

Theme support = company theme share
                / (company theme share + benchmark)

Value Alignment = 100 × average support
                  across stated values
```

A company receives a theme support score of 50 when its share matches the peer average, provided the minimum benchmark does not apply. Greater emphasis produces a higher score, while no matching discussion produces zero.

Each peer company receives equal weight. At least five peers with usable data are required, and the company being scored is excluded from its own benchmark. Peers do not need Part 1 observations.

Only publicly stated themes are included. Companies are not penalized simply for discussing other priorities. Missing statements and statements with no identified themes cannot receive alignment scores.

### 2. Identity Coherence

Coherence examines whether a company's disclosed priorities repeatedly shift back toward earlier patterns.

Each annual proxy is represented by the same ten-theme profile used in Part 2. The difference between consecutive years is measured using **1 minus cosine similarity**.

A change is considered substantial when its distance is at least **0.0760373**, the 75th percentile of the 360 observed consecutive-year changes.

A reversal occurs when:

- The company makes two substantial changes across three consecutive years (A → B → C).
- The profile in year C is closer to A than either adjacent comparison, indicating a return toward the earlier pattern.

```text
Identity Coherence =
100 × (1 - reversals / eligible three-year windows)
```

The calculation uses all eligible, overlapping three-year windows in the company's uninterrupted history, ending in the year being scored. At least four consecutive years of usable data are required. Missing years or profiles with no detected themes interrupt the history.

A score of 100 means no qualifying reversals were detected. Importantly, a company can make a lasting change without being penalized. The measure focuses on repeated backtracking, not change itself.

### 3. Final index

```text
Authenticity Index =
(Value Alignment + Identity Coherence) / 2
```

Both components receive equal weight. This is a simple, transparent choice rather than a statistically optimized weighting scheme.

**A complete score is calculated only when both components are available in the same year.** Missing components are never replaced with zero or estimated values.

## Reliability checks and limitations

I tested how sensitive the index is to its main assumptions by:

- Changing the component weights to 70/30 and 30/70.
- Testing the 60th and 90th percentiles instead of the 75th for substantial changes.
- Changing the minimum alignment benchmark from 0.005 to 0.001 and 0.01.
- Excluding observations with extraction warnings and recalculating the affected measures.

Comparisons use the same company-years with complete scores under both settings, and changes in coverage are reported separately.

**The main limitation is that the index measures disclosure patterns, not actual behavior.** Some words may be matched to a theme even when they appear in unrelated contexts. For example, NVIDIA's stock-plan appendices influence its measured priorities, potentially creating misleading changes.

Coherence also has limited ability to distinguish companies: **195 of 248 eligible observations score 100**. This means the absence of detected reversals is common and should not be interpreted as proof of authenticity.

Other limitations include incomplete historical About pages, changes in page content, repeated proxy language, and differences in filing structure. Coherence scores also reuse earlier observations, so annual scores are not independent. Because the method uses information from the full study period and some About-page captures occur after proxy filings, the index is retrospective rather than predictive.

### Realistic improvements

With more time, I would prioritize three improvements:

1. **Check a small sample of theme matches.** Manually review approximately 40–50 selected proxy paragraphs, especially unusual matches and extreme scores, to identify common classification errors.
2. **Improve ambiguous keyword rules.** Refine the matching vocabulary to exclude procedural language and misleading contexts identified during those checks, then examine how the affected scores change.
3. **Test more comparable document sections.** Repeat the analysis on a smaller sample using similar proxy sections to see whether differences in document structure influence the results.

These targeted checks would help improve measurement quality without requiring a manual review of every company's reports.

## Dataset and reproduction

[`outputs/dataset.csv`](outputs/dataset.csv) contains one row per company-year, with the following fields:

| Columns | Description |
|---|---|
| `ticker`, `company_name`, `sector`, `year` | Company and year identifiers |
| `value_alignment`, `identity_coherence` | Annual component scores |
| `authenticity_index`, `score_basis` | Complete index and available evidence |
| `identity_change`, `transition_status` | Size and type of change in disclosed priorities |
| `valid_transition_count`, `reversal_count` | History used to calculate coherence |
| `part1_available`, `part2_available`, `stated_theme_count` | Source coverage and number of stated themes |
| `quality_flags`, `analyst_notes` | Data-quality issues, missingness, and interpretation notes |

The [implementation](../src/part3/) uses the existing Part 1 and Part 2 datasets without modifying them or making additional API requests.

```sh
uv sync
uv run python -m src.part3
uv run python -m unittest src.part3.test_index
```
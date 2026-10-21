# Part 3: Organizational Authenticity Index

The index combines support for stated values with consistency in disclosed
priorities. Each observation represents one company-year, capturing variation
across companies and over time from 2016–2024.

## Dataset and coverage

The [dataset](outputs/dataset.csv) retains all 450 company-years, including gaps.

| Evidence available | Company-years |
|---|---:|
| Both components | 153 |
| Alignment only | 58 |
| Coherence only | 95 |
| Neither component | 144 |

Only rows with **both components** receive an `authenticity_index`.
Single-component rows retain **partial evidence**, not comparable authenticity
estimates. Missing values remain blank; genuine zeros remain zero.

The 153 complete observations span 44 companies. Coverage varies by year:
20 companies have complete scores in 2019 and 30 in 2024.

## Calculations and decisions

### Value alignment

Part 1 identifies stated themes; Part 2 measures their emphasis in proxy statements.
For each stated theme:

```text
benchmark = max(other sector-year companies' mean theme share, 0.005)
support = company theme share / (company theme share + benchmark)
alignment = 100 × mean support across stated themes
```

The focal company is excluded and at least five usable peers are required.
Sector-year benchmarks account for differences in disclosure composition; the
floor prevents tiny benchmarks from exaggerating support. Peer-average support
scores 50 when the floor does not bind. Only stated themes enter the average:
discussing other priorities is not inherently contradictory. Empty theme lists
supply no alignment target, and missing statements are not carried forward.

### Identity coherence

Annual change is `1 − cosine similarity` between consecutive ten-theme proxy
profiles. A substantial move meets the pooled 75th-percentile distance cutoff:
**0.0760373** across 360 adjacent-year pairs.

For consecutive profiles A, B and C, a reversal requires two substantial moves
and `distance(A, C) < min(distance(A, B), distance(B, C))`.

```text
coherence = 100 × (1 − reversals / eligible three-year windows)
```

Each score uses the uninterrupted history ending that year, requiring **four
consecutive usable years**. Missing years and all-zero profiles reset the history.
Coherence and the annual composite are therefore unavailable in 2016–2018;
2019 is the earliest eligible year. Lasting changes are allowed: this component
measures backtracking, rather than penalizing every shift in priorities.

### Annual composite

```text
annual index = (annual alignment + annual coherence) / 2
```

Both components must exist for the same company-year. Equal weights keep the
dimensions equally influential without claiming an empirically optimal weighting.
Years with missing components receive no substitute composite.

## Columns

| Column | Meaning |
|---|---|
| `ticker`, `company_name`, `sector` | Fixed company identity |
| `year` | Observation year, 2016–2024 |
| `value_alignment`, `identity_coherence` | Annual component scores; 0–100 |
| `authenticity_index` | Equal-weight composite; blank unless both components exist |
| `score_basis` | `both`, `alignment_only`, `coherence_only`, or `unavailable` |
| `quality_flags`, `analyst_notes` | JSON list of source/timing/coverage limitations and their explanation |
| `identity_change` | Cosine distance from the immediately preceding proxy profile; 0–1 |
| `transition_status` | Latest pattern: stable, reversal, sustained transition, provisional change, or insufficient history |
| `part1_available`, `part2_available` | Completed statement assessment and usable proxy measures, respectively; 1/0 |
| `stated_theme_count` | Number of assessed stated themes; blank if unassessed |
| `valid_transition_count` | Adjacent transitions in the uninterrupted proxy history |
| `reversal_count` | Reversals in that history; blank before coherence is eligible |

## Findings and limitations

Coherence equals 100 in **195 of 248 eligible company-years**, limiting discrimination.
A score of 100 means no qualifying reversals were detected, not proven authenticity.

Sensitivity checks vary weights (70/30 and 30/70), change cutoffs (60th and 90th
percentiles), and benchmark floors (0.001 and 0.01), and exclude extraction
warnings. Comparisons match the same company-years with both components in
both scenarios; lost coverage is counted separately. Changing coverage means
yearly distributions need not represent the same companies.

Sparse statements, changing page scope, duplicated proxy text and context-insensitive
keyword matches limit interpretation. Targeted checks found stock-plan appendices
affecting NVIDIA's theme mix; its low score is not evidence of poor conduct.
Comparable proxy sections and broader manual validation would improve the measure.
Histories overlap, calibration uses the full period, and About captures can follow
proxy filings. Scores describe communication retrospectively; they do not establish
conduct or causality.

## Reproduction

The [code](../src/part3/) reads the current Part 1 and Part 2 CSVs without modifying
them or making network/model requests. Improved coverage can change scores.

```sh
uv sync
uv run python -m src.part3
uv run python -m unittest src.part3.test_index
```

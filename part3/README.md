# Part 3: Organizational Authenticity Index

Part 3 produces **one score per company for 2016–2024**, using its available
observations. The two components are averaged separately over time, then combined
with equal weights. Missing years and missing components are never treated as zero.

The [dataset](outputs/dataset.csv) retains all 50 companies:

| Evidence supporting the score | Companies |
|---|---:|
| Both component averages | 41 |
| Alignment average only | 1 |
| Coherence average only | 7 |
| Neither component available | 1 |

This gives **49 available scores**. Apple has alignment evidence but insufficient
consecutive proxy history for coherence. Broadcom, Intel, Medtronic, McDonald's,
Starbucks, ConocoPhillips and Valero have coherence evidence without usable
alignment scores. Target remains blank.

## Averaging rule

```text
company alignment = average of available annual alignment scores
company coherence = average of available annual coherence scores

both available: company score = (alignment + coherence) / 2
one available:  company score = that component's average
none available: company score = blank
```

For example, alignment scores of 50 and 70 average to 60. Coherence scores of
80, 90 and 100 average to 90. The company score is `(60 + 90) / 2 = 75`.
This gives each component equal weight despite different numbers of observed
years. Averaging all five annual values together would instead give coherence
more weight simply because it has more observations.

The `score_basis` column identifies `both`, `alignment_only`, `coherence_only` or
`unavailable`. A single-component score remains useful but does not establish
both dimensions. In particular, a coherence-only score of 100 does not show
perfect alignment with stated values. Comparisons should use the same score basis.

**Alignment already uses both source datasets.** Part 1 supplies the stated themes;
Part 2 supplies their disclosure support. Part 1 alone does not contain a numerical
authenticity score. No substitute score is invented by counting how many values
a company claims to hold.

## Component calculations

### Value Alignment

For each theme assigned to the company's Part 1 statement in a given year:

```text
benchmark = max(mean theme share among other sector-year companies, 0.005)
theme support = company theme share / (company theme share + benchmark)
annual alignment = 100 × average support across stated themes
```

Sector-year peers account for differences in proxy composition. Companies receive
equal weight, the focal company is excluded, and at least five usable peers are
required. The floor prevents tiny peer shares from producing exaggerated support;
it binds in 32 of 639 stated-theme comparisons. A score of 50 means peer-average
support when the floor does not bind. Observed zero support remains zero.

Only stated themes enter the average: discussing other legitimate priorities is
not inherently contradictory. Overlapping proxy theme shares need not sum to one.
An assessed empty theme list supplies no alignment target and remains distinct
from an unavailable assessment. Missing statements are not copied from another year.

There are **172 annual alignment observations across 42 companies**. Their company
averages use one to nine observed years; `alignment_years` makes that support visible.

### Identity Coherence

Annual change is `1 − cosine similarity` between consecutive ten-theme proxy
profiles. Cosine compares the relative mix of themes. Missing years and all-zero
profiles interrupt the history.

A substantial move has distance at least **0.0760373**, the pooled 75th percentile
of 360 valid adjacent-year distances. Linear quantiles, equality at the cutoff
and a minimum threshold of 0.00000001 handle ties and completely stable data.

For consecutive profiles A, B and C, a reversal requires two substantial adjacent
moves and a return toward A:

```text
distance(A, C) < min(distance(A, B), distance(B, C))
annual coherence = 100 × (1 − reversals / eligible three-year windows)
```

Each annual score uses the uninterrupted history ending in that year, with at least
four consecutive years. A→A→A→A and A→A→B→B score 100; A→B→A→A scores 50;
A→B→A→B scores 0, provided A and B are substantially different. A lasting change
is therefore allowed. This specifically measures backtracking, rather than every
form of instability.

The company component averages its eligible annual coherence scores. These
histories overlap, so the observations are not independent and early reversals
can affect several later scores. There are **248 annual coherence observations
across 48 companies**; the earliest eligible year is 2019.

## Findings and source checks

Among the **41 companies with both components**, the average combined score is
**68.1**. Illustrative company scores are Amazon **87.0**, JPMorgan Chase **51.8**
and NVIDIA **14.4**. These summarize available period evidence rather than provide
complete annual histories or a validated ranking of corporate conduct.

Coherence reaches 100 for **35 of 48 company averages**, limiting discrimination.
The seven coherence-only companies average 95.9, illustrating why their scores
should not be pooled into a ranking with the two-component companies.

Source checks against existing About-page evidence and proxy paragraphs show
both useful matches and measurement problems:

- **Amazon:** employee commitments correspond to proxy discussions of wages and
  tuition support. However, repeated human-capital paragraphs and residual
  shareholder-proposal language can increase measured emphasis.
- **JPMorgan Chase:** passages discuss conduct training and inclusion, supporting
  the stated themes. Lower coherence reflects earlier reversals, even where later
  annual patterns are more consistent.
- **NVIDIA:** alternating stock-plan appendices add a different mix of matched
  themes. Possible compensation criteria and a director's Environmental Engineering
  title show how keyword matches can produce apparent priorities and reversals.

These were targeted checks, not independent validation of all theme labels.

## Sensitivity and limitations

Sensitivity analysis varies component weights
(70/30 and 30/70), the change percentile (60th and 90th), and the benchmark floor
(0.001 and 0.01). It also excludes extraction warnings and recomputes annual
peer benchmarks, histories and company averages.

Comparisons use companies available under both scenarios **with the same score
basis**. Rank correlations use only companies with both components in both
scenarios. Lost coverage and changes in basis are reported separately. For a
single-component company, changing the relative component weights does not change
its score: the available weight is normalized to one.

Changing the benchmark floor moves company scores by only 0.12–0.18 points on
average. Changing the reversal percentile moves them by 1.69–2.00 points on
average, with individual changes as large as 26.55 points. Excluding extraction
warnings leaves 44 scored companies: five lose their scores and three change basis.
Among the 41 remaining companies with unchanged basis, the average absolute change
is 0.66 points.

The index measures consistency in corporate communication, not verified conduct.
Sparse statement coverage, changing declaration scope, proxy composition and
context-insensitive matches limit interpretation. A one-year alignment average
has less supporting evidence than a multi-year average, even when their numbers
are similar.

The component averages can also cover different sets of years. The full-period
summary is retrospective: calibration uses the full study period, and in 184 of
204 jointly available annual observations the About-page capture follows the
proxy filing. These scores should not be treated as information available at the
start of the period or used predictively without past-only recalculation.

Further work should standardize comparable proxy sections, remove residual proposal
and duplicate text, and validate thematic matches before making stronger claims.

## Dataset and reproduction

| Column | Meaning |
|---|---|
| `ticker`, `company_name`, `sector` | Fixed company identity |
| `value_alignment` | Mean available annual alignment, 0–100 |
| `identity_coherence` | Mean available annual coherence, 0–100 |
| `authenticity_index` | Average of available component means, 0–100 |
| `score_basis` | Both components, alignment only, coherence only, or unavailable |
| `part1_years` | Years with completed Part 1 assessments, including assessed empty themes |
| `part2_years` | Years with usable proxy theme measures |
| `alignment_years` | Annual scores entering the alignment average |
| `coherence_years` | Annual scores entering the coherence average |
| `quality_flags` | JSON list of source, timing and company-level evidence limitations |
| `analyst_notes` | Coverage and explanation of partial or unavailable scores |

The [code](../src/part3/) uses existing dependencies and makes no network or model
requests. It calculates scores from the Part 1 and Part 2 CSVs without modifying
them. Rerunning uses the current inputs, so improved source coverage can change scores.

```sh
uv sync
uv run python -m src.part3
uv run python -m unittest src.part3.test_index
```

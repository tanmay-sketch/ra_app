# Part 4: Disclosure Profiles

**Research question:** Do companies exhibit distinct patterns of disclosed
priorities, and do they move between those patterns over time?

Clustering provides an exploratory extension of the authenticity index. Groups
are discovered from disclosure features, then compared with sector membership
and available Part 3 scores. The aim is to examine whether the features reveal
shared priorities or mainly reflect reporting conventions.

## Features and method

The analysis uses **421 company-years from 49 companies**, covering 2016–2024.
The [dataset](outputs/dataset.csv) retains all 450 expected observations; 29
without usable proxy measures have blank cluster assignments. Zero theme
profiles would also remain unassigned.

The ten features are Part 2's shares for Integrity, Innovation, Quality, Safety,
Customers, Employees, Inclusion, Environment, Community and Shareholders:

```text
theme share = words in paragraphs matching a theme / all analyzed words
normalized profile = ten-theme vector / its Euclidean length
```

A whole paragraph contributes to every theme it matches, so shares can overlap.
These features capture **relative coverage of theme-matched paragraphs**, not
the frequency of individual theme words. Normalization emphasizes the mix of
priorities and removes overall thematic intensity: two filings with proportional
profiles receive the same input even if one contains much less relevant text.
Columns are not standardized, avoiding automatic amplification of rare themes.

[K-means](https://sklearn.org/stable/modules/generated/sklearn.cluster.k_means.html)
is fitted for 2–5 clusters using Euclidean distance. Each candidate uses ten
fixed seeds, each with 20 initializations; the lowest-inertia fit represents that
candidate. The highest mean [silhouette](https://sklearn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html)
selects the final partition. Sector, year, company identity, tone and authenticity
scores are excluded from fitting. Cluster numbers indicate descending size, not rank.

## Preliminary findings

Five clusters have the highest silhouette, **0.234**, compared with 0.227, 0.223
and 0.222 for two, three and four clusters. Separation is modest, and the small
advantage does not establish five natural organizational types. Twelve assigned
observations have negative individual silhouettes, indicating ambiguous boundaries.

| Cluster | Descriptive emphasis | Company-years | Available Part 3 scores | Median index |
|---|---|---:|---:|---:|
| C1 | Shareholders | 139 | 37 | 63.4 |
| C2 | Employees and Inclusion | 124 | 50 | 72.6 |
| C3 | Environment, alongside Shareholders and Safety | 75 | 34 | 69.3 |
| C4 | Innovation and Customers, alongside Shareholders | 74 | 26 | 72.2 |
| C5 | Community/Inclusion matches; Berkshire Hathaway only | 9 | 6 | 57.2 |

These descriptions follow the fitted profiles; they were not supplied as labels.

![Mean normalized theme weights for the five disclosure clusters](outputs/profiles.png)

Each row is a cluster; `n` counts company-year observations. Darker cells indicate
greater relative emphasis. Weights are averaged after normalizing each profile;
they are not percentages of document text or probabilities.

The most informative result is **a measurement problem exposed by C5**. All nine
observations are Berkshire Hathaway filings. Reviewing its
[2016](https://www.sec.gov/Archives/edgar/data/1067983/000119312516501649/d117328ddef14a.htm)
and [2024](https://www.sec.gov/Archives/edgar/data/1067983/000119312524069107/d512828ddef14a.htm)
proxies shows that Inclusion matches include procedural wording about
“inclusion in the proxy statement” and a committee that “does not seek diversity.”
Here, procedural inclusion concerns publishing proposals in the document;
it does not mean financial inclusion or access to banking and credit.
Community matches largely concern directors' charitable-foundation backgrounds.
Recalculation reproduces the stored shares exactly, but these passages do not
establish affirmative corporate commitments. A distinct cluster can therefore
reflect lexical ambiguity and document structure rather than distinctive values.
This limitation originates in [Part 2's theme extraction](../part2/README.md#limitations-and-next-steps),
before the features reach the clustering analysis.

C3 is sector-related: **56 of 75 observations are Energy filings**. Overall
adjusted Rand agreement with sector labels is 0.144: the clusters do not simply
reproduce sector labels.

Companies switch clusters in **96 of 360 adjacent-year comparisons (26.7%)**,
involving 40 companies. Gaps are not bridged. These switches describe changes
relative to a fixed, full-period partition; they need not represent changes in
conduct or the same magnitude of thematic movement.

Part 3 comparisons use only its 153 complete annual scores. Their differing
cluster medians are descriptive: coverage is uneven, and theme shares also enter
the index's construction. They cannot independently validate authenticity or
establish that one disclosure profile is better.

## Evaluation and limits

Across the ten seeds, the selected partition's mean adjusted Rand agreement is
**0.930**, with a minimum of **0.869**. Four clusters are more initialization-stable
(mean 0.999), despite their slightly lower silhouette. Excluding 51 extraction-warning
filings and refitting five clusters gives **0.954 agreement** on the 370 retained
observations. Numerical stability supports reproducibility, not the validity of
the categories or the existence of genuine groups.

The features impose important limits:

- **Context:** Inclusion combines board diversity and workforce inclusion; Safety
  combines physical safety, cybersecurity and privacy. Phrase matching does not
  establish stance, sincerity, negation or implementation.
- **Evidence:** Attention to a theme does not measure concrete commitments,
  resources allocated, progress or independently verified outcomes. Sparse Quality
  matches may reflect the purpose of proxy statements rather than low concern
  for product quality.
- **Comparability:** Templates, duplicated passages and residual proposal language
  can influence profiles. Repeated observations represent 49 companies, not 421
  independent organizations; companies with more available years contribute more
  to the fit. K-means also imposes a partition even when separation is weak.

The immediate priority is passage-level validation: exclude procedural uses,
resolve negation, and distinguish director backgrounds from company actions.
Additional features should separate board from workforce inclusion and digital
from physical safety; distinguish actions from aspirations; and capture targets,
deadlines, expenditure and achieved outcomes. Behavioral claims would also need
independent evidence. Adding dimensions alone would not establish validity.

## Dataset schema

Each row represents one company and proxy meeting year. The CSV combines the
original theme features, clustering results and existing Part 3 comparison
fields. It does not calculate another authenticity score. All 450 rows remain,
including years without a cluster; a missing Part 3 score does not prevent clustering.

| Column | Meaning and use |
|---|---|
| `ticker` | Company identifier used to join Parts 2 and 3. Together with `year`, uniquely identifies a row. |
| `company_name` | Company name from the fixed study roster. |
| `sector` | One of the five study sectors; used to interpret clusters, not to fit them. |
| `year` | Proxy meeting year, 2016–2024; used to track changes within a company. |
| `theme_shares` | JSON object containing the ten original Part 2 shares, each between 0 and 1. For example, 0.05 means 5% of analyzed words occur in matching paragraphs. Shares overlap and need not sum to 1. These are the only clustering features; normalization happens during fitting. Blank when unavailable. |
| `cluster` | Integer assignment, 1–5 in this run. IDs are numbered by decreasing cluster size, not authenticity. Blank for missing or all-zero profiles. |
| `cluster_silhouette` | Fit to the assigned cluster relative to the nearest alternative, from −1 to 1. Near 1 indicates better separation; near 0 indicates overlap; negative values indicate greater similarity to another cluster. Not a confidence probability; blank when unassigned. |
| `cluster_changed_from_prior` | 1 when the cluster differs from the immediately preceding year's, 0 when unchanged. Blank for the first year or if either year is unassigned; gaps are never bridged. |
| `authenticity_index` | Existing Part 3 score, 0–100; blank unless both components are available. Joined after clustering for descriptive comparison. |
| `score_basis` | Part 3 evidence: `both`, `alignment_only`, `coherence_only` or `unavailable`. Describes the index's coverage, not the clustering result. |
| `quality_flags` | JSON list of profile issues: `part2_missing`, `zero_theme_profile` or `part2_extraction_warning`. An empty list means no recorded flag, not independently verified quality. |

Blank numeric fields indicate missing or inapplicable values; they are not zeros.

## Reproduction

The [code](../src/part4/) uses the current Part 2 and Part 3 CSVs without modifying
them or making network/LLM requests. Saved results use scikit-learn 1.9.1.

```sh
uv sync
uv run python -m src.part4
```

# Part 4: Disclosure Profiles

## Research question and contribution

**Do firms exhibit recurring patterns of disclosed priorities, and do they move between these patterns over time?** Rather than assume that one sector or one authenticity score defines corporate identity, this exploratory analysis clusters the *relative mix* of themes appearing in annual proxy statements. It then examines cluster composition, transitions, and descriptive differences in the Part 3 index.

The key finding is methodological: one apparently distinct cluster largely exposes **ambiguous theme matching**, not a validated organizational type. This is useful evidence about the measurement pipeline and the limits of inferring corporate values from disclosure language.

## Method and research choices

The input comprises **421 usable company-years from 49 companies**, 2016-2024. Each observation is a ten-theme vector of Part 2 proxy paragraph shares: Integrity, Innovation, Quality, Safety, Customers, Employees, Inclusion, Environment, Community, and Shareholders. The vector is divided by its Euclidean norm before clustering. This emphasizes the *relative mix* of matched themes, not the total share of a document discussing them. Theme shares can overlap because one paragraph may match several themes. The ten columns are not individually standardized, avoiding automatic amplification of rare categories.

K-means is estimated for **2-5 clusters** using Euclidean distance, seeds 0-9 per candidate, and 20 initializations per seed. The lowest-inertia fit represents each candidate; its average silhouette across observations selects the number of clusters, with ties favoring fewer clusters. One pooled partition covers all years. Company, sector, year, tone, and authenticity are **not fitting features**. Cluster identifiers are ordered by decreasing size and imply neither quality nor authenticity.

## Preliminary findings

Five clusters achieve the highest silhouette (**0.234**), but separation is modest: two, three, and four clusters score 0.227, 0.223, and 0.222, respectively. Twelve observations have negative individual silhouettes. The small improvement over four clusters does not establish five genuine corporate archetypes.

| Cluster | Dominant matched emphasis | Company-years | Complete Part 3 scores | Median index |
|---|---|---:|---:|---:|
| C1 | Shareholders | 139 | 37 | 63.4 |
| C2 | Employees and Inclusion | 124 | 50 | 72.6 |
| C3 | Environment, with Shareholders and Safety | 75 | 34 | 69.3 |
| C4 | Innovation and Customers, with Shareholders | 74 | 26 | 72.2 |
| C5 | Community and Inclusion matches | 9 | 6 | 57.2 |

![Mean normalized theme weights across disclosure clusters](outputs/profiles.png)

The figure reports **mean normalized weights**, not shares of all proxy words or probabilities. C3 is substantially associated with Energy: 56 of its 75 observations come from that sector. Yet the adjusted Rand agreement between clusters and sector labels is only **0.144**, so clusters do not simply reproduce the sector classification.

**C5 contains all nine Berkshire Hathaway observations and no other companies.** Examination of its 2016 and 2024 proxy passages shows why caution is necessary. Some Inclusion matches refer to *including shareholder proposals in a proxy statement* or to a committee that *does not seek diversity* in director selection. Community matches often reflect directors' charitable-foundation biographies. These terms occur in source text, but the passages do not establish affirmative corporate commitments. Reproducing the theme shares does not resolve the underlying semantic error. Here, clustering makes a weakness of Part 2's matching method visible.

Companies change cluster in **96 of 360** valid adjacent-year comparisons (26.7%), across 40 companies; gaps are never bridged. The Part 3 medians above use only 153 complete company-year scores and are descriptive. Theme shares also enter Part 3's alignment component, so such comparisons cannot independently validate the index.

## Stability, limitations, and next steps

Comparing each seed's partition with the lowest-inertia reference gives mean adjusted Rand agreement **0.930** (minimum 0.869). Four clusters are more initialization-stable (mean 0.999). Removing 51 filings whose Part 2 notes flag extraction review and refitting the selected five clusters gives **0.954** agreement on the 370 retained observations. These checks support computational stability, **not** the substantive reality of the groups.

Phrase matching does not consistently distinguish endorsement from negation, procedural text from substantive priorities, or biographies from company actions. Section templates, duplicate wording, and regulations shape the features. The 421 observations are repeated filings from only 49 companies, not independent organizations, and K-means partitions even weakly separated data. The practical next step is passage-level validation and extraction from comparable proxy sections, followed by features that distinguish concrete actions, targets, and outcomes from aspirational or procedural language.

## Output schema and reproduction

[`outputs/dataset.csv`](outputs/dataset.csv) retains all 450 company-years; 29 lack usable profiles and have blank clusters. Fitting requires a nonzero theme profile and a text reference; a missing Part 3 score does not prevent clustering. `ticker`, `company_name`, `sector`, `year` identify observations; `theme_shares` holds the original JSON features; `cluster`, `cluster_silhouette`, and `cluster_changed_from_prior` describe assignments and adjacent-year transitions; `authenticity_index` and `score_basis` carry Part 3 information solely for post-fit comparison; and `quality_flags` identifies missing, all-zero, or extraction-warning profiles. Blank numeric values are not zeros.

The pipeline in [`src/part4/`](../src/part4/) reuses Parts 2 and 3 without network or LLM requests. Saved results use scikit-learn 1.9.1.

```sh
uv sync
uv run python -m src.part4
```

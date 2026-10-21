# Part 3: Organizational Authenticity Index

## Research objective and findings

This part constructs an **annual, company-level index of alignment between stated values and disclosed priorities**, combining Part 1 About-page themes with Part 2 proxy-statement theme shares. A second component captures whether the mix of disclosed priorities repeatedly reverses direction. The index is best interpreted as a measure of *consistency in corporate communication*, not verified organizational conduct.

The dataset includes all **450 company-years** from 2016-2024. An `authenticity_index` is reported only where **both components exist in the same company-year**:

| Evidence available | Company-years |
|---|---:|
| Both components: complete index | **153** |
| Alignment only | 58 |
| Coherence only | 95 |
| Neither | 144 |

The 153 complete observations span **44 companies**. The number of complete scores rises from 20 companies in 2019 to 30 in 2024; coherence cannot be calculated in 2016-2018 because it needs four consecutive years of usable proxy data. No missing value is interpreted as zero, and single-component results remain partial evidence rather than substitute authenticity scores.

Across complete company-year observations, the index has a mean of **68.59**, median **70.38**, standard deviation **10.14**, and observed range **20.32-90.00**. These are pooled annual observations, not independent companies, and changing annual coverage makes direct year-to-year comparisons sensitive to sample composition. In **195 of 248** eligible coherence observations, coherence equals 100, indicating limited discrimination in that component.

## Index construction and assumptions

**Value alignment** asks whether a company's disclosed emphasis supports each theme it explicitly states. For company `i`, theme `t`, and year `y`:

```text
benchmark(t,y) = max(mean proxy theme share of other sector-year firms, 0.005)
support(i,t,y) = theme_share(i,t,y) / (theme_share(i,t,y) + benchmark(t,y))
alignment(i,y) = 100 * mean(support over company i's stated themes)
```

Each peer receives equal weight; the focal company is excluded, and at least five usable sector-year peers are required. Only *stated* themes enter the average, so discussing additional legitimate priorities is not automatically penalized. A benchmark-matched share scores 50 where the floor does not bind; zero observed support scores zero. An empty or unavailable stated-theme assessment cannot yield alignment.

**Identity coherence** measures backtracking in ten-theme proxy profiles. Adjacent-year change is `1 - cosine_similarity`. A substantial move is at least **0.0760373**, the pooled 75th-percentile distance among 360 valid adjacent-year transitions. For three consecutive profiles `A, B, C`, a reversal requires substantial `A->B` and `B->C` moves and `distance(A,C) < min(distance(A,B), distance(B,C))`.

```text
coherence(i,y) = 100 * (1 - reversals / eligible three-year windows)
authenticity_index(i,y) = (alignment(i,y) + coherence(i,y)) / 2
```

Coherence uses uninterrupted history ending in the target year, with at least four consecutive usable years; a gap or all-zero profile resets it. This operationalization permits lasting change and penalizes only qualifying returns toward an earlier profile. The composite weights alignment and coherence equally as a transparent modeling choice, not an empirically estimated optimum.

## Checks, threats to validity, and improvements

Sensitivity checks vary component weights (70/30 and 30/70), the substantial-change threshold (60th and 90th percentiles), and the alignment benchmark floor (0.001 and 0.01). They also exclude extraction-warning observations. Comparisons use matched company-years with both components, while losses of coverage are tracked separately.

Targeted source checks illustrate both potential correspondence and false signals. In particular, NVIDIA's stock-plan appendices alter keyword-matched proxy profiles, so a low or unstable score does **not** establish weak corporate conduct. A coherence score of 100 means only that no qualifying reversals were detected. Threats include sparse historical About pages, changing page scope, duplicated or procedural proxy text, ambiguous theme matches, and overlapping coherence histories. Full-period calibration and cases where About captures follow proxy filings also preclude interpreting the scores as prospective signals.

With more time, I would validate labeled passages manually, standardize comparable proxy sections, test alternative thresholds on held-out observations, and supplement disclosures with independent behavioral evidence. These steps are prerequisites for stronger claims about organizational authenticity.

## Data and reproduction

[`outputs/dataset.csv`](outputs/dataset.csv) has one row per company-year. Fields include `ticker`, `company_name`, `sector`, `year`; `value_alignment`, `identity_coherence`, `authenticity_index`, `score_basis`; `identity_change`, `transition_status`, `valid_transition_count`, `reversal_count`; `part1_available`, `part2_available`, `stated_theme_count`; and `quality_flags`, `analyst_notes` for provenance and limitations.

[`src/part3/`](../src/part3/) reads the current Part 1 and Part 2 CSVs without modifying them or making network/model requests:

```sh
uv sync
uv run python -m src.part3
uv run python -m unittest src.part3.test_index
```

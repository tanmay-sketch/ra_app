"""Descriptive summaries, assumption checks and observed identity trajectories."""

import csv
import json
import math
import os
from collections import Counter
from pathlib import Path
from statistics import correlation, mean, median, stdev


SCORES = ('value_alignment', 'identity_coherence', 'authenticity_index')
LABELS = ('Value Alignment', 'Identity Coherence', 'Organizational Authenticity Index')


def _stats(values):
    values = list(values)
    return {'n': len(values), 'mean': mean(values) if values else None,
            'median': median(values) if values else None,
            'sd': stdev(values) if len(values) > 1 else None,
            'min': min(values) if values else None, 'max': max(values) if values else None}


def _score_stats(rows):
    return {name: _stats(row[name] for row in rows if row[name] is not None)
            for name in SCORES}


def _groups(rows, field):
    return [{'group': group, 'n': len(subset), **_score_stats(subset)}
            for group in sorted({row[field] for row in rows}, key=lambda value: (value is None, value))
            if (subset := [row for row in rows if row[field] == group])]


def _ranks(values):
    """Average tied ranks; ranks compare companies on the common sample."""
    ranked = [0.0] * len(values)
    order = sorted(range(len(values)), key=values.__getitem__)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for position in order[start:end]:
            ranked[position] = (start + 1 + end) / 2
        start = end
    return ranked


def _rank_correlation(left, right):
    if len(left) < 2 or len(set(left)) < 2 or len(set(right)) < 2:
        return None
    return correlation(_ranks(left), _ranks(right))


def _sensitivity(observations, baseline, metadata):
    from src.part3.index import company_scores, score

    settings = metadata['settings']
    defaults = {'alignment_weight': settings['alignment_weight'],
                'percentile': settings['change_percentile'],
                'baseline_floor': settings['baseline_floor'], 'exclude_warnings': False}
    scenarios = [('baseline', {}), ('alignment_weight_70', {'alignment_weight': .7}),
                 ('alignment_weight_30', {'alignment_weight': .3}),
                 ('change_percentile_60', {'percentile': .6}),
                 ('change_percentile_90', {'percentile': .9}),
                 ('benchmark_floor_001', {'baseline_floor': .001}),
                 ('benchmark_floor_010', {'baseline_floor': .01}),
                 ('exclude_extraction_warnings', {'exclude_warnings': True})]
    original = {row['ticker']: row for row in baseline if row['authenticity_index'] is not None}
    result = []
    for name, changed in scenarios:
        parameters = defaults | changed
        if changed:
            annual, details = score(observations, **parameters)
            rows = company_scores(annual, alignment_weight=parameters['alignment_weight'])
        else:
            rows, details = baseline, metadata
        scores = {row['ticker']: row for row in rows if row['authenticity_index'] is not None}
        common = original.keys() & scores.keys()
        keys = sorted(key for key in common if original[key]['score_basis'] == scores[key]['score_basis'])
        ranked = [key for key in keys if original[key]['score_basis'] == 'both']
        left = [original[key]['authenticity_index'] for key in keys]
        right = [scores[key]['authenticity_index'] for key in keys]
        differences = [abs(a - b) for a, b in zip(left, right)]
        result.append({'scenario': name, 'alignment_weight': parameters['alignment_weight'],
                       'coherence_weight': 1 - parameters['alignment_weight'],
                       'change_percentile': parameters['percentile'],
                       'benchmark_floor': parameters['baseline_floor'],
                       'exclude_extraction_warnings': parameters['exclude_warnings'],
                       'change_threshold': details['change_threshold'],
                       'available_companies': len(scores), 'common_same_basis_companies': len(keys),
                       'basis_changed_companies': sum(original[key]['score_basis'] != scores[key]['score_basis']
                                                      for key in common),
                       'lost_companies': len(original.keys() - scores.keys()),
                       'gained_companies': len(scores.keys() - original.keys()),
                       'coverage_change_from_baseline': len(scores) - len(original),
                       'common_baseline_mean': mean(left) if left else None,
                       'common_scenario_mean': mean(right) if right else None,
                       'mean_absolute_change': mean(differences) if differences else None,
                       'max_absolute_change': max(differences) if differences else None,
                       'ranked_both_component_companies': len(ranked),
                       'spearman_rank_correlation': _rank_correlation(
                           [original[key]['authenticity_index'] for key in ranked],
                           [scores[key]['authenticity_index'] for key in ranked])})
    return result


def _annual_eligibility(rows):
    flags = Counter(flag for row in rows for flag in set(row['quality_flags']))
    alignment_reasons = {'part1_missing', 'part2_missing', 'no_stated_themes',
                         'too_few_sector_peers', 'extraction_warning_excluded'}
    coherence_reasons = {'part2_missing', 'zero_theme_profile', 'insufficient_history',
                         'extraction_warning_excluded'}
    blockers = {'value_alignment': alignment_reasons, 'identity_coherence': coherence_reasons,
                'authenticity_index': alignment_reasons | coherence_reasons}
    return {'expected_rows': len(rows),
            'part1_available': sum(bool(row['part1_available']) for row in rows),
            'part2_available': sum(bool(row['part2_available']) for row in rows),
            'both_parts_available': sum(bool(row['part1_available'] and row['part2_available'])
                                        for row in rows),
            'assessed_empty_declarations': sum(row['stated_theme_count'] == 0 for row in rows),
            'jointly_assessed_empty_declarations': sum(row['stated_theme_count'] == 0
                                                       and row['part1_available'] and row['part2_available']
                                                       for row in rows),
            'available_scores': {key: sum(row[key] is not None for row in rows) for key in SCORES},
            'missing_scores': {key: sum(row[key] is None for row in rows) for key in SCORES},
            'quality_flag_counts': dict(sorted(flags.items())),
            'missing_score_reasons': {
                key: dict(sorted(Counter(flag for row in rows if row[key] is None
                                         for flag in set(row['quality_flags']) & blockers[key]).items()))
                for key in SCORES},
            'note': 'Reason counts overlap; one observation may have multiple blockers. Timing, source-quality and provisional-change flags do not themselves prevent scoring.'}


def _benchmark_diagnostics(observations, rows, floor):
    lookup = {(obs['ticker'], obs['year']): obs for obs in observations}
    benchmarks, floored, peers = [], 0, []
    for row in rows:
        if row['value_alignment'] is None:
            continue
        obs = lookup[row['ticker'], row['year']]
        cohort = [other for other in observations if other['sector'] == obs['sector']
                  and other['year'] == obs['year'] and other['ticker'] != obs['ticker']
                  and other['shares'] is not None]
        peers.append(len(cohort))
        for theme in obs['stated']:
            benchmark = mean(other['shares'][theme] for other in cohort)
            benchmarks.append(benchmark)
            floored += benchmark < floor
    return {'usable_peer_counts': _stats(peers), 'raw_stated_theme_benchmarks': _stats(benchmarks),
            'stated_theme_comparisons': len(benchmarks), 'floor_binding_comparisons': floored,
            'floor_binding_fraction': floored / len(benchmarks) if benchmarks else None}


def _review_cases(observations, annual_rows, company_rows):
    """Inspect comparable company scores through their annual alignment evidence."""
    lookup = {(obs['ticker'], obs['year']): obs for obs in observations}
    available = [row for row in company_rows if row['score_basis'] == 'both']
    selected, used = [], set()
    for label, reverse in (('low', False), ('high', True)):
        ordered = sorted(available, key=lambda r: (r['authenticity_index'], r['ticker']),
                         reverse=reverse)
        sectors = set()
        for row in ordered:
            key = row['ticker']
            if key in used or row['sector'] in sectors:
                continue
            aligned = sorted([annual for annual in annual_rows if annual['ticker'] == key
                              and annual['value_alignment'] is not None],
                             key=lambda annual: (annual['value_alignment'], annual['year']))
            evidence = []
            for annual in dict.fromkeys((aligned[0]['year'], aligned[-1]['year'])):
                obs = lookup[key, annual]
                scored = next(item for item in aligned if item['year'] == annual)
                evidence.append({'year': annual, 'value_alignment': scored['value_alignment'],
                                 'stated_themes': list(obs['stated']), 'disclosure_shares': obs['shares'],
                                 'quality_flags': scored['quality_flags'],
                                 'part1_snapshot_url': obs['part1'].get('snapshot_url', ''),
                                 'part2_source_url': obs['part2'].get('source_url', ''),
                                 'part2_text_file': obs['part2'].get('text_file', '')})
            selected.append({'selection': label, **row, 'annual_alignment_evidence': evidence})
            used.add(key)
            sectors.add(row['sector'])
            if len(sectors) == 3:
                break
    return selected


def _trajectory_selection(rows):
    choices, used = [], set()
    for status in ('reversal', 'sustained_transition', 'provisional_change', 'stable'):
        candidates = [row for row in rows if row['transition_status'] == status
                      and row['ticker'] not in used and row['identity_coherence'] is not None]
        if candidates:
            row = sorted(candidates, key=lambda r: (-r['valid_transition_count'], r['ticker'], r['year']))[0]
            choices.append({'ticker': row['ticker'], 'selected_year': row['year'], 'pattern': status})
            used.add(row['ticker'])
    return choices


def _plots(observations, rows, selected, output_dir):
    os.environ.setdefault('MPLCONFIGDIR', str(output_dir.parent / 'work' / 'matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams['svg.hashsalt'] = 'part3'
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharex=True)
    for ax, score, label in zip(axes, SCORES, LABELS):
        values = [row[score] for row in rows if row[score] is not None]
        if score == 'authenticity_index':
            groups = [[row[score] for row in rows if row['score_basis'] == basis]
                      for basis in ('both', 'alignment_only', 'coherence_only')]
            ax.hist(groups, bins=list(range(0, 101, 10)), stacked=True, edgecolor='white',
                    color=['#385d86', '#dc9147', '#78a283'],
                    label=['Both components', 'Alignment only', 'Coherence only'])
            ax.legend(frameon=False, fontsize=8, loc='upper left')
        else:
            ax.hist(values, bins=list(range(0, 101, 10)), color='#385d86', edgecolor='white')
        ax.set(title=f'{label}\n(n = {len(values)})', xlim=(0, 100), xlabel='Score', ylabel='Companies')
    fig.tight_layout()
    fig.savefig(output_dir / 'distributions.svg', metadata={'Date': None})
    plt.close(fig)
    if not selected:
        (output_dir / 'trajectories.svg').unlink(missing_ok=True)
        return
    fig, axes = plt.subplots(len(selected), 1, figsize=(9, 2.7 * len(selected)), squeeze=False,
                             sharex=True)
    years = sorted({obs['year'] for obs in observations})
    for ax, choice in zip(axes[:, 0], selected):
        company = {obs['year']: obs for obs in observations if obs['ticker'] == choice['ticker']}
        usable = [obs for obs in company.values() if obs['shares'] is not None]
        themes = sorted(usable[0]['shares'], key=lambda theme: (
            -max(obs['shares'][theme] for obs in usable) + min(obs['shares'][theme] for obs in usable), theme))[:3]
        choice['plotted_themes'] = themes
        # Separate scales keep within-company movements visible.
        maximum = max(100 * obs['shares'][theme] for obs in usable for theme in themes)
        upper = min(100, max(5, math.ceil(maximum * 1.1 / 5) * 5))
        for theme in themes:
            values = [100 * company[year]['shares'][theme]
                      if year in company and company[year]['shares'] is not None else math.nan for year in years]
            ax.plot(years, values, marker='o', markersize=3, label=theme)
        ax.set(title=f"{choice['ticker']}: {choice['pattern'].replace('_', ' ')} in {choice['selected_year']}",
               ylabel='Narrative words (%)', ylim=(0, upper), xticks=years)
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1), frameon=False)
    axes[-1, 0].set_xlabel('Annual-meeting year')
    fig.tight_layout()
    fig.savefig(output_dir / 'trajectories.svg', metadata={'Date': None})
    plt.close(fig)


def _ceiling(rows):
    return {score: {'at_zero': sum(row[score] == 0 for row in rows),
                    'at_100': sum(row[score] == 100 for row in rows),
                    'fraction_at_100': mean(row[score] == 100 for row in rows if row[score] is not None)
                    if any(row[score] is not None for row in rows) else None}
            for score in SCORES}


def write_report(observations, annual_rows, company_rows, metadata, output_dir):
    """Summarize full-period company scores; retain annual evidence as diagnostics."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sensitivity = _sensitivity(observations, company_rows, metadata)
    with (output_dir / 'sensitivity.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sensitivity[0]))
        writer.writeheader()
        writer.writerows(sensitivity)
    selected = _trajectory_selection(annual_rows)
    _plots(observations, company_rows, selected, output_dir)
    basis_counts = dict(Counter(row['score_basis'] for row in company_rows))
    summary = {'metadata': metadata,
               'eligibility': {
                   'expected_companies': len(company_rows),
                   'available_scores': {key: sum(row[key] is not None for row in company_rows) for key in SCORES},
                   'score_basis_counts': {basis: basis_counts.get(basis, 0)
                                          for basis in ('both', 'alignment_only', 'coherence_only', 'unavailable')},
                   'years_per_component': {key: _stats(row[key] for row in company_rows)
                                           for key in ('part1_years', 'part2_years', 'alignment_years', 'coherence_years')},
                   'unavailable': [{'ticker': row['ticker'], 'reason': row['analyst_notes']}
                                   for row in company_rows if row['authenticity_index'] is None]},
               'overall': _score_stats(company_rows), 'by_sector': _groups(company_rows, 'sector'),
               'by_score_basis': _groups(company_rows, 'score_basis'),
               'sector_by_score_basis': [{'sector': sector, 'by_score_basis': _groups(
                   [row for row in company_rows if row['sector'] == sector], 'score_basis')}
                   for sector in sorted({row['sector'] for row in company_rows})],
               'ceiling_diagnostics': _ceiling(company_rows),
               'annual_diagnostics': {
                   'eligibility': _annual_eligibility(annual_rows),
                   'transition_counts': dict(sorted(Counter(row['transition_status'] for row in annual_rows).items())),
                   'ceiling_diagnostics': _ceiling(annual_rows),
                   'benchmark_diagnostics': _benchmark_diagnostics(observations, annual_rows, metadata['settings']['baseline_floor'])},
               'sensitivity': sensitivity, 'selected_trajectories': selected,
               'trajectory_selection': 'One observed company per available pattern; longest current history, then ticker and year. Three most variable theme shares are plotted. Gaps break lines; vertical scales vary by company.',
               'case_review': _review_cases(observations, annual_rows, company_rows),
               'case_selection': 'Three highest and three lowest company scores with both components, selecting different sectors within each group. Annual alignment extremes provide source links. These are review candidates, not independent validation.',
               'interpretation': 'Descriptive consistency of corporate communication and disclosure; no causal or verified-conduct claims.',
               'company_comparison': 'Company components average their own available years. Scores using one component are reported separately from scores using both; component coverage periods can differ.',
               'rank_comparison': 'Tie-aware Spearman correlation uses companies with both components in both scenarios; undefined for constant scores. Absolute score changes use all common companies whose component basis is unchanged.'}
    temporary = output_dir / '.summary.json.tmp'
    temporary.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n',
                         encoding='utf-8')
    temporary.replace(output_dir / 'summary.json')
    return summary

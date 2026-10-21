"""Explore disclosure profiles locally: python -m src.part4."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import sklearn
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_samples, silhouette_score
from sklearn.preprocessing import normalize

from src.part2.common import THEMES
from src.tickers import TICKERS

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ('ticker', 'company_name', 'sector', 'year', 'theme_shares', 'cluster',
          'cluster_silhouette', 'cluster_changed_from_prior', 'authenticity_index',
          'score_basis', 'quality_flags')
SEEDS = range(10)
N_INIT = 20


def read_rows(path, required):
    records = {}
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        missing = {'ticker', 'company_name', 'sector', 'year', *required} - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f'{path}: missing columns {sorted(missing)}')
        for row in reader:
            ticker, year = row['ticker'], int(row['year'])
            company = TICKERS.get(ticker)
            if (company is None or year not in range(2016, 2025)
                    or row['company_name'] != company['name'] or row['sector'] != company['sector']):
                raise ValueError(f'{path}: invalid company-year identity {ticker} {year}')
            if (ticker, year) in records:
                raise ValueError(f'{path}: duplicate company-year {ticker} {year}')
            records[ticker, year] = row
    return records


def load_inputs(part2, part3):
    disclosures = read_rows(part2, {'theme_shares', 'text_file', 'analyst_notes'})
    indices = read_rows(part3, {'authenticity_index', 'score_basis'})
    rows = []
    for ticker, company in TICKERS.items():
        for year in range(2016, 2025):
            source, index = disclosures.get((ticker, year), {}), indices.get((ticker, year), {})
            shares = json.loads(source['theme_shares']) if source.get('theme_shares', '').strip() else None
            if shares is not None and (
                    not isinstance(shares, dict) or set(shares) != set(THEMES)
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not np.isfinite(v) or not 0 <= v <= 1 for v in shares.values())):
                raise ValueError(f'{ticker} {year}: expected ten finite theme shares in [0, 1].')
            flags = []
            if shares is None or not source.get('text_file'):
                shares = None
                flags.append('part2_missing')
            elif not any(shares.values()):
                flags.append('zero_theme_profile')
            if 'Extraction review:' in source.get('analyst_notes', ''):
                flags.append('part2_extraction_warning')
            value = index.get('authenticity_index', '')
            value = float(value) if value else None
            basis = index.get('score_basis', 'unavailable')
            if (basis not in {'both', 'alignment_only', 'coherence_only', 'unavailable'}
                    or (value is not None) != (basis == 'both')
                    or value is not None and (not np.isfinite(value) or not 0 <= value <= 100)):
                raise ValueError(f'{ticker} {year}: inconsistent Part 3 score and evidence basis.')
            rows.append({'ticker': ticker, 'company_name': company['name'], 'sector': company['sector'],
                         'year': year, 'theme_shares': shares, 'cluster': None,
                         'cluster_silhouette': None, 'cluster_changed_from_prior': None,
                         'authenticity_index': value, 'score_basis': basis, 'quality_flags': flags})
    return rows


def best_fit(profiles, k):
    models = [KMeans(n_clusters=k, random_state=seed, n_init=N_INIT).fit(profiles) for seed in SEEDS]
    reference = min(models, key=lambda model: model.inertia_)
    agreement = [adjusted_rand_score(reference.labels_, model.labels_) for model in models]
    return reference, agreement


def cluster(profiles):
    candidates, models = [], {}
    distinct = len(np.unique(profiles.round(12), axis=0))
    for k in range(2, min(5, distinct, len(profiles) - 1) + 1):
        model, agreement = best_fit(profiles, k)
        models[k] = model
        candidates.append({'k': k, 'silhouette': float(silhouette_score(profiles, model.labels_)),
                           'minimum_seed_ari': min(agreement), 'mean_seed_ari': float(np.mean(agreement)),
                           'reference_seed': model.random_state})
    if not candidates:
        raise ValueError('Clustering requires at least three observations and two distinct profiles.')
    selected = max(candidates, key=lambda item: (item['silhouette'], -item['k']))
    model = models[selected['k']]
    # Number clusters by descending size; numbers have no ordinal interpretation.
    order = sorted(range(model.n_clusters), key=lambda label: (-sum(model.labels_ == label), label))
    mapping = {label: position + 1 for position, label in enumerate(order)}
    labels = np.array([mapping[label] for label in model.labels_])
    return labels, candidates, selected


def summarize(rows, fitted, profiles, labels, candidates, selected):
    lookup = {(row['ticker'], row['year']): row for row in rows}
    for row in rows:
        previous = lookup.get((row['ticker'], row['year'] - 1))
        if row['cluster'] is not None and previous and previous['cluster'] is not None:
            row['cluster_changed_from_prior'] = row['cluster'] != previous['cluster']
    groups = []
    for label in sorted(set(labels)):
        mask = labels == label
        members = [row for row, included in zip(fitted, mask) if included]
        scores = [row['authenticity_index'] for row in members if row['authenticity_index'] is not None]
        groups.append({'cluster': int(label), 'company_years': len(members),
                       'companies': sorted({row['ticker'] for row in members}),
                       'sector_counts': dict(sorted(Counter(row['sector'] for row in members).items())),
                       'mean_normalized_weights': dict(zip(THEMES, profiles[mask].mean(axis=0).tolist())),
                       'authenticity_n': len(scores),
                       'authenticity_median': float(np.median(scores)) if scores else None})
    clean = np.array(['part2_extraction_warning' not in row['quality_flags'] for row in fitted])
    warning_check = None
    k = selected['k']
    if clean.sum() > k and len(np.unique(profiles[clean].round(12), axis=0)) >= k:
        refit, _ = best_fit(profiles[clean], k)
        warning_check = {'retained_rows': int(clean.sum()),
                         'adjusted_rand': float(adjusted_rand_score(labels[clean], refit.labels_))}
    transitions = [row for row in rows if row['cluster_changed_from_prior'] is not None]
    return {'observation_unit': 'company-year', 'features': list(THEMES),
            'normalization': 'Each ten-theme vector divided by its L2 norm; no column scaling.',
            'seeds': list(SEEDS), 'n_init': N_INIT, 'sklearn_version': sklearn.__version__,
            'selected_k': k, 'selection_rule': 'Highest silhouette among k=2..5; lower k breaks ties.',
            'candidates': candidates, 'fitted_rows': len(fitted), 'retained_rows': len(rows),
            'clusters': groups, 'adjacent_pairs': len(transitions),
            'cluster_switches': sum(row['cluster_changed_from_prior'] for row in transitions),
            'sector_adjusted_rand': float(adjusted_rand_score([row['sector'] for row in fitted], labels)),
            'without_extraction_warnings': warning_check}


def write_dataset(path, rows):
    temporary = path.with_suffix('.csv.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
            writer.writeheader()
            for row in rows:
                writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list))
                                 else int(value) if isinstance(value, bool)
                                 else round(value, 8) if isinstance(value, float) else value
                                 for key, value in row.items()})
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Explore clusters of annual disclosure priorities.')
    parser.add_argument('--part2', type=Path, default=ROOT / 'part2/outputs/dataset.csv')
    parser.add_argument('--part3', type=Path, default=ROOT / 'part3/outputs/dataset.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'part4/outputs')
    args = parser.parse_args()
    try:
        output = args.output_dir.resolve()
        sources = [args.part2.resolve(), args.part3.resolve()]
        if output in {path.parent for path in sources} or any(
                (output / name).resolve() in sources
                for name in ('dataset.csv', 'dataset.csv.tmp', 'summary.json', 'profiles.png')):
            raise ValueError('Output directory must be separate from source datasets.')
        rows = load_inputs(*sources)
        fitted = [row for row in rows if row['theme_shares'] and 'zero_theme_profile' not in row['quality_flags']]
        profiles = normalize(np.array([[row['theme_shares'][theme] for theme in THEMES] for row in fitted]))
        labels, candidates, selected = cluster(profiles)
        silhouettes = silhouette_samples(profiles, labels)
        for row, label, silhouette in zip(fitted, labels, silhouettes):
            row.update(cluster=int(label), cluster_silhouette=float(silhouette))
        summary = summarize(rows, fitted, profiles, labels, candidates, selected)
        summary['inputs'] = {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path):
                             hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        output.mkdir(parents=True, exist_ok=True)
        write_dataset(output / 'dataset.csv', rows)
        os.environ.setdefault('MPLCONFIGDIR', str(output.parent / 'work' / 'matplotlib'))
        from .plot import plot_profiles
        plot_profiles(profiles, labels, output / 'profiles.png')
        (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    except (ValueError, OSError) as error:
        parser.exit(1, f'Part 4: {error}\n')
    print(f'Saved {len(rows)} company-years; clustered {len(fitted)} into {selected["k"]} groups '
          f'(silhouette {selected["silhouette"]:.3f}).')


if __name__ == '__main__':
    main()

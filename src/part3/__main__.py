"""Build Part 3 locally: python -m src.part3."""

import argparse
import csv
import json
from pathlib import Path

from .data import ROOT, load_inputs
from .index import score
from .report import write_report

FIELDS = (
    'ticker', 'company_name', 'sector', 'year', 'value_alignment', 'identity_coherence',
    'authenticity_index', 'score_basis', 'identity_change', 'transition_status',
    'part1_available', 'part2_available', 'stated_theme_count', 'valid_transition_count',
    'reversal_count', 'quality_flags', 'analyst_notes',
)


def write_dataset(path, rows):
    temporary = path.with_suffix('.csv.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator='\n')
            writer.writeheader()
            for row in rows:
                writer.writerow({key: (json.dumps(value, ensure_ascii=False) if isinstance(value, list)
                                       else int(value) if isinstance(value, bool)
                                       else round(value, 8) if isinstance(value, float) else value)
                                 for key, value in row.items()})
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Build the Organizational Authenticity Index.')
    parser.add_argument('--part1', type=Path, default=ROOT / 'part1/outputs/dataset.csv')
    parser.add_argument('--part2', type=Path, default=ROOT / 'part2/outputs/dataset.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'part3/outputs')
    args = parser.parse_args()
    try:
        args.output_dir = args.output_dir.resolve()
        inputs = {args.part1.resolve(), args.part2.resolve()}
        if (args.output_dir in {path.parent for path in inputs}
                or any((args.output_dir / name).resolve() in inputs
                       for name in ('dataset.csv', 'dataset.csv.tmp', 'sensitivity.csv',
                                    'summary.json', '.summary.json.tmp',
                                    'distributions.svg', 'trajectories.svg'))):
            raise ValueError('Output directory must be separate from both source datasets.')
        observations, provenance = load_inputs(args.part1, args.part2)
        annual_rows, metadata = score(observations)
        metadata.update(provenance)
        metadata.update({
            'observation_unit': 'company-year',
            'aggregation': 'Average alignment and coherence within each company-year only '
                           'when both exist. Missing components remain missing.',
        })
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_dataset(args.output_dir / 'dataset.csv', annual_rows)
        write_report(observations, annual_rows, metadata, args.output_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Part 3: {error}\n')
    print(f'Saved {len(annual_rows)} company-years to {args.output_dir / "dataset.csv"}')
    print(f'Two-component authenticity scores: '
          f'{sum(row["authenticity_index"] is not None for row in annual_rows)}.')


if __name__ == '__main__':
    main()

"""Build Part 3 locally: python -m src.part3."""

import argparse
import csv
import json
from pathlib import Path

from .data import ROOT, load_inputs
from .index import company_scores, score
from .report import write_report

FIELDS = (
    'ticker', 'company_name', 'sector', 'value_alignment', 'identity_coherence',
    'authenticity_index', 'score_basis', 'part1_years', 'part2_years',
    'alignment_years', 'coherence_years', 'quality_flags', 'analyst_notes',
)


def write_dataset(path, rows):
    temporary = path.with_suffix('.csv.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
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
        rows = company_scores(annual_rows)
        metadata.update(provenance)
        metadata.update({
            'observation_unit': 'company',
            'aggregation': 'Average each component over its available years, then average '
                           'the available component means. Missing values do not enter denominators.',
        })
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_dataset(args.output_dir / 'dataset.csv', rows)
        summary = write_report(observations, annual_rows, rows, metadata, args.output_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Part 3: {error}\n')
    counts = summary['eligibility']['available_scores']
    print(f'Saved {len(rows)} companies to {args.output_dir}')
    print(f'Alignment: {counts["value_alignment"]}; coherence: {counts["identity_coherence"]}; '
          f'available-component score: {counts["authenticity_index"]}.')


if __name__ == '__main__':
    main()

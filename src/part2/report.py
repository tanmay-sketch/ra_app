"""Coverage and descriptive trends, retaining each company's equal weight."""

import json
import os
from statistics import mean

from src.part2.common import OUTPUT_DIR, THEMES, WORK_DIR, YEARS, atomic_json
from src.tickers import TICKERS

EVENTS = [
    {'event': 'WHO characterizes COVID-19 as a pandemic', 'date': '2020-03-11',
     'source': 'https://www.who.int/news-room/speeches/item/'
               'who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020'},
    {'event': 'SEC adopts pay-versus-performance rule', 'date': '2022-08-25',
     'source': 'https://www.sec.gov/newsroom/press-releases/2022-149',
     'note': 'Applies to relevant disclosures for fiscal years ending on or after 2022-12-16.'},
]


def write_report(rows: list[dict], audits: dict, directory=OUTPUT_DIR) -> None:
    """Summarize available coverage, company-weighted measures and paired changes."""
    usable = [row for row in rows if row['text_file']]
    coverage = {str(year): sum(int(r['year']) == year for r in usable) for year in YEARS}
    themes = {(r['ticker'], int(r['year'])): json.loads(r['theme_shares'])
              for r in usable if r['theme_shares']}
    tones = {(r['ticker'], int(r['year'])): json.loads(r['tone_rates'])
             for r in usable if r['tone_rates']}
    # Company means have equal weight; changes use only firms present in both years.
    sector_means, paired_changes = [], []
    for sector in dict.fromkeys(company['sector'] for company in TICKERS.values()):
        for year in YEARS:
            companies = [t for t, c in TICKERS.items() if c['sector'] == sector and (t, year) in themes]
            paired = [t for t in companies if (t, year - 1) in themes]
            tone_companies = [t for t, c in TICKERS.items() if c['sector'] == sector and (t, year) in tones]
            tone_paired = [t for t in tone_companies if (t, year - 1) in tones]
            sector_means.append({'sector': sector, 'year': year, 'companies': len(companies),
                'theme_shares': {k: mean(themes[t, year][k] for t in companies) for k in THEMES} if companies else {},
                'tone_companies': len(tone_companies),
                'tone_rates': {k: mean(tones[t, year][k] for t in tone_companies)
                               for k in ('positive', 'negative', 'uncertainty')} if tone_companies else {}})
            paired_changes.append({'sector': sector, 'year': year, 'paired_companies': len(paired),
                'theme_share_changes': {k: mean(themes[t, year][k] - themes[t, year - 1][k] for t in paired)
                                        for k in THEMES} if paired else {},
                'tone_paired_companies': len(tone_paired),
                'tone_rate_changes': {k: mean(tones[t, year][k] - tones[t, year - 1][k] for t in tone_paired)
                                      for k in ('positive', 'negative', 'uncertainty')} if tone_paired else {}})
    # Filing dates identify comparisons spanning an event, without implying causality.
    event_pairs = []
    by_key = {(r['ticker'], int(r['year'])): r for r in usable}
    for event in EVENTS:
        affected = []
        for row in usable:
            prior = by_key.get((row['ticker'], int(row['year']) - 1))
            if (prior and prior['filing_date'] and row['filing_date']
                    and prior['filing_date'] < event['date'] <= row['filing_date']):
                affected.append({'ticker': row['ticker'], 'year': int(row['year']),
                                 'similarity_to_prior': row['similarity_to_prior'],
                                 'notes': row['analyst_notes']})
        event_pairs.append(event | {'adjacent_filing_pairs_spanning_event': affected})
    summary = {
        'company_years': len(rows), 'with_text': len(usable),
        'with_topics': len(themes), 'with_tone': len(tones),
        'with_adjacent_comparison': sum(bool(r['similarity_to_prior']) for r in rows),
        'coverage_by_year': coverage, 'sector_year_means': sector_means,
        'balanced_adjacent_changes': paired_changes, 'events': event_pairs,
        'interpretation': 'Descriptive disclosure-language measures; no causal or conduct claims.',
        'topic_method': 'Provisional spaCy phrase matches; vocabulary has not had independent validation.',
    }
    atomic_json(directory / 'summary.json', summary)
    if not usable:
        for name in ('coverage.svg', 'themes.svg'):
            (directory / name).unlink(missing_ok=True)
        return
    os.environ.setdefault('MPLCONFIGDIR', str(WORK_DIR / 'matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    # Stable SVG IDs and omitted timestamps avoid artificial changes between runs.
    matplotlib.rcParams['svg.hashsalt'] = 'part2'
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(list(YEARS), [coverage[str(year)] for year in YEARS], color='#435e91')
    ax.set(ylim=(0, 50), xticks=list(YEARS), ylabel='Companies with usable proxy text',
           title='Part 2 coverage by annual-meeting year')
    fig.tight_layout()
    fig.savefig(directory / 'coverage.svg', metadata={'Date': None})
    plt.close(fig)
    if themes:
        fig, ax = plt.subplots(figsize=(9, 5))
        for theme in THEMES:
            points = [(year, [v[theme] for (t, y), v in themes.items() if y == year]) for year in YEARS]
            points = [(year, mean(values) if values else float('nan')) for year, values in points]
            ax.plot([p[0] for p in points], [p[1] for p in points], marker='o', label=theme)
        ax.set(xticks=list(YEARS), ylim=(0, 1), ylabel='Mean share of analyzed words',
               title='Topic emphasis (provisional; company coverage varies)')
        ax.legend(loc='center left', bbox_to_anchor=(1, .5), frameon=False)
        fig.tight_layout()
        fig.savefig(directory / 'themes.svg', metadata={'Date': None})
        plt.close(fig)
    else:
        (directory / 'themes.svg').unlink(missing_ok=True)

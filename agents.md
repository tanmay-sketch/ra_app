# AGENTS.md

## Project Goal

Study **organizational authenticity**, specifically the alignment between what companies publicly state they value and what their disclosures suggest they prioritize.

The project covers 50 specified S&P 500 companies across five sectors from 2016–2024.

The goal is to produce reliable datasets, meaningful analyses, and well-justified research findings. Prioritize reproducibility, methodological clarity, and intellectual honesty.

## Project Structure

```text
.
├── src/
│   ├── part1/
│   ├── part2/
│   ├── part3/
│   └── part4/
├── part1/
│   ├── README.md
│   └── outputs/
├── part2/
│   ├── README.md
│   └── outputs/
├── part3/
│   ├── README.md
│   └── outputs/
└── part4/
    ├── README.md
    └── outputs/
```

- `src/partN/` contains the code for each part.
- `partN/README.md` documents methodology, decisions, assumptions, findings, and limitations.
- `partN/outputs/` contains the relevant datasets, results, and figures.

Keep the repository minimal. Avoid unnecessary files, tests, abstractions, or redundant outputs.

## Project Parts

### Part 1: Stated Values

Collect archived corporate About Us or equivalent pages using the Wayback Machine for the 50 companies from 2016–2024.

Extract clean text and analyze changes in stated values, themes, and language over time. Produce a structured company-year dataset.

### Part 2: Lived Values

Collect one consistent type of corporate disclosure (ESG, sustainability, DEI, or proxy reports) for the same companies and period.

Analyze changes in language, tone, and topic emphasis across companies, sectors, and years. Produce a documented structured dataset.

### Part 3: Organizational Authenticity Index

Use Parts 1 and 2 to construct a measure of alignment between stated values and disclosed priorities.

Justify the measure, examine its distribution, perform validity checks, and discuss limitations.

### Part 4: Research Proposal

Propose and briefly implement an additional analysis using the constructed measure or underlying data.

Focus on an interesting research question, sound reasoning, and careful interpretation of findings.

## Working Guidelines

- Work on **one part at a time**, inferred from the conversation context and current task.
- Do not start another part unless explicitly directed or clearly indicated by context.
- Keep code simple, readable, and reproducible.
- Use the provided research requirements and company list as the source of truth.
- Document important methodological choices, assumptions, and data limitations.
- Never fabricate data, sources, or results.
- Distinguish observed findings from interpretations.
- Keep each part's README updated as work progresses.
- Prefer defensible research decisions over unnecessary complexity.
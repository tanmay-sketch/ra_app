"""Check the research meaning of the index: python -m unittest src.part3.test_index."""

import copy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

from src.part3.data import THEMES, load_inputs
from src.part3.index import company_scores, coherence, cosine_distance, score, value_alignment
from src.tickers import TICKERS


def profile(**values):
    return {theme: values.get(theme, 0.0) for theme in THEMES}


A = profile(Integrity=1.0)
B = profile(Employees=1.0)


def observation(ticker, year, shares=None, *, warning=False):
    company = TICKERS[ticker]
    return {
        "ticker": ticker, "company_name": company["name"],
        "sector": company["sector"], "year": year,
        "stated": ("Integrity",), "shares": shares if shares is not None else A.copy(),
        "part1_available": True, "part2_available": True,
        "flags": ["extraction_warning"] if warning else [],
        "extraction_warning": warning, "part1": {}, "part2": {},
    }


class AlignmentTests(unittest.TestCase):
    def test_peer_average_is_fifty_and_only_stated_themes_count(self):
        shares = profile(Integrity=0.2, Employees=0.9)
        peers = [profile(Integrity=0.2, Employees=0.01) for _ in range(5)]
        self.assertAlmostEqual(value_alignment(("Integrity",), shares, peers), 50)

    def test_zero_support_is_zero_and_empty_statement_is_unavailable(self):
        peers = [A.copy() for _ in range(5)]
        self.assertEqual(value_alignment(("Integrity",), profile(), peers), 0)
        self.assertIsNone(value_alignment((), A, peers))
        self.assertIsNone(value_alignment(None, A, peers))

    def test_all_stated_themes_and_overlapping_shares_are_valid(self):
        shares = {theme: 0.5 for theme in THEMES}
        self.assertAlmostEqual(value_alignment(tuple(THEMES), shares, [shares] * 5), 50)

    def test_benchmark_floor_and_minimum_peer_count(self):
        peers = [profile() for _ in range(5)]
        self.assertAlmostEqual(value_alignment(("Integrity",), profile(Integrity=0.005), peers), 50)
        self.assertIsNone(value_alignment(("Integrity",), A, peers[:4]))

    def test_focal_company_does_not_set_its_own_benchmark(self):
        tickers = list(TICKERS)[:6]
        observations = [observation(t, 2016, profile(Integrity=0.1)) for t in tickers]
        observations[0]["shares"] = profile(Integrity=0.4)
        rows, _ = score(observations)
        focal = next(row for row in rows if row["ticker"] == tickers[0])
        self.assertAlmostEqual(focal["value_alignment"], 80, places=5)


class CoherenceTests(unittest.TestCase):
    def test_reference_histories(self):
        cases = [("AAAA", 100), ("AABB", 100), ("ABAA", 50), ("ABAB", 0)]
        for letters, expected in cases:
            with self.subTest(history=letters):
                result = coherence([A if letter == "A" else B for letter in letters], 0.5)
                self.assertEqual(result["identity_coherence"], expected)
                self.assertEqual(result["valid_transition_count"], 3)
                self.assertEqual(result["reversal_count"], int((100 - expected) / 50))

    def test_insufficient_history_and_zero_vector_interrupt(self):
        for history in ([A, B, A], [A, A, A, profile(), A, A]):
            result = coherence(history, 0.5)
            self.assertIsNone(result["identity_coherence"])
            self.assertEqual(result["transition_status"], "insufficient_history")
        self.assertIsNone(cosine_distance(A, profile()))

    def test_ties_count_as_substantial_and_new_change_is_provisional(self):
        self.assertEqual(coherence([A, B, A, B], 1)["identity_coherence"], 0)
        self.assertEqual(coherence([A, A, A, B], 1)["transition_status"], "provisional_change")
        self.assertEqual(coherence([A, A, B, B], 1)["transition_status"], "sustained_transition")

    def test_cosine_is_scale_invariant(self):
        self.assertAlmostEqual(cosine_distance([1, 2], [2, 4]), 0)
        self.assertEqual(cosine_distance([1, 0], [0, 1]), 1)

    def test_stable_population_threshold_does_not_mark_zero_change(self):
        observations = [observation("MSFT", year) for year in range(2016, 2020)]
        rows, metadata = score(observations)
        self.assertGreater(metadata["change_threshold"], 0)
        self.assertEqual(rows[-1]["identity_coherence"], 100)
        self.assertEqual(rows[-1]["transition_status"], "stable")

    def test_calendar_gap_resets_history_and_does_not_bridge_change(self):
        years = (2016, 2017, 2018, 2020, 2021, 2022, 2023)
        rows, _ = score([observation("MSFT", year) for year in years])
        by_year = {row["year"]: row for row in rows}
        self.assertIsNone(by_year[2020]["identity_change"])
        self.assertIsNone(by_year[2022]["identity_coherence"])
        self.assertEqual(by_year[2023]["identity_coherence"], 100)

    def test_no_future_company_history_enters_earlier_score(self):
        observations = [observation("MSFT", 2016 + i, shares)
                        for i, shares in enumerate([A, B, A, A, B, A])]
        early, early_meta = score(observations[:4])
        extended, extended_meta = score(observations)
        self.assertEqual(early_meta["change_threshold"], extended_meta["change_threshold"])
        self.assertEqual(early[-1], extended[3])
        self.assertEqual(early[-1]["identity_coherence"], 50)


class PipelineTests(unittest.TestCase):
    def test_quality_exclusion_recomputes_peers_and_history(self):
        tickers = list(TICKERS)[:6]
        observations = [observation(t, year, warning=t == tickers[-1] and year == 2018)
                        for t in tickers for year in range(2016, 2020)]
        next(row for row in observations if row["extraction_warning"])["shares"] = B.copy()
        baseline, baseline_meta = score(observations, percentile=0.95)
        excluded, excluded_meta = score(observations, percentile=0.95, exclude_warnings=True)
        self.assertEqual(baseline_meta["distance_pair_count"], 18)
        self.assertEqual(excluded_meta["distance_pair_count"], 16)
        self.assertGreater(baseline_meta["change_threshold"], excluded_meta["change_threshold"])
        baseline = {(row["ticker"], row["year"]): row for row in baseline}
        excluded = {(row["ticker"], row["year"]): row for row in excluded}
        self.assertIsNotNone(baseline[tickers[0], 2018]["value_alignment"])
        self.assertIsNone(excluded[tickers[0], 2018]["value_alignment"])
        flagged = excluded[tickers[-1], 2018]
        self.assertTrue(flagged["part2_available"])
        self.assertIsNone(flagged["identity_coherence"])
        self.assertIsNone(excluded[tickers[-1], 2019]["identity_coherence"])

    def test_scores_are_bounded_and_inputs_are_not_modified(self):
        observations = [observation(t, year) for t in list(TICKERS)[:6]
                        for year in range(2016, 2020)]
        original = copy.deepcopy(observations)
        rows, _ = score(observations)
        self.assertEqual(observations, original)
        for row in rows:
            for column in ("value_alignment", "identity_coherence", "authenticity_index"):
                value = row[column]
                if value is not None:
                    self.assertTrue(math.isfinite(value) and 0 <= value <= 100)
        final = rows[-1]
        self.assertAlmostEqual(final["authenticity_index"],
                               (final["value_alignment"] + final["identity_coherence"]) / 2)

    def test_invalid_method_settings_are_rejected(self):
        for setting in ({"alignment_weight": -0.1}, {"alignment_weight": 1.1},
                        {"percentile": float("nan")}, {"percentile": 75},
                        {"baseline_floor": 0}, {"baseline_floor": float("inf")}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                score([], **setting)


class CompanyTests(unittest.TestCase):
    @staticmethod
    def annual(ticker, year, alignment=None, identity=None, *, part1=True, part2=True, flags=()):
        return {
            "ticker": ticker, "company_name": TICKERS[ticker]["name"],
            "sector": TICKERS[ticker]["sector"], "year": year,
            "value_alignment": alignment, "identity_coherence": identity,
            "part1_available": part1, "part2_available": part2,
            "quality_flags": list(flags),
        }

    def test_component_means_receive_equal_weight_despite_different_year_counts(self):
        annual = [self.annual("MSFT", 2016, 10), self.annual("MSFT", 2017, 30),
                  self.annual("MSFT", 2019, identity=100, part1=False)]
        original = copy.deepcopy(annual)
        company = company_scores(annual)[0]
        self.assertEqual(company["value_alignment"], 20)
        self.assertEqual(company["identity_coherence"], 100)
        self.assertEqual(company["authenticity_index"], 60)
        self.assertEqual(company["score_basis"], "both")
        self.assertEqual((company["alignment_years"], company["coherence_years"]), (2, 1))
        self.assertEqual((company["part1_years"], company["part2_years"]), (2, 3))
        self.assertEqual(annual, original)

    def test_one_component_is_retained_without_halving_and_no_components_stay_missing(self):
        annual = [self.annual("MSFT", 2016, 20), self.annual("MSFT", 2017, 40),
                  self.annual("AAPL", 2019, identity=20), self.annual("AAPL", 2020, identity=40),
                  self.annual("NVDA", 2016, part1=False, part2=False)]
        companies = {row["ticker"]: row for row in company_scores(annual)}
        self.assertEqual(len(companies), 3)
        for ticker, expected, basis in (("MSFT", 30, "alignment_only"),
                                        ("AAPL", 30, "coherence_only"),
                                        ("NVDA", None, "unavailable")):
            with self.subTest(ticker=ticker):
                self.assertEqual(companies[ticker]["authenticity_index"], expected)
                self.assertEqual(companies[ticker]["score_basis"], basis)

    def test_genuine_zero_is_available(self):
        company = company_scores([self.annual("MSFT", 2016, 0)])[0]
        self.assertEqual(company["value_alignment"], 0)
        self.assertEqual(company["authenticity_index"], 0)
        self.assertEqual(company["alignment_years"], 1)
        self.assertEqual(company["score_basis"], "alignment_only")

    def test_partial_source_coverage_does_not_mark_the_whole_company_missing(self):
        annual = [self.annual("MSFT", 2016, 20, flags=("part2_extraction_warning",)),
                  self.annual("MSFT", 2017, identity=80, part1=False, flags=("part1_missing",)),
                  self.annual("AAPL", 2016, part1=False, part2=False)]
        companies = {row["ticker"]: row for row in company_scores(annual)}
        self.assertNotIn("part1_missing", companies["MSFT"]["quality_flags"])
        self.assertIn("part2_extraction_warning", companies["MSFT"]["quality_flags"])
        self.assertIn("part1_missing", companies["AAPL"]["quality_flags"])
        self.assertIn("part2_missing", companies["AAPL"]["quality_flags"])

    def test_sensitivity_weights_renormalize_over_available_components(self):
        annual = [self.annual("MSFT", 2019, 20, 100), self.annual("AAPL", 2019, 20),
                  self.annual("NVDA", 2019, identity=100)]
        companies = {row["ticker"]: row for row in company_scores(annual, alignment_weight=0.7)}
        self.assertAlmostEqual(companies["MSFT"]["authenticity_index"], 44)
        self.assertEqual(companies["AAPL"]["authenticity_index"], 20)
        self.assertEqual(companies["NVDA"]["authenticity_index"], 100)
        zero_weight = company_scores([annual[2]], alignment_weight=1)[0]
        self.assertIsNone(zero_weight["authenticity_index"])
        self.assertEqual(zero_weight["score_basis"], "unavailable")
        for weight in (-0.1, 1.1, float("nan")):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                company_scores(annual, alignment_weight=weight)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = [Path(self.temp.name) / name for name in ("part1.csv", "part2.csv")]
        identity = {"ticker": "MSFT", "company_name": "Microsoft", "sector": "Technology", "year": "2016"}
        self.part1 = {**identity, "page_text_clean": "A verified company statement.",
                      "theme_categories": '["Integrity"]', "snapshot_url": ""}
        self.part2 = {**identity, "theme_shares": json.dumps(profile(Integrity=0.1)),
                      "text_file": "text/MSFT/2016.txt", "source_url": "https://www.sec.gov/example.htm",
                      "filing_date": "2016-04-01", "analyst_notes": ""}

    def load(self, part1=None, part2=None):
        for path, rows in zip(self.paths, (part1 or [self.part1], part2 or [self.part2])):
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        return load_inputs(*self.paths)

    def test_roster_scaffold_and_empty_assessment_remain_distinct(self):
        self.part1["theme_categories"] = "[]"
        observations, _ = self.load()
        self.assertEqual(len(observations), 450)
        focal = next(row for row in observations if row["ticker"] == "MSFT" and row["year"] == 2016)
        self.assertTrue(focal["part1_available"])
        self.assertEqual(tuple(focal["stated"]), ())
        self.part1["theme_categories"] = ""
        observations, _ = self.load()
        focal = next(row for row in observations if row["ticker"] == "MSFT" and row["year"] == 2016)
        self.assertFalse(focal["part1_available"])
        self.assertIsNone(focal["stated"])

    def test_duplicate_unknown_issuer_year_and_sector_are_rejected(self):
        with self.assertRaises(ValueError):
            self.load(part1=[self.part1, self.part1])
        for column, value in (("ticker", "UNKNOWN"), ("year", "2015"), ("sector", "Energy"),
                              ("company_name", "Wrong company")):
            with self.subTest(column=column), self.assertRaises(ValueError):
                self.load(part2=[{**self.part2, column: value}])

    def test_invalid_theme_lists_are_rejected(self):
        for value in ('[', '["Unknown"]', '{"Integrity": 1}', '[true]'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load(part1=[{**self.part1, "theme_categories": value}])

    def test_invalid_shares_are_rejected(self):
        invalid = ['{', json.dumps({"Integrity": 0.1})]
        invalid += [json.dumps({**profile(), "Integrity": value})
                    for value in (-0.1, 1.1, float("nan"), float("inf"), True)]
        invalid += [json.dumps({**profile(), "Unknown": 0.1})]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load(part2=[{**self.part2, "theme_shares": value}])

    def test_zero_shares_are_available_without_local_text_files(self):
        self.part2["theme_shares"] = json.dumps(profile())
        observations, _ = self.load()
        focal = next(row for row in observations if row["ticker"] == "MSFT" and row["year"] == 2016)
        self.assertTrue(focal["part2_available"])
        before = [path.read_bytes() for path in self.paths]
        score(observations)
        self.assertEqual(before, [path.read_bytes() for path in self.paths])


if __name__ == "__main__":
    unittest.main()

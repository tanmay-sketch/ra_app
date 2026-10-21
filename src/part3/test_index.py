"""Check the research meaning of the index: python -m unittest src.part3.test_index."""

import copy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

from src.part3.data import THEMES, load_inputs
from src.part3.index import coherence, cosine_distance, score, value_alignment
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
    def test_annual_composite_requires_both_components_and_four_consecutive_years(self):
        observations = [observation(t, year) for t in list(TICKERS)[:6]
                        for year in range(2016, 2021)]
        for row in observations:
            if row["year"] == 2020 and row["ticker"] in ("MSFT", "AAPL"):
                row.update(part1_available=False, stated=None)
                if row["ticker"] == "AAPL":
                    row.update(part2_available=False, shares=None)
        rows, _ = score(observations)
        by_key = {(row["ticker"], row["year"]): row for row in rows}
        for row in rows:
            if row["year"] < 2019:
                self.assertIsNone(row["identity_coherence"])
                self.assertIsNone(row["authenticity_index"])
                self.assertEqual(row["score_basis"], "alignment_only")
        full = by_key["MSFT", 2019]
        self.assertEqual(full["score_basis"], "both")
        self.assertAlmostEqual(full["authenticity_index"], 75)
        partial = by_key["MSFT", 2020]
        self.assertEqual(partial["score_basis"], "coherence_only")
        self.assertEqual(partial["identity_coherence"], 100)
        self.assertIsNone(partial["authenticity_index"])
        missing = by_key["AAPL", 2020]
        self.assertEqual(missing["score_basis"], "unavailable")
        self.assertIsNone(missing["authenticity_index"])

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

    def test_genuine_zero_is_available(self):
        observations = [observation(t, year) for t in list(TICKERS)[:6]
                        for year in range(2016, 2020)]
        for row in observations:
            if row["ticker"] == "MSFT" and row["year"] % 2:
                row["shares"] = B.copy()
        rows, _ = score(observations)
        focal = {row["year"]: row for row in rows if row["ticker"] == "MSFT"}
        self.assertEqual(focal[2017]["value_alignment"], 0)
        self.assertIsNone(focal[2017]["authenticity_index"])
        self.assertEqual(focal[2017]["score_basis"], "alignment_only")
        complete = focal[2019]
        self.assertEqual(complete["value_alignment"], 0)
        self.assertEqual(complete["identity_coherence"], 0)
        self.assertEqual(complete["authenticity_index"], 0)
        self.assertEqual(complete["score_basis"], "both")

    def test_sensitivity_weights_apply_only_to_complete_composites(self):
        observations = [observation(t, year) for t in list(TICKERS)[:6]
                        for year in range(2016, 2020)]
        for row in observations:
            if row["ticker"] == "MSFT":
                row["shares"] = profile(Integrity=0.25, Employees=0.75)
            elif row["ticker"] == "AAPL" and row["year"] == 2019:
                row.update(part1_available=False, stated=None)
        weighted, _ = score(observations, alignment_weight=0.7)
        by_key = {(row["ticker"], row["year"]): row for row in weighted}
        self.assertAlmostEqual(by_key["MSFT", 2019]["authenticity_index"], 44)
        self.assertIsNone(by_key["MSFT", 2016]["authenticity_index"])
        self.assertIsNone(by_key["AAPL", 2019]["authenticity_index"])
        endpoint, _ = score(observations, alignment_weight=1)
        partial = next(row for row in endpoint if row["ticker"] == "AAPL" and row["year"] == 2019)
        self.assertIsNone(partial["authenticity_index"])
        self.assertEqual(partial["score_basis"], "coherence_only")


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

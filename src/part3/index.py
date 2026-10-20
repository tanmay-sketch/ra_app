"""Calculate stated-value alignment and reversals in disclosure priorities."""

from collections import defaultdict
from math import fsum, isfinite

import numpy as np

from .data import THEMES


def value_alignment(stated, shares, peers, *, baseline_floor=0.005, minimum_peers=5):
    """Average support for stated themes against other sector-year companies."""
    if not stated or shares is None or len(peers) < minimum_peers:
        return None
    supports = []
    for theme in stated:
        benchmark = max(fsum(peer[theme] for peer in peers) / len(peers), baseline_floor)
        support = shares[theme] / (shares[theme] + benchmark)
        supports.append(support)
    return 100 * fsum(supports) / len(supports)


def _vector(profile):
    values = [profile[theme] for theme in THEMES] if isinstance(profile, dict) else profile
    return np.asarray(values, dtype=float)


def cosine_distance(a, b):
    """Return a distance in [0, 1]; zero vectors have no usable direction."""
    a, b = _vector(a), _vector(b)
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("Theme profiles must be vectors of the same length.")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Theme profiles must contain finite values.")
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if not denominator:
        return None
    return float(np.clip(1 - np.dot(a, b) / denominator, 0, 1))


def _reversal(a, b, c, threshold):
    left, right = cosine_distance(a, b), cosine_distance(b, c)
    endpoint = cosine_distance(a, c)
    return left >= threshold and right >= threshold and endpoint < min(left, right)


def coherence(history, threshold, *, min_years=4):
    """Score an uninterrupted history and describe its latest three-year pattern."""
    # A zero vector interrupts history even when called independently of score().
    run = []
    for profile in history:
        if cosine_distance(profile, profile) is None:
            run = []
        else:
            run.append(profile)
    transitions = max(0, len(run) - 1)
    result = {
        "identity_coherence": None,
        "transition_status": "insufficient_history",
        "valid_transition_count": transitions,
        "reversal_count": None,
    }
    if len(run) < min_years or threshold is None:
        return result

    reversals = sum(_reversal(a, b, c, threshold) for a, b, c in zip(run, run[1:], run[2:]))
    a, b, c = run[-3:]
    left, right = cosine_distance(a, b), cosine_distance(b, c)
    endpoint = cosine_distance(a, c)
    if _reversal(a, b, c, threshold):
        status = "reversal"
    elif left >= threshold and right < threshold and endpoint >= threshold:
        status = "sustained_transition"
    elif left < threshold and right < threshold:
        status = "stable"
    else:
        status = "provisional_change"
    result.update(
        identity_coherence=100 * (1 - reversals / (transitions - 1)),
        transition_status=status,
        reversal_count=int(reversals),
    )
    return result


def score(observations, *, alignment_weight=0.5, percentile=0.75,
          baseline_floor=0.005, exclude_warnings=False):
    """Return company-year scores without modifying the supplied observations."""
    if not isfinite(alignment_weight) or not 0 <= alignment_weight <= 1:
        raise ValueError("Alignment weight must be between zero and one.")
    if not isfinite(percentile) or not 0 <= percentile <= 1:
        raise ValueError("Change percentile must be between zero and one.")
    if not isfinite(baseline_floor) or baseline_floor <= 0:
        raise ValueError("Benchmark floor must be positive and finite.")

    observations = list(observations)
    profiles, statements = {}, {}
    groups, companies = defaultdict(list), defaultdict(list)
    excluded = set()
    for observation in observations:
        key = observation["ticker"], observation["year"]
        remove = exclude_warnings and observation.get("extraction_warning", False)
        if remove:
            excluded.add(key)
        profiles[key] = (observation["shares"]
                         if observation["part2_available"] and not remove else None)
        statements[key] = (observation["stated"]
                           if observation["part1_available"] and not remove else None)
        if profiles[key] is not None:
            groups[observation["sector"], observation["year"]].append((key, profiles[key]))
        companies[observation["ticker"]].append(observation)

    # Calibration uses all valid adjacent pairs, including later study years.
    distances = []
    changes = {}
    for key, profile in profiles.items():
        previous = profiles.get((key[0], key[1] - 1))
        distance = (cosine_distance(previous, profile)
                    if previous is not None and profile is not None else None)
        changes[key] = distance
        if distance is not None:
            distances.append(distance)
    threshold = (max(1e-8, float(np.quantile(distances, percentile, method="linear")))
                 if distances else None)

    results = {}
    for ticker, company in companies.items():
        history, previous_year = [], None
        for observation in sorted(company, key=lambda item: item["year"]):
            year = observation["year"]
            key = ticker, year
            profile, stated = profiles[key], statements[key]
            flags, notes = list(observation.get("flags", [])), []
            if not observation["part1_available"]:
                flags.append("part1_missing")
                notes.append("Part 1 assessment unavailable.")
            if not observation["part2_available"]:
                flags.append("part2_missing")
                notes.append("Proxy theme shares unavailable.")
            if key in excluded:
                flags.append("extraction_warning_excluded")
                notes.append("Source extraction warning excluded from scoring.")
            if stated == () or stated == []:
                flags.append("no_stated_themes")
                notes.append("No stated themes to assess.")

            peers = [peer for peer_key, peer in groups[observation["sector"], year]
                     if peer_key[0] != ticker]
            alignment = value_alignment(stated, profile, peers, baseline_floor=baseline_floor)
            if stated and profile is not None and len(peers) < 5:
                flags.append("too_few_sector_peers")
                notes.append(f"Alignment requires five usable sector-year peers; {len(peers)} available.")

            direction_usable = profile is not None and cosine_distance(profile, profile) is not None
            if previous_year is not None and year != previous_year + 1:
                history = []
                flags.append("history_reset")
            if not direction_usable:
                if history:
                    flags.append("history_reset")
                history = []
                if profile is not None:
                    flags.append("zero_theme_profile")
                    notes.append("All-zero proxy profile has no direction; coherence history resets.")
            else:
                prior = profiles.get((ticker, year - 1))
                if previous_year is not None and (prior is None or cosine_distance(prior, prior) is None):
                    flags.append("history_reset")
                history.append(profile)

            evidence = coherence(history, threshold)
            identity = evidence["identity_coherence"]
            if identity is None:
                flags.append("insufficient_history")
                notes.append(f"Coherence requires four consecutive usable years; {len(history)} available.")
            else:
                windows = evidence["valid_transition_count"] - 1
                notes.append(f"{evidence['reversal_count']} reversals across {windows} eligible windows "
                             f"in {len(history)} consecutive years.")
            if evidence["transition_status"] == "provisional_change":
                flags.append("provisional_change")
                notes.append("The latest shift has not yet established persistence or a reversal.")

            combined = (alignment_weight * alignment + (1 - alignment_weight) * identity
                        if alignment is not None and identity is not None else None)
            results[key] = {
                "ticker": ticker,
                "company_name": observation["company_name"],
                "sector": observation["sector"],
                "year": year,
                "value_alignment": alignment,
                "identity_coherence": identity,
                "authenticity_index": combined,
                "identity_change": changes[key],
                "transition_status": evidence["transition_status"],
                "part1_available": observation["part1_available"],
                "part2_available": observation["part2_available"],
                "stated_theme_count": (len(observation["stated"])
                                       if observation["stated"] is not None else None),
                "valid_transition_count": evidence["valid_transition_count"],
                "reversal_count": evidence["reversal_count"],
                "quality_flags": list(dict.fromkeys(flags)),
                "analyst_notes": " ".join(notes),
            }
            previous_year = year

    metadata = {
        "settings": {
            "alignment_weight": alignment_weight,
            "coherence_weight": 1 - alignment_weight,
            "change_percentile": percentile,
            "baseline_floor": baseline_floor,
            "minimum_peers": 5,
            "minimum_history_years": 4,
            "exclude_warnings": exclude_warnings,
        },
        "change_threshold": threshold,
        "distance_pair_count": len(distances),
        "excluded_count": len(excluded),
    }
    return [results[item["ticker"], item["year"]] for item in observations], metadata


def company_scores(annual_rows, *, alignment_weight=0.5):
    """Average each observed component first, then combine the available means."""
    if not isfinite(alignment_weight) or not 0 <= alignment_weight <= 1:
        raise ValueError("Alignment weight must be between zero and one.")
    companies = defaultdict(list)
    for row in annual_rows:
        companies[row["ticker"]].append(row)

    # Annual gaps and transient labels do not describe the whole study period.
    annual_flags = {"history_reset", "insufficient_history", "provisional_change",
                    "part1_missing", "part2_missing", "no_stated_themes",
                    "too_few_sector_peers"}
    results = []
    for ticker, rows in companies.items():
        alignment = [row["value_alignment"] for row in rows
                     if row["value_alignment"] is not None]
        identity = [row["identity_coherence"] for row in rows
                    if row["identity_coherence"] is not None]
        alignment_mean = fsum(alignment) / len(alignment) if alignment else None
        identity_mean = fsum(identity) / len(identity) if identity else None
        components = [(alignment_mean, alignment_weight), (identity_mean, 1 - alignment_weight)]
        available = [(value, weight) for value, weight in components if value is not None]
        weight_sum = fsum(weight for _, weight in available)
        combined = (fsum(value * weight for value, weight in available) / weight_sum
                    if weight_sum else None)
        basis = ("both" if alignment and identity else "alignment_only" if alignment
                 else "coherence_only" if identity else "unavailable")
        part1_years = sum(bool(row["part1_available"]) for row in rows)
        part2_years = sum(bool(row["part2_available"]) for row in rows)
        flags = list(dict.fromkeys(flag for row in rows for flag in row["quality_flags"]
                                   if flag not in annual_flags))
        if not part1_years:
            flags.append("part1_missing")
        if not part2_years:
            flags.append("part2_missing")
        if not alignment:
            flags.append("alignment_unavailable")
            if part1_years and not any(row.get("stated_theme_count") for row in rows):
                flags.append("no_stated_themes")
        if not identity:
            flags.append("coherence_unavailable")

        note = (f"Alignment averages {len(alignment)} annual scores; "
                f"coherence averages {len(identity)} annual scores. ")
        if available and not weight_sum:
            basis = "unavailable"
            note += "The available component has zero configured weight."
        elif basis == "both":
            note += "The period score combines the two component means."
        elif basis == "alignment_only":
            note += "The score reflects alignment only; disclosure coherence is unmeasured."
        elif basis == "coherence_only":
            note += "The score reflects disclosure coherence only; stated-value alignment is unmeasured."
        else:
            note += "Neither component could be scored."

        results.append({
            "ticker": ticker, "company_name": rows[0]["company_name"], "sector": rows[0]["sector"],
            "value_alignment": alignment_mean, "identity_coherence": identity_mean,
            "authenticity_index": combined, "score_basis": basis,
            "part1_years": part1_years, "part2_years": part2_years,
            "alignment_years": len(alignment), "coherence_years": len(identity),
            "quality_flags": list(dict.fromkeys(flags)), "analyst_notes": note,
        })
    return results

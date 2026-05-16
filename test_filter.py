"""
Cheap relevance-filter audit.

Runs the Granite filter on the 5 deliberately-seeded "noise" interactions
plus 2 obvious-legit controls, and prints PASS/FAIL per case so you can
see whether the filter is actually discriminating or just rubber-stamping.

Token cost: 7 small Granite calls. No extraction.

Usage:
    python test_filter.py
"""

import json
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.WARNING)  # quiet — we print our own table


# id  →  expected relevance ("drop" means filter should reject)
EXPECTED = {
    # Noise interactions — should all be DROPPED (clear cases) or ambiguous
    "not_neuraledge_noise_001":  "ambiguous",  # mentions NeuralEdge in deal context
    "not_luminary_noise_001":    "drop",       # admin standup, mentioned in passing
    "not_quantum_noise_001":     "drop",       # market research, no specific startup
    "not_fleetmind_noise_001":   "drop",       # industry conference panel
    "not_polardb_noise_001":     "drop",       # office coffee catch-up
    # Legit controls — should be KEPT
    "not_neuraledge_001":        "keep",       # First Intro Call with founders
    "slack_neuraledge_003":      "keep",       # IC memo with metrics
}


def main():
    mock = json.load(open(Path(__file__).parent / "mock_data.json", encoding="utf-8"))

    # Index every interaction by id
    all_interactions = {}
    for company in mock["companies"]:
        for x in company.get("interactions", []):
            all_interactions[x["id"]] = (company["organization"]["name"], x)

    # Init filter (Granite — flash model)
    from src.llm.watsonx_client import WatsonXClient
    from src.llm.relevance_filter import RelevanceFilter

    flash = WatsonXClient(model="flash")
    rfilter = RelevanceFilter(watsonx_client=flash)

    print()
    print(f"{'COMPANY':<18} {'ID':<32} {'EXPECT':<10} {'ACTUAL':<8} {'VERDICT':<8} REASON")
    print("-" * 130)

    for interaction_id, expect in EXPECTED.items():
        if interaction_id not in all_interactions:
            print(f"{'?':<18} {interaction_id:<32} MISSING in mock_data.json")
            continue
        company_name, interaction = all_interactions[interaction_id]
        decision = rfilter.filter_interaction(interaction)
        actual = "keep" if decision.relevant else "drop"

        # Verdict logic: ambiguous = either answer OK
        if expect == "ambiguous":
            verdict = "OK"
        else:
            verdict = "OK" if actual == expect else "WRONG"

        reason = decision.reason[:70].replace("\n", " ")
        print(f"{company_name:<18} {interaction_id:<32} {expect:<10} {actual:<8} {verdict:<8} {reason}")

    print()


if __name__ == "__main__":
    main()

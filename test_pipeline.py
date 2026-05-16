"""
Quick smoke test for the extraction pipeline.

Feeds the first company from mock_data.json directly through:
  1. RelevanceFilter  (Granite 4.0 H Small)
  2. ExtractionEngine (Llama 3.3 70B Instruct)

No database or data-source connectors needed — just WatsonX credentials in .env.

Usage:
    python test_pipeline.py
"""

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("test_pipeline")


def main():
    # ------------------------------------------------------------------ #
    # Load mock data                                                       #
    # ------------------------------------------------------------------ #
    mock_path = Path(__file__).parent / "mock_data.json"
    with open(mock_path, encoding="utf-8") as f:
        mock = json.load(f)

    company_raw = mock["companies"][1]
    company_name = company_raw["organization"]["name"]
    logger.info(f"Testing with company: {company_name}")

    # Reshape into the format the pipeline expects (mirrors DataAggregator output)
    company_data = {
        "company_name": company_name,
        "company_domain": company_raw["organization"]["domain"],
        "interactions": company_raw.get("interactions", []),
        "metadata": {},
    }
    logger.info(f"Loaded {len(company_data['interactions'])} interactions")

    # ------------------------------------------------------------------ #
    # Initialise LLM clients                                               #
    # ------------------------------------------------------------------ #
    from src.llm.watsonx_client import WatsonXClient

    flash_client = WatsonXClient(model="flash")   # Granite — relevance filter
    pro_client   = WatsonXClient(model="pro")     # Llama   — extraction

    # ------------------------------------------------------------------ #
    # Step 1: Relevance filter                                             #
    # ------------------------------------------------------------------ #
    logger.info("─" * 60)
    logger.info("STEP 1: Relevance filtering")
    from src.llm.relevance_filter import RelevanceFilter

    relevance_filter = RelevanceFilter(watsonx_client=flash_client)
    filtered = relevance_filter.filter_company_data(company_data)

    total = len(company_data["interactions"])
    kept  = len(filtered["interactions"])
    logger.info(f"Filtering done: {kept}/{total} interactions kept")

    if kept == 0:
        logger.error("No relevant interactions — cannot proceed to extraction.")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Step 2: Extraction                                                   #
    # ------------------------------------------------------------------ #
    logger.info("─" * 60)
    logger.info("STEP 2: Intelligence extraction")
    from src.llm.extraction_engine import ExtractionEngine

    extraction_engine = ExtractionEngine(watsonx_client=pro_client)
    extraction = extraction_engine.extract(filtered)

    # ------------------------------------------------------------------ #
    # Print results                                                        #
    # ------------------------------------------------------------------ #
    logger.info("─" * 60)
    logger.info("EXTRACTION RESULT")
    logger.info(f"  Company:     {extraction.company.name}")
    logger.info(f"  Sector:      {extraction.company.sector}")
    logger.info(f"  Stage:       {extraction.company.stage}")
    logger.info(f"  Verdict:     {extraction.decision_record.verdict}")
    logger.info(f"  Confidence:  {extraction.extraction_meta.confidence:.2f}")
    logger.info(f"  Contacts:    {len(extraction.contacts)}")
    logger.info(f"  Interactions:{len(extraction.interactions)}")
    if extraction.extraction_meta.warnings:
        for w in extraction.extraction_meta.warnings:
            logger.warning(f"  Warning: {w}")

    logger.info("─" * 60)
    logger.info("Pipeline smoke test passed.")

    # Dump full JSON to file for inspection
    out_path = Path(__file__).parent / "test_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(extraction.model_dump(), f, indent=2, default=str)
    logger.info(f"Full extraction saved to {out_path}")


if __name__ == "__main__":
    main()

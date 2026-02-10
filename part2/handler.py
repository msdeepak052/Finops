"""
Lambda Handler — Bedrock AI Recommendation Validator (Part 2)

Triggered by S3 event when Part 1 uploads a JSON report.
Validates recommendations against the organization's allow-list,
uses Bedrock AI for non-approved types, and generates enriched reports.

Environment Variables:
  REPORT_BUCKET    — S3 bucket name for report storage
  REPORT_PREFIX    — S3 key prefix (default: "reports")
  BEDROCK_MODEL_ID — Bedrock model alias or full ID (default: "claude")
  BEDROCK_REGION   — AWS region for Bedrock endpoint (default: "us-east-1")
"""

import json
import logging
import os
import re
from typing import Any

from bedrock_validator import (
    AllowListChecker,
    BedrockClient,
    EnrichedReportBuilder,
    RecommendationEnricher,
    S3ReportReader,
)

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

for handler in logger.handlers:
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda entry point — triggered by S3 event notification.

    Args:
        event: S3 event notification payload.
        context: Lambda context object.

    Returns:
        Dict with execution summary and S3 report locations.
    """
    logger.info("Part 2: Starting Bedrock AI Recommendation Validation")
    logger.info("Event: %s", json.dumps(event, default=str))

    # ── Guard: Parse S3 event and apply filters ──────────────────
    reader = S3ReportReader()

    try:
        s3_info = reader.parse_s3_event(event)
    except ValueError as e:
        logger.error("Invalid S3 event: %s", e)
        return {"statusCode": 400, "body": str(e)}

    bucket = s3_info["bucket"]
    key = s3_info["key"]

    # Guard: skip non-JSON files
    if not key.endswith(".json"):
        logger.info("Skipping non-JSON file: %s", key)
        return {"statusCode": 200, "body": f"Skipped non-JSON file: {key}"}

    # Guard: skip validated reports (prevent re-triggering)
    if "/validated/" in key:
        logger.info("Skipping validated report (prevent re-trigger): %s", key)
        return {"statusCode": 200, "body": f"Skipped validated report: {key}"}

    # ── Configuration ────────────────────────────────────────────
    report_bucket = os.environ.get("REPORT_BUCKET", bucket)
    report_prefix = os.environ.get("REPORT_PREFIX", "reports")
    bedrock_model = os.environ.get("BEDROCK_MODEL_ID", "claude")
    bedrock_region = os.environ.get("BEDROCK_REGION", "us-east-1")

    # Extract timestamp from S3 key path (e.g., reports/2025-01-15_12-00-00/...)
    timestamp = _extract_timestamp(key)

    # ── Step 1: Read Part 1 report ───────────────────────────────
    logger.info("Step 1/4: Reading Part 1 report from s3://%s/%s", bucket, key)
    recommendations = reader.read_report(bucket, key)

    if not recommendations:
        logger.info("No recommendations in report. Nothing to validate.")
        return {
            "statusCode": 200,
            "body": "No recommendations to validate",
            "total_instances": 0,
        }

    logger.info("Loaded %d recommendations for validation", len(recommendations))

    # ── Step 2: Load allow-list + init Bedrock ───────────────────
    logger.info("Step 2/4: Loading allow-list and initializing Bedrock")
    checker = AllowListChecker().load()
    bedrock = BedrockClient(model_id=bedrock_model, region=bedrock_region)

    # ── Step 3: Enrich recommendations ───────────────────────────
    logger.info("Step 3/4: Validating %d recommendations", len(recommendations))
    enricher = RecommendationEnricher(checker, bedrock)
    enriched = enricher.enrich_all(recommendations)

    # ── Step 4: Generate and upload reports ──────────────────────
    logger.info("Step 4/4: Generating enriched CSV and JSON reports")
    builder = EnrichedReportBuilder()
    csv_content = builder.build_csv(enriched)
    json_content = builder.build_json(enriched)

    s3_keys = builder.upload_to_s3(
        bucket_name=report_bucket,
        csv_content=csv_content,
        json_content=json_content,
        prefix=report_prefix,
        timestamp=timestamp,
    )

    # Also save locally (/tmp in Lambda)
    builder.save_local(csv_content, json_content)

    # ── Summary ──────────────────────────────────────────────────
    approved = sum(1 for r in enriched if r.get("validation_status") == "Approved (Allowed Instance)")
    ai_recommended = sum(1 for r in enriched if r.get("validation_status") == "AI-Recommended Alternative")
    failed = sum(1 for r in enriched if r.get("validation_status") == "AI Validation Failed")
    total_savings = sum(float(r.get("estimated_monthly_savings_with_discount", 0)) for r in enriched)

    summary = {
        "statusCode": 200,
        "body": "Validation report generated successfully",
        "total_instances_validated": len(enriched),
        "approved_in_allowlist": approved,
        "ai_recommended_alternatives": ai_recommended,
        "ai_validation_failed": failed,
        "total_estimated_monthly_savings_with_discount_usd": round(total_savings, 2),
        "bedrock_model": bedrock_model,
        "s3_csv": f"s3://{report_bucket}/{s3_keys['csv_key']}",
        "s3_json": f"s3://{report_bucket}/{s3_keys['json_key']}",
    }

    logger.info("Part 2 execution summary: %s", json.dumps(summary))
    return summary


def _extract_timestamp(key: str) -> str:
    """Extract the timestamp folder from an S3 key path."""
    # Match pattern like 2025-01-15_12-00-00
    match = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", key)
    return match.group(1) if match else ""

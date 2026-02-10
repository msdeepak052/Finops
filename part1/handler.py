"""
Lambda Handler — EC2 Cost Optimization Report Generator

Orchestrates the full pipeline:
  1. Fetch EC2 recommendations from Compute Optimizer
  2. Enrich with EC2 tags (instance names)
  3. Filter out EKS/Kubernetes instances
  4. Enrich with On-Demand pricing data
  5. Generate CSV and JSON reports
  6. Upload reports to S3

Environment Variables:
  REPORT_BUCKET  — S3 bucket name for report storage
  REPORT_PREFIX  — S3 key prefix (default: "reports")
  AWS_REGION     — Target region for pricing lookups (default from Lambda env)
  ACCOUNT_IDS    — Comma-separated list of account IDs for multi-account
                   (optional; empty = current account only)
"""

import json
import logging
import os
from typing import Any

from compute_optimizer import (
    ComputeOptimizerClient,
    CostCalculator,
    EC2TagFetcher,
    EKSFilter,
    ReportBuilder,
)

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Strip default Lambda handler to get clean JSON logs
for handler in logger.handlers:
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda entry point.

    Args:
        event: EventBridge scheduled event or manual invocation payload.
        context: Lambda context object.

    Returns:
        Dict with execution summary and S3 report locations.
    """
    logger.info("Starting EC2 Cost Optimization Report generation")
    logger.info("Event: %s", json.dumps(event, default=str))

    # Configuration from environment
    report_bucket = os.environ.get("REPORT_BUCKET", "")
    report_prefix = os.environ.get("REPORT_PREFIX", "reports")
    region = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
    account_ids_raw = os.environ.get("ACCOUNT_IDS", "")
    account_ids = [a.strip() for a in account_ids_raw.split(",") if a.strip()] if account_ids_raw else []

    if not report_bucket:
        raise ValueError("REPORT_BUCKET environment variable is required")

    # ── Step 1: Fetch Compute Optimizer recommendations ─────────────
    logger.info("Step 1/5: Fetching Compute Optimizer EC2 recommendations")
    optimizer = ComputeOptimizerClient(account_ids=account_ids)
    recommendations = optimizer.get_ec2_recommendations()

    if not recommendations:
        logger.info("No EC2 recommendations found. Exiting.")
        return {
            "statusCode": 200,
            "body": "No recommendations found",
            "total_instances": 0,
        }

    logger.info("Found %d total EC2 recommendations", len(recommendations))

    # ── Step 2: Enrich with EC2 tags ────────────────────────────────
    logger.info("Step 2/5: Fetching EC2 tags for %d instances", len(recommendations))
    tag_fetcher = EC2TagFetcher()
    recommendations = tag_fetcher.enrich_recommendations(recommendations)

    # ── Step 3: Filter out EKS/Kubernetes instances ─────────────────
    logger.info("Step 3/5: Filtering EKS/Kubernetes instances")
    non_eks, eks_excluded = EKSFilter.filter_recommendations(recommendations)

    logger.info(
        "After EKS filter: %d instances for report, %d EKS instances excluded",
        len(non_eks),
        len(eks_excluded),
    )

    if not non_eks:
        logger.info("All instances are EKS workloads. No report to generate.")
        return {
            "statusCode": 200,
            "body": "All instances are EKS workloads — nothing to report",
            "total_instances": len(recommendations),
            "eks_excluded": len(eks_excluded),
            "non_eks_included": 0,
        }

    # ── Step 4: Enrich with pricing data ────────────────────────────
    logger.info("Step 4/5: Fetching On-Demand pricing for %d instances", len(non_eks))
    calculator = CostCalculator(region=region)
    non_eks = calculator.enrich_recommendations(non_eks)

    # ── Step 5: Generate and upload reports ─────────────────────────
    logger.info("Step 5/5: Generating CSV and JSON reports")
    builder = ReportBuilder()
    csv_content = builder.build_csv(non_eks)
    json_content = builder.build_json(non_eks)

    s3_keys = builder.upload_to_s3(
        bucket_name=report_bucket,
        csv_content=csv_content,
        json_content=json_content,
        prefix=report_prefix,
    )

    # ── Summary ─────────────────────────────────────────────────────
    total_savings_on_demand = sum(
        r.get("estimated_monthly_savings_on_demand", 0) for r in non_eks
    )
    total_savings_after_discounts = sum(
        r.get("estimated_monthly_savings_after_discounts", 0) for r in non_eks
    )

    summary = {
        "statusCode": 200,
        "body": "Report generated successfully",
        "total_instances_analyzed": len(recommendations),
        "eks_excluded": len(eks_excluded),
        "non_eks_included": len(non_eks),
        "total_estimated_monthly_savings_on_demand_usd": round(total_savings_on_demand, 2),
        "total_estimated_monthly_savings_after_discounts_usd": round(total_savings_after_discounts, 2),
        "s3_csv": f"s3://{report_bucket}/{s3_keys['csv_key']}",
        "s3_json": f"s3://{report_bucket}/{s3_keys['json_key']}",
    }

    logger.info("Execution summary: %s", json.dumps(summary))
    return summary

"""
Enriched Report Builder

Generates CSV and JSON reports from validated/enriched recommendation data.
Follows the same patterns as Part 1's ReportBuilder.
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOTO_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
)

# Column mapping: internal_key -> display_name (order matters for CSV)
ENRICHED_COLUMNS = [
    ("Account ID", "Account ID"),
    ("Instance ID", "Instance ID"),
    ("Instance Name", "Instance Name"),
    ("Finding", "Finding"),
    ("Current Instance Type", "Current Instance Type"),
    ("Recommended Instance Type", "CO Recommended Type"),
    ("validation_status", "Validation Status"),
    ("final_recommendation", "Final Recommendation"),
    ("discount_tier_name", "Discount Tier"),
    ("discount_percent", "Discount (%)"),
    ("Current Monthly On-Demand Price (USD)", "Current Monthly Price (USD)"),
    ("Recommended Monthly On-Demand Price (USD)", "Recommended Monthly Price (USD)"),
    ("discounted_monthly_price", "Discounted Monthly Price (USD)"),
    ("Est. Monthly Savings On-Demand (USD)", "Est. Savings On-Demand (USD)"),
    ("estimated_monthly_savings_with_discount", "Est. Savings With Discount (USD)"),
    ("ai_confidence", "AI Confidence"),
    ("ai_analysis_summary", "AI Analysis"),
    ("ai_alternatives", "AI Alternatives"),
    ("bedrock_model", "Bedrock Model"),
]


class EnrichedReportBuilder:
    """Generates and uploads enriched validation reports."""

    def __init__(self, session: boto3.Session | None = None):
        self._session = session or boto3.Session()
        self._timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    def build_csv(self, recommendations: list[dict[str, Any]]) -> str:
        """Build a CSV string from enriched recommendations."""
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header row
        headers = [display for _, display in ENRICHED_COLUMNS]
        writer.writerow(headers)

        # Data rows
        for rec in recommendations:
            row = []
            for key, _ in ENRICHED_COLUMNS:
                value = rec.get(key, "")
                if isinstance(value, list):
                    value = "; ".join(str(v) for v in value)
                row.append(value)
            writer.writerow(row)

        csv_content = output.getvalue()
        logger.info("Generated enriched CSV report with %d rows", len(recommendations))
        return csv_content

    def build_json(self, recommendations: list[dict[str, Any]]) -> str:
        """Build a JSON report string from enriched recommendations."""
        # Compute summary statistics
        approved = sum(1 for r in recommendations if r.get("validation_status") == "Approved (Allowed Instance)")
        ai_recommended = sum(1 for r in recommendations if r.get("validation_status") == "AI-Recommended Alternative")
        failed = sum(1 for r in recommendations if r.get("validation_status") == "AI Validation Failed")
        total_savings = sum(float(r.get("estimated_monthly_savings_with_discount", 0)) for r in recommendations)

        report = {
            "report_metadata": {
                "generated_at": self._timestamp,
                "report_type": "validated",
                "total_instances": len(recommendations),
                "approved_count": approved,
                "ai_recommended_count": ai_recommended,
                "ai_failed_count": failed,
                "total_estimated_monthly_savings_with_discount": round(total_savings, 2),
                "validation_summary": {
                    "Approved (Allowed Instance)": approved,
                    "AI-Recommended Alternative": ai_recommended,
                    "AI Validation Failed": failed,
                },
            },
            "recommendations": [
                self._build_json_record(rec) for rec in recommendations
            ],
        }

        json_content = json.dumps(report, indent=2, default=str)
        logger.info("Generated enriched JSON report with %d records", len(recommendations))
        return json_content

    def upload_to_s3(
        self,
        bucket_name: str,
        csv_content: str,
        json_content: str,
        prefix: str = "reports",
        timestamp: str | None = None,
    ) -> dict[str, str]:
        """
        Upload enriched CSV and JSON reports to S3.

        Files go under {prefix}/{timestamp}/validated/ subfolder.

        Args:
            bucket_name: Target S3 bucket name.
            csv_content: CSV report string.
            json_content: JSON report string.
            prefix: S3 key prefix.
            timestamp: Timestamp folder from Part 1 report path. If None, uses own timestamp.

        Returns:
            Dict with S3 keys for uploaded files.
        """
        s3_client = self._session.client("s3", config=BOTO_CONFIG)
        ts = timestamp or self._timestamp

        csv_key = f"{prefix}/{ts}/validated/ec2_validated_report.csv"
        json_key = f"{prefix}/{ts}/validated/ec2_validated_report.json"

        s3_client.put_object(
            Bucket=bucket_name,
            Key=csv_key,
            Body=csv_content.encode("utf-8"),
            ContentType="text/csv",
            ServerSideEncryption="aws:kms",
        )
        logger.info("Uploaded enriched CSV to s3://%s/%s", bucket_name, csv_key)

        s3_client.put_object(
            Bucket=bucket_name,
            Key=json_key,
            Body=json_content.encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
        )
        logger.info("Uploaded enriched JSON to s3://%s/%s", bucket_name, json_key)

        return {"csv_key": csv_key, "json_key": json_key}

    def save_local(self, csv_content: str, json_content: str, output_dir: str = "/tmp") -> dict[str, str]:
        """
        Save reports to local filesystem (for Lambda /tmp or local testing).

        Returns:
            Dict with file paths.
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        csv_path = os.path.join(output_dir, "ec2_validated_report.csv")
        json_path = os.path.join(output_dir, "ec2_validated_report.json")

        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_content)

        logger.info("Saved local reports to %s", output_dir)
        return {"csv_path": csv_path, "json_path": json_path}

    def _build_json_record(self, rec: dict[str, Any]) -> dict[str, Any]:
        """Build a clean JSON record using display-friendly keys."""
        record = {}
        for key, display in ENRICHED_COLUMNS:
            record[display] = rec.get(key, "")
        return record

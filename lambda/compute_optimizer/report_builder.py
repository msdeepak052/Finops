"""
Report Builder

Generates CSV and JSON reports from enriched EC2 recommendation data.
Supports local file output and S3 upload.
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
REPORT_COLUMNS = [
    ("account_id", "Account ID"),
    ("instance_id", "Instance ID"),
    ("instance_name", "Instance Name"),
    ("finding", "Finding"),
    ("finding_reasons", "Finding Reasons"),
    ("cpu_finding_reasons", "CPU Finding Reasons"),
    ("memory_finding_reasons", "Memory Finding Reasons"),
    ("recommendation_instance_state", "Recommendation Instance State"),
    ("current_instance_type", "Current Instance Type"),
    ("recommended_instance_type", "Recommended Instance Type"),
    ("current_performance_risk", "Current Performance Risk"),
    ("recommended_performance_risk", "Recommended Performance Risk"),
    ("current_instance_price", "Current Hourly Price (USD)"),
    ("recommended_instance_price", "Recommended Hourly Price (USD)"),
    ("current_on_demand_price", "Current Monthly On-Demand Price (USD)"),
    ("recommended_on_demand_price", "Recommended Monthly On-Demand Price (USD)"),
    ("price_difference", "Monthly Price Difference (USD)"),
    ("estimated_monthly_savings_on_demand", "Est. Monthly Savings On-Demand (USD)"),
    ("estimated_monthly_savings_after_discounts", "Est. Monthly Savings After Discounts (USD)"),
    ("savings_opportunity_pct", "Savings Opportunity (%)"),
    ("savings_after_discounts_pct", "Savings After Discounts (%)"),
    ("savings_currency", "Currency"),
    ("inferred_workload_types", "Inferred Workload Types"),
    ("recommended_migration_effort", "Migration Effort"),
]


class ReportBuilder:
    """Generates and uploads cost optimization reports."""

    def __init__(self, session: boto3.Session | None = None):
        self._session = session or boto3.Session()
        self._timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    def build_csv(self, recommendations: list[dict[str, Any]]) -> str:
        """
        Build a CSV string from the recommendations.

        Returns:
            CSV content as a string.
        """
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header row
        headers = [display for _, display in REPORT_COLUMNS]
        writer.writerow(headers)

        # Data rows
        for rec in recommendations:
            row = []
            for key, _ in REPORT_COLUMNS:
                value = rec.get(key, "")
                # Convert lists to semicolon-separated strings for CSV
                if isinstance(value, list):
                    value = "; ".join(str(v) for v in value)
                row.append(value)
            writer.writerow(row)

        csv_content = output.getvalue()
        logger.info("Generated CSV report with %d rows", len(recommendations))
        return csv_content

    def build_json(self, recommendations: list[dict[str, Any]]) -> str:
        """
        Build a JSON report string from the recommendations.

        Returns:
            JSON content as a formatted string.
        """
        report = {
            "report_metadata": {
                "generated_at": self._timestamp,
                "total_instances": len(recommendations),
                "total_estimated_monthly_savings_on_demand": sum(
                    r.get("estimated_monthly_savings_on_demand", 0) for r in recommendations
                ),
                "total_estimated_monthly_savings_after_discounts": sum(
                    r.get("estimated_monthly_savings_after_discounts", 0) for r in recommendations
                ),
                "finding_summary": self._build_finding_summary(recommendations),
            },
            "recommendations": [
                self._build_json_record(rec) for rec in recommendations
            ],
        }

        json_content = json.dumps(report, indent=2, default=str)
        logger.info("Generated JSON report with %d records", len(recommendations))
        return json_content

    def upload_to_s3(
        self,
        bucket_name: str,
        csv_content: str,
        json_content: str,
        prefix: str = "reports",
    ) -> dict[str, str]:
        """
        Upload CSV and JSON reports to S3.

        Args:
            bucket_name: Target S3 bucket name.
            csv_content: CSV report string.
            json_content: JSON report string.
            prefix: S3 key prefix (folder).

        Returns:
            Dict with S3 keys for the uploaded files.
        """
        s3_client = self._session.client("s3", config=BOTO_CONFIG)

        csv_key = f"{prefix}/{self._timestamp}/ec2_optimization_report.csv"
        json_key = f"{prefix}/{self._timestamp}/ec2_optimization_report.json"

        s3_client.put_object(
            Bucket=bucket_name,
            Key=csv_key,
            Body=csv_content.encode("utf-8"),
            ContentType="text/csv",
            ServerSideEncryption="aws:kms",
        )
        logger.info("Uploaded CSV report to s3://%s/%s", bucket_name, csv_key)

        s3_client.put_object(
            Bucket=bucket_name,
            Key=json_key,
            Body=json_content.encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
        )
        logger.info("Uploaded JSON report to s3://%s/%s", bucket_name, json_key)

        return {"csv_key": csv_key, "json_key": json_key}

    def _build_json_record(self, rec: dict[str, Any]) -> dict[str, Any]:
        """Build a clean JSON record using display-friendly keys."""
        record = {}
        for key, display in REPORT_COLUMNS:
            record[display] = rec.get(key, "")
        return record

    @staticmethod
    def _build_finding_summary(recommendations: list[dict[str, Any]]) -> dict[str, int]:
        """Count instances by finding type."""
        summary: dict[str, int] = {}
        for rec in recommendations:
            finding = rec.get("finding", "Unknown")
            summary[finding] = summary.get(finding, 0) + 1
        return summary

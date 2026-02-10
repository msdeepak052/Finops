"""
S3 Report Reader

Parses S3 event notifications and reads Part 1 JSON reports from S3.
"""

import json
import logging
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOTO_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
)


class S3ReportReader:
    """Reads Part 1 JSON reports from S3 triggered by S3 event notifications."""

    def __init__(self, session: boto3.Session | None = None):
        self._session = session or boto3.Session()
        self._s3_client = self._session.client("s3", config=BOTO_CONFIG)

    def parse_s3_event(self, event: dict[str, Any]) -> dict[str, str]:
        """
        Parse an S3 event notification to extract bucket and key.

        Args:
            event: S3 event notification payload.

        Returns:
            Dict with 'bucket' and 'key'.

        Raises:
            ValueError: If the event does not contain valid S3 records.
        """
        records = event.get("Records", [])
        if not records:
            raise ValueError("No Records found in S3 event")

        s3_info = records[0].get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", "")
        key = unquote_plus(s3_info.get("object", {}).get("key", ""))

        if not bucket or not key:
            raise ValueError(f"Missing bucket or key in S3 event: bucket={bucket}, key={key}")

        logger.info("Parsed S3 event: bucket=%s, key=%s", bucket, key)
        return {"bucket": bucket, "key": key}

    def read_report(self, bucket: str, key: str) -> list[dict[str, Any]]:
        """
        Download and parse a Part 1 JSON report from S3.

        Args:
            bucket: S3 bucket name.
            key: S3 object key.

        Returns:
            List of recommendation dicts from the report.
        """
        logger.info("Reading report from s3://%s/%s", bucket, key)

        response = self._s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        report = json.loads(body)

        recommendations = report.get("recommendations", [])
        logger.info(
            "Loaded %d recommendations from report (generated at: %s)",
            len(recommendations),
            report.get("report_metadata", {}).get("generated_at", "unknown"),
        )
        return recommendations

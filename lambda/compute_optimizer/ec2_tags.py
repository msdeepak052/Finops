"""
EC2 Tag Fetcher

Retrieves tags for EC2 instances using the describe_instances API
with pagination support. Enriches recommendation data with instance
names and full tag maps.
"""

import logging
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOTO_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
)

# EC2 describe_instances supports up to 1000 instance IDs per call
BATCH_SIZE = 200


class EC2TagFetcher:
    """Fetches EC2 tags in batches and enriches recommendation records."""

    def __init__(self, session: boto3.Session | None = None):
        self._session = session or boto3.Session()
        self._client = self._session.client("ec2", config=BOTO_CONFIG)

    def fetch_tags_for_instances(self, instance_ids: list[str]) -> dict[str, dict[str, str]]:
        """
        Fetch tags for a list of EC2 instance IDs.

        Args:
            instance_ids: List of EC2 instance IDs (e.g., ["i-0abc123", ...]).

        Returns:
            Dict mapping instance_id -> {tag_key: tag_value}.
        """
        if not instance_ids:
            return {}

        all_tags: dict[str, dict[str, str]] = {}

        # Process in batches to respect API limits
        for i in range(0, len(instance_ids), BATCH_SIZE):
            batch = instance_ids[i : i + BATCH_SIZE]
            logger.info(
                "Fetching tags for instances %d-%d of %d",
                i + 1,
                min(i + BATCH_SIZE, len(instance_ids)),
                len(instance_ids),
            )
            batch_tags = self._fetch_batch(batch)
            all_tags.update(batch_tags)

        return all_tags

    def _fetch_batch(self, instance_ids: list[str]) -> dict[str, dict[str, str]]:
        """Fetch tags for a single batch of instance IDs with pagination."""
        tags_map: dict[str, dict[str, str]] = {}
        paginator = self._client.get_paginator("describe_instances")

        page_iterator = paginator.paginate(
            InstanceIds=instance_ids,
            PaginationConfig={"PageSize": 100},
        )

        try:
            for page in page_iterator:
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        iid = instance["InstanceId"]
                        raw_tags = instance.get("Tags", [])
                        tags_map[iid] = {
                            tag["Key"]: tag["Value"] for tag in raw_tags
                        }
        except self._client.exceptions.ClientError as e:
            # Some instances may have been terminated between recommendation
            # fetch and tag fetch. Log and continue gracefully.
            error_code = e.response["Error"]["Code"]
            if error_code == "InvalidInstanceID.NotFound":
                logger.warning(
                    "Some instances not found (likely terminated): %s", e
                )
            else:
                raise

        return tags_map

    def enrich_recommendations(
        self, recommendations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Enrich recommendation records with EC2 tags and instance names.

        Modifies records in-place and returns the same list.
        """
        instance_ids = [r["instance_id"] for r in recommendations if r.get("instance_id")]
        if not instance_ids:
            return recommendations

        tags_map = self.fetch_tags_for_instances(instance_ids)

        for rec in recommendations:
            iid = rec["instance_id"]
            tags = tags_map.get(iid, {})
            rec["tags"] = tags
            rec["instance_name"] = tags.get("Name", "")

        logger.info("Enriched %d recommendations with tags", len(recommendations))
        return recommendations

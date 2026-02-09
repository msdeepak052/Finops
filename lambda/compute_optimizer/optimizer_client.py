"""
AWS Compute Optimizer Client

Fetches EC2 instance recommendations from AWS Compute Optimizer with
full pagination support, retry logic, and structured data extraction.
"""

import logging
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Retry configuration following AWS best practices
BOTO_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
    max_pool_connections=10,
)


class ComputeOptimizerClient:
    """Fetches and structures EC2 recommendations from Compute Optimizer."""

    # Fields we extract from each recommendation
    FINDING_REASON_CODES_CPU = {
        "CPUOverprovisioned",
        "CPUUnderprovisioned",
    }
    FINDING_REASON_CODES_MEMORY = {
        "MemoryOverprovisioned",
        "MemoryUnderprovisioned",
    }

    def __init__(self, session: boto3.Session | None = None, account_ids: list[str] | None = None):
        """
        Args:
            session: Optional boto3 session (useful for cross-account assume-role).
            account_ids: Optional list of AWS account IDs for multi-account queries.
                         If None, queries the caller's account only.
        """
        self._session = session or boto3.Session()
        self._client = self._session.client("compute-optimizer", config=BOTO_CONFIG)
        self._account_ids = account_ids or []

    def get_ec2_recommendations(self) -> list[dict[str, Any]]:
        """
        Fetch all EC2 instance recommendations from Compute Optimizer.

        Returns a list of structured recommendation dicts, one per instance.
        Handles pagination automatically.
        """
        all_recommendations: list[dict[str, Any]] = []
        next_token = None

        logger.info("Fetching EC2 instance recommendations from Compute Optimizer...")

        while True:
            kwargs: dict[str, Any] = {"maxResults": 1000}
            if next_token:
                kwargs["nextToken"] = next_token
            if self._account_ids:
                kwargs["accountIds"] = self._account_ids

            response = self._client.get_ec2_instance_recommendations(**kwargs)

            raw_recommendations = response.get("instanceRecommendations", [])
            logger.info("Fetched batch of %d recommendations", len(raw_recommendations))

            for rec in raw_recommendations:
                structured = self._structure_recommendation(rec)
                if structured:
                    all_recommendations.append(structured)

            next_token = response.get("nextToken")
            if not next_token:
                break

        logger.info("Total recommendations fetched: %d", len(all_recommendations))
        return all_recommendations

    def _structure_recommendation(self, rec: dict[str, Any]) -> dict[str, Any] | None:
        """Extract and flatten a single Compute Optimizer recommendation."""
        try:
            instance_arn = rec.get("instanceArn", "")
            instance_id = instance_arn.split("/")[-1] if "/" in instance_arn else rec.get("instanceName", "")

            # Current instance details
            current_type = rec.get("currentInstanceType", "")
            finding = rec.get("finding", "")
            finding_reasons = rec.get("findingReasonCodes", [])

            # Separate CPU and memory finding reasons
            cpu_reasons = [r for r in finding_reasons if r in self.FINDING_REASON_CODES_CPU]
            memory_reasons = [r for r in finding_reasons if r in self.FINDING_REASON_CODES_MEMORY]

            # Current performance risk
            current_perf_risk = rec.get("currentPerformanceRisk", "N/A")

            # Effective performance risk from utilization metrics
            effective_perf_risk = rec.get("effectiveRecommendationPreferences", {}).get(
                "inferredWorkloadTypes", []
            )

            # Top recommendation (first in the list)
            recommendation_options = rec.get("recommendationOptions", [])
            top_rec = recommendation_options[0] if recommendation_options else {}

            recommended_type = top_rec.get("instanceType", "")
            rec_perf_risk = top_rec.get("performanceRisk", 0)
            rec_migration_effort = top_rec.get("migrationEffort", "Unknown")

            # Savings and pricing from savingsOpportunity
            savings_opp = top_rec.get("savingsOpportunity", {})
            savings_pct = savings_opp.get("savingsOpportunityPercentage", 0)

            estimated_monthly_savings = savings_opp.get("estimatedMonthlySavings", {})
            savings_value = estimated_monthly_savings.get("value", 0)
            savings_currency = estimated_monthly_savings.get("currency", "USD")

            # Savings after discounts (from savingsOpportunityAfterDiscounts if available)
            savings_after_discounts_block = top_rec.get("savingsOpportunityAfterDiscounts", {})
            savings_after_discounts_pct = savings_after_discounts_block.get(
                "savingsOpportunityPercentage", 0
            )
            savings_after_discounts_est = savings_after_discounts_block.get(
                "estimatedMonthlySavings", {}
            )
            savings_after_discounts_value = savings_after_discounts_est.get("value", 0)

            # Instance state
            rec_instance_state = top_rec.get("instanceState", "running")

            return {
                "instance_id": instance_id,
                "instance_arn": instance_arn,
                "account_id": rec.get("accountId", ""),
                "instance_name": "",  # Populated later from EC2 tags
                "current_instance_type": current_type,
                "finding": finding,
                "finding_reasons": finding_reasons,
                "cpu_finding_reasons": cpu_reasons,
                "memory_finding_reasons": memory_reasons,
                "current_performance_risk": current_perf_risk,
                "inferred_workload_types": effective_perf_risk,
                "recommended_instance_type": recommended_type,
                "recommendation_instance_state": rec_instance_state,
                "recommended_performance_risk": rec_perf_risk,
                "recommended_migration_effort": rec_migration_effort,
                "savings_opportunity_pct": savings_pct,
                "estimated_monthly_savings_on_demand": savings_value,
                "savings_currency": savings_currency,
                "savings_after_discounts_pct": savings_after_discounts_pct,
                "estimated_monthly_savings_after_discounts": savings_after_discounts_value,
                "current_on_demand_price": 0.0,  # Populated by CostCalculator
                "recommended_on_demand_price": 0.0,  # Populated by CostCalculator
                "current_instance_price": 0.0,  # Populated by CostCalculator
                "recommended_instance_price": 0.0,  # Populated by CostCalculator
                "price_difference": 0.0,  # Populated by CostCalculator
                "tags": {},  # Populated by EC2TagFetcher
            }
        except Exception:
            logger.exception("Failed to structure recommendation for ARN: %s", rec.get("instanceArn"))
            return None

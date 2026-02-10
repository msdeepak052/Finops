"""
Cost Calculator

Fetches On-Demand pricing from the AWS Pricing API for EC2 instance types
and enriches recommendations with current/recommended pricing and savings.

Uses the Pricing API (us-east-1 endpoint) with caching to minimize API calls.
"""

import logging
from typing import Any

import boto3
import json
from botocore.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOTO_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
)

# Monthly hours assumption (730 = average hours/month)
MONTHLY_HOURS = 730.0


class CostCalculator:
    """Fetches EC2 pricing and calculates cost differences."""

    def __init__(self, session: boto3.Session | None = None, region: str = "us-east-1"):
        """
        Args:
            session: Optional boto3 session.
            region: AWS region for pricing lookups. Pricing API is in us-east-1.
        """
        self._session = session or boto3.Session()
        # Pricing API is only available in us-east-1 and ap-south-1
        self._pricing_client = self._session.client(
            "pricing", region_name="us-east-1", config=BOTO_CONFIG
        )
        self._target_region = region
        self._price_cache: dict[str, float] = {}

    def get_on_demand_price(self, instance_type: str) -> float:
        """
        Get the hourly On-Demand price for an instance type.

        Results are cached to avoid redundant API calls.

        Args:
            instance_type: EC2 instance type (e.g., "m5.xlarge").

        Returns:
            Hourly On-Demand price in USD. Returns 0.0 if not found.
        """
        if instance_type in self._price_cache:
            return self._price_cache[instance_type]

        if not instance_type:
            return 0.0

        try:
            region_name = self._get_region_long_name(self._target_region)

            response = self._pricing_client.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": region_name},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                    {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                ],
                MaxResults=1,
            )

            price_list = response.get("PriceList", [])
            if price_list:
                price_data = json.loads(price_list[0]) if isinstance(price_list[0], str) else price_list[0]
                on_demand = price_data.get("terms", {}).get("OnDemand", {})
                for term in on_demand.values():
                    for dimension in term.get("priceDimensions", {}).values():
                        price_per_unit = dimension.get("pricePerUnit", {})
                        usd_price = float(price_per_unit.get("USD", "0"))
                        if usd_price > 0:
                            self._price_cache[instance_type] = usd_price
                            return usd_price

            logger.warning("No On-Demand price found for %s in %s", instance_type, self._target_region)
            self._price_cache[instance_type] = 0.0
            return 0.0

        except Exception:
            logger.exception("Error fetching price for %s", instance_type)
            self._price_cache[instance_type] = 0.0
            return 0.0

    def enrich_recommendations(self, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Enrich recommendations with On-Demand pricing and cost differences.

        Calculates:
          - current_on_demand_price (monthly)
          - recommended_on_demand_price (monthly)
          - current_instance_price (hourly)
          - recommended_instance_price (hourly)
          - price_difference (monthly saving, positive = cheaper recommendation)

        Modifies records in-place and returns the same list.
        """
        # Collect unique instance types to minimize pricing API calls
        instance_types = set()
        for rec in recommendations:
            if rec.get("current_instance_type"):
                instance_types.add(rec["current_instance_type"])
            if rec.get("recommended_instance_type"):
                instance_types.add(rec["recommended_instance_type"])

        logger.info("Fetching On-Demand prices for %d unique instance types", len(instance_types))

        # Pre-warm cache
        for itype in instance_types:
            self.get_on_demand_price(itype)

        # Enrich each recommendation
        for rec in recommendations:
            current_hourly = self.get_on_demand_price(rec.get("current_instance_type", ""))
            recommended_hourly = self.get_on_demand_price(rec.get("recommended_instance_type", ""))

            rec["current_instance_price"] = round(current_hourly, 6)
            rec["recommended_instance_price"] = round(recommended_hourly, 6)
            rec["current_on_demand_price"] = round(current_hourly * MONTHLY_HOURS, 2)
            rec["recommended_on_demand_price"] = round(recommended_hourly * MONTHLY_HOURS, 2)
            rec["price_difference"] = round(
                rec["current_on_demand_price"] - rec["recommended_on_demand_price"], 2
            )

        logger.info("Enriched %d recommendations with pricing data", len(recommendations))
        return recommendations

    @staticmethod
    def _get_region_long_name(region_code: str) -> str:
        """Map AWS region code to the long name used by the Pricing API."""
        region_map = {
            "us-east-1": "US East (N. Virginia)",
            "us-east-2": "US East (Ohio)",
            "us-west-1": "US West (N. California)",
            "us-west-2": "US West (Oregon)",
            "af-south-1": "Africa (Cape Town)",
            "ap-east-1": "Asia Pacific (Hong Kong)",
            "ap-south-1": "Asia Pacific (Mumbai)",
            "ap-south-2": "Asia Pacific (Hyderabad)",
            "ap-southeast-1": "Asia Pacific (Singapore)",
            "ap-southeast-2": "Asia Pacific (Sydney)",
            "ap-southeast-3": "Asia Pacific (Jakarta)",
            "ap-northeast-1": "Asia Pacific (Tokyo)",
            "ap-northeast-2": "Asia Pacific (Seoul)",
            "ap-northeast-3": "Asia Pacific (Osaka)",
            "ca-central-1": "Canada (Central)",
            "eu-central-1": "Europe (Frankfurt)",
            "eu-central-2": "Europe (Zurich)",
            "eu-west-1": "Europe (Ireland)",
            "eu-west-2": "Europe (London)",
            "eu-west-3": "Europe (Paris)",
            "eu-south-1": "Europe (Milan)",
            "eu-south-2": "Europe (Spain)",
            "eu-north-1": "Europe (Stockholm)",
            "me-south-1": "Middle East (Bahrain)",
            "me-central-1": "Middle East (UAE)",
            "sa-east-1": "South America (Sao Paulo)",
        }
        return region_map.get(region_code, region_code)

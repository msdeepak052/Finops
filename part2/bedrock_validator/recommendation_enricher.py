"""
Recommendation Enricher

Orchestrates the validation pipeline: checks each recommendation against
the allow-list, invokes Bedrock AI for non-approved types, and enriches
the recommendation data with validation results.
"""

import logging
from typing import Any

from .allowlist_checker import AllowListChecker
from .bedrock_client import BedrockClient
from .prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RecommendationEnricher:
    """Validates and enriches recommendations using allow-list + Bedrock AI."""

    def __init__(
        self,
        checker: AllowListChecker,
        bedrock: BedrockClient,
    ):
        self._checker = checker
        self._bedrock = bedrock

    def enrich_all(self, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate and enrich all recommendations.

        For each recommendation:
          - If recommended type is in allow-list → auto-approve with discount tier
          - If not → query Bedrock AI for alternatives from allow-list
          - If Bedrock fails → mark as failed, continue with next

        Args:
            recommendations: List of Part 1 recommendation dicts (display-key format).

        Returns:
            Enriched recommendations with validation fields added.
        """
        allowed_types = self._checker.get_all_allowed_types()
        enriched = []

        for i, rec in enumerate(recommendations):
            rec_type = rec.get("Recommended Instance Type", "")
            instance_id = rec.get("Instance ID", "unknown")
            logger.info(
                "Validating %d/%d: %s → %s",
                i + 1, len(recommendations), instance_id, rec_type,
            )

            if self._checker.is_allowed(rec_type):
                enriched_rec = self._approve_allowed(rec)
            else:
                enriched_rec = self._validate_with_bedrock(rec, allowed_types)

            enriched.append(enriched_rec)

        approved = sum(1 for r in enriched if r.get("validation_status") == "Approved (Allowed Instance)")
        ai_recommended = sum(1 for r in enriched if r.get("validation_status") == "AI-Recommended Alternative")
        failed = sum(1 for r in enriched if r.get("validation_status") == "AI Validation Failed")

        logger.info(
            "Enrichment complete: %d approved, %d AI-recommended, %d failed (total: %d)",
            approved, ai_recommended, failed, len(enriched),
        )
        return enriched

    def _approve_allowed(self, rec: dict[str, Any]) -> dict[str, Any]:
        """Approve a recommendation whose type is in the allow-list."""
        rec_type = rec.get("Recommended Instance Type", "")
        tier = self._checker.get_tier(rec_type)

        enriched = {**rec}
        enriched["validation_status"] = "Approved (Allowed Instance)"
        enriched["final_recommendation"] = rec_type
        enriched["discount_tier_name"] = tier["tier_name"] if tier else ""
        enriched["discount_percent"] = tier["discount_percent"] if tier else 0

        # Calculate discounted pricing
        recommended_monthly = float(rec.get("Recommended Monthly On-Demand Price (USD)", 0))
        discount = enriched["discount_percent"] / 100
        discounted_price = round(recommended_monthly * (1 - discount), 2)
        current_monthly = float(rec.get("Current Monthly On-Demand Price (USD)", 0))

        enriched["discounted_monthly_price"] = discounted_price
        enriched["estimated_monthly_savings_with_discount"] = round(current_monthly - discounted_price, 2)

        enriched["ai_alternatives"] = ""
        enriched["ai_analysis_summary"] = "Instance type is pre-approved in the organization's allow-list."
        enriched["ai_confidence"] = "high"
        enriched["bedrock_model"] = ""

        logger.info("Approved: %s (type %s in %s)", rec.get("Instance ID"), rec_type, tier["tier_name"] if tier else "?")
        return enriched

    def _validate_with_bedrock(
        self, rec: dict[str, Any], allowed_types: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Query Bedrock AI for alternative recommendations from the allow-list."""
        enriched = {**rec}

        try:
            system_prompt, user_prompt = PromptBuilder.build_validation_prompt(rec, allowed_types)
            result = self._bedrock.invoke(system_prompt, user_prompt)

            alternatives = result.get("alternatives", [])
            if not alternatives:
                raise ValueError("Bedrock returned no alternatives")

            # Use the top-ranked alternative
            best = alternatives[0]
            best_type = best.get("instance_type", "")
            tier = self._checker.get_tier(best_type)

            enriched["validation_status"] = "AI-Recommended Alternative"
            enriched["final_recommendation"] = best_type
            enriched["discount_tier_name"] = tier["tier_name"] if tier else ""
            enriched["discount_percent"] = tier["discount_percent"] if tier else 0

            # Calculate discounted pricing for the AI-recommended type
            # Use recommended price as proxy (actual price lookup would need Pricing API)
            recommended_monthly = float(rec.get("Recommended Monthly On-Demand Price (USD)", 0))
            discount = enriched["discount_percent"] / 100
            discounted_price = round(recommended_monthly * (1 - discount), 2)
            current_monthly = float(rec.get("Current Monthly On-Demand Price (USD)", 0))

            enriched["discounted_monthly_price"] = discounted_price
            enriched["estimated_monthly_savings_with_discount"] = round(current_monthly - discounted_price, 2)

            # Format alternatives as readable string
            alt_strings = []
            for alt in alternatives[:3]:
                alt_strings.append(
                    f"#{alt.get('rank', '?')}: {alt.get('instance_type', '?')} — {alt.get('reason', '')}"
                )
            enriched["ai_alternatives"] = "; ".join(alt_strings)
            enriched["ai_analysis_summary"] = result.get("analysis_summary", "")
            enriched["ai_confidence"] = result.get("confidence", "unknown")
            enriched["bedrock_model"] = self._bedrock.model_id

            logger.info(
                "AI recommendation for %s: %s → %s (confidence: %s)",
                rec.get("Instance ID"), rec.get("Recommended Instance Type"), best_type,
                enriched["ai_confidence"],
            )

        except Exception:
            logger.exception("Bedrock validation failed for %s", rec.get("Instance ID"))
            enriched["validation_status"] = "AI Validation Failed"
            enriched["final_recommendation"] = rec.get("Recommended Instance Type", "")
            enriched["discount_tier_name"] = ""
            enriched["discount_percent"] = 0
            enriched["discounted_monthly_price"] = 0
            enriched["estimated_monthly_savings_with_discount"] = 0
            enriched["ai_alternatives"] = ""
            enriched["ai_analysis_summary"] = "Bedrock AI validation failed. Using original CO recommendation."
            enriched["ai_confidence"] = ""
            enriched["bedrock_model"] = self._bedrock.model_id

        return enriched

"""Tests for RecommendationEnricher."""

from unittest.mock import MagicMock

import pytest

from bedrock_validator.recommendation_enricher import RecommendationEnricher


def _sample_recommendation(rec_type="m5.xlarge"):
    return {
        "Account ID": "111111111111",
        "Instance ID": "i-0abc123",
        "Instance Name": "web-server-1",
        "Finding": "OVER_PROVISIONED",
        "Current Instance Type": "m5.2xlarge",
        "Recommended Instance Type": rec_type,
        "Current Monthly On-Demand Price (USD)": 280.32,
        "Recommended Monthly On-Demand Price (USD)": 140.16,
        "Est. Monthly Savings On-Demand (USD)": 140.16,
    }


def _mock_checker(allowed_types=None, tier_info=None):
    checker = MagicMock()
    checker.get_all_allowed_types.return_value = allowed_types or [
        {"instance_type": "m5.xlarge", "family": "m5", "category": "General Purpose",
         "discount_percent": 50, "tier_name": "Tier 1 — Enterprise Reserved"},
    ]
    if tier_info:
        checker.is_allowed.return_value = True
        checker.get_tier.return_value = tier_info
    else:
        checker.is_allowed.return_value = False
        checker.get_tier.return_value = None
    return checker


def _mock_bedrock(alternatives=None, confidence="high"):
    bedrock = MagicMock()
    bedrock.model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock.invoke.return_value = {
        "alternatives": alternatives or [
            {"instance_type": "m5.xlarge", "reason": "Best match", "rank": 1},
        ],
        "analysis_summary": "m5.xlarge is the closest approved type.",
        "confidence": confidence,
    }
    return bedrock


class TestEnrichAllApproved:
    def test_approved_instance_gets_discount(self):
        tier_info = {
            "tier_name": "Tier 1 — Enterprise Reserved",
            "discount_percent": 50,
            "family": "m5",
            "category": "General Purpose",
        }
        checker = _mock_checker(tier_info=tier_info)
        bedrock = _mock_bedrock()

        enricher = RecommendationEnricher(checker, bedrock)
        results = enricher.enrich_all([_sample_recommendation("m5.xlarge")])

        assert len(results) == 1
        rec = results[0]
        assert rec["validation_status"] == "Approved (Allowed Instance)"
        assert rec["final_recommendation"] == "m5.xlarge"
        assert rec["discount_percent"] == 50
        assert rec["discount_tier_name"] == "Tier 1 — Enterprise Reserved"
        assert rec["discounted_monthly_price"] == 70.08  # 140.16 * 0.5
        assert rec["ai_confidence"] == "high"
        # Bedrock should NOT be called for approved types
        bedrock.invoke.assert_not_called()

    def test_approved_savings_calculation(self):
        tier_info = {
            "tier_name": "Tier 2 — Standard Reserved",
            "discount_percent": 35,
            "family": "t3",
            "category": "Burstable",
        }
        checker = _mock_checker(tier_info=tier_info)
        bedrock = _mock_bedrock()

        enricher = RecommendationEnricher(checker, bedrock)
        results = enricher.enrich_all([_sample_recommendation("t3.medium")])

        rec = results[0]
        # Discounted price = 140.16 * (1 - 0.35) = 91.10
        assert rec["discounted_monthly_price"] == 91.10
        # Savings = 280.32 - 91.10 = 189.22
        assert rec["estimated_monthly_savings_with_discount"] == 189.22


class TestEnrichAllAIRecommended:
    def test_non_allowed_triggers_bedrock(self):
        checker = _mock_checker()
        # After Bedrock returns, checker.get_tier needs to be called for the alternative
        checker.get_tier.side_effect = [
            None,  # First call for the original recommended type (not allowed)
            {"tier_name": "Tier 1", "discount_percent": 50, "family": "m5", "category": "General Purpose"},
        ]
        bedrock = _mock_bedrock()

        enricher = RecommendationEnricher(checker, bedrock)
        results = enricher.enrich_all([_sample_recommendation("m5a.xlarge")])

        rec = results[0]
        assert rec["validation_status"] == "AI-Recommended Alternative"
        assert rec["final_recommendation"] == "m5.xlarge"
        assert "m5.xlarge" in rec["ai_alternatives"]
        assert rec["ai_confidence"] == "high"
        assert rec["bedrock_model"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        bedrock.invoke.assert_called_once()

    def test_multiple_alternatives_formatted(self):
        checker = _mock_checker()
        checker.get_tier.return_value = {"tier_name": "Tier 1", "discount_percent": 50, "family": "m5", "category": "General Purpose"}
        bedrock = _mock_bedrock(alternatives=[
            {"instance_type": "m5.xlarge", "reason": "Best match", "rank": 1},
            {"instance_type": "m6i.xlarge", "reason": "Newer gen", "rank": 2},
            {"instance_type": "c5.xlarge", "reason": "Compute focused", "rank": 3},
        ])

        enricher = RecommendationEnricher(checker, bedrock)
        results = enricher.enrich_all([_sample_recommendation("m5a.xlarge")])

        rec = results[0]
        assert "#1: m5.xlarge" in rec["ai_alternatives"]
        assert "#2: m6i.xlarge" in rec["ai_alternatives"]
        assert "#3: c5.xlarge" in rec["ai_alternatives"]


class TestEnrichAllGracefulDegradation:
    def test_bedrock_failure_does_not_crash_batch(self):
        checker = _mock_checker()
        bedrock = _mock_bedrock()
        bedrock.invoke.side_effect = Exception("Bedrock timeout")

        enricher = RecommendationEnricher(checker, bedrock)
        results = enricher.enrich_all([_sample_recommendation("m5a.xlarge")])

        assert len(results) == 1
        rec = results[0]
        assert rec["validation_status"] == "AI Validation Failed"
        assert rec["final_recommendation"] == "m5a.xlarge"  # Falls back to original
        assert rec["ai_confidence"] == ""

    def test_mixed_batch_continues_after_failure(self):
        checker = _mock_checker()
        # First is not allowed (will fail), second is not allowed (will succeed)
        tier_info = {"tier_name": "Tier 1", "discount_percent": 50, "family": "m5", "category": "General Purpose"}
        checker.get_tier.side_effect = [
            None,  # First check - not in tier
            None,  # Second check - not in tier
            tier_info,  # get_tier for AI result of second rec
        ]
        bedrock = _mock_bedrock()
        bedrock.invoke.side_effect = [
            Exception("Timeout"),  # First fails
            {  # Second succeeds
                "alternatives": [{"instance_type": "m5.xlarge", "reason": "OK", "rank": 1}],
                "analysis_summary": "Good match",
                "confidence": "high",
            },
        ]

        recs = [
            _sample_recommendation("x1.xlarge"),
            _sample_recommendation("x2.large"),
        ]
        recs[1]["Instance ID"] = "i-0def456"

        enricher = RecommendationEnricher(checker, bedrock)
        results = enricher.enrich_all(recs)

        assert len(results) == 2
        assert results[0]["validation_status"] == "AI Validation Failed"
        assert results[1]["validation_status"] == "AI-Recommended Alternative"

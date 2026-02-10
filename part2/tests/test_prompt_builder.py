"""Tests for PromptBuilder."""

from bedrock_validator.prompt_builder import PromptBuilder


def _sample_recommendation():
    return {
        "Instance ID": "i-0abc123",
        "Instance Name": "web-server-1",
        "Finding": "OVER_PROVISIONED",
        "Current Instance Type": "m5.2xlarge",
        "Recommended Instance Type": "m5a.xlarge",
        "Current Monthly On-Demand Price (USD)": 280.32,
        "Recommended Monthly On-Demand Price (USD)": 140.16,
        "Est. Monthly Savings On-Demand (USD)": 140.16,
    }


def _sample_allowed_types():
    return [
        {
            "instance_type": "m5.xlarge",
            "family": "m5",
            "category": "General Purpose",
            "discount_percent": 50,
            "tier_name": "Tier 1",
        },
        {
            "instance_type": "c5.xlarge",
            "family": "c5",
            "category": "Compute Optimized",
            "discount_percent": 50,
            "tier_name": "Tier 1",
        },
    ]


class TestBuildValidationPrompt:
    def test_returns_system_and_user_prompts(self):
        system, user = PromptBuilder.build_validation_prompt(
            _sample_recommendation(), _sample_allowed_types()
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_user_prompt_contains_instance_details(self):
        _, user = PromptBuilder.build_validation_prompt(
            _sample_recommendation(), _sample_allowed_types()
        )
        assert "m5.2xlarge" in user
        assert "m5a.xlarge" in user
        assert "i-0abc123" in user
        assert "web-server-1" in user
        assert "OVER_PROVISIONED" in user

    def test_user_prompt_contains_allowlist_table(self):
        _, user = PromptBuilder.build_validation_prompt(
            _sample_recommendation(), _sample_allowed_types()
        )
        assert "m5.xlarge" in user
        assert "c5.xlarge" in user
        assert "50%" in user

    def test_system_prompt_requires_json(self):
        system, _ = PromptBuilder.build_validation_prompt(
            _sample_recommendation(), _sample_allowed_types()
        )
        assert "JSON" in system

    def test_user_prompt_contains_json_format(self):
        _, user = PromptBuilder.build_validation_prompt(
            _sample_recommendation(), _sample_allowed_types()
        )
        assert "alternatives" in user
        assert "analysis_summary" in user
        assert "confidence" in user


class TestFormatAllowlistTable:
    def test_table_has_header(self):
        table = PromptBuilder._format_allowlist_table(_sample_allowed_types())
        assert "Instance Type" in table
        assert "Family" in table
        assert "Discount" in table

    def test_table_has_entries(self):
        table = PromptBuilder._format_allowlist_table(_sample_allowed_types())
        assert "m5.xlarge" in table
        assert "c5.xlarge" in table

    def test_empty_allowlist(self):
        table = PromptBuilder._format_allowlist_table([])
        assert "Instance Type" in table  # Header still present

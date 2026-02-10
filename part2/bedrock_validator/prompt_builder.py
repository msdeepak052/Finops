"""
Prompt Builder

Constructs structured prompts for Bedrock AI validation of
EC2 instance recommendations against the organization's allow-list.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SYSTEM_PROMPT = """You are an AWS EC2 instance type expert. Your role is to validate \
Compute Optimizer recommendations against an organization's approved instance type \
allow-list and suggest the best alternatives when the recommended type is not approved.

IMPORTANT: Respond ONLY with a valid JSON object. No explanations, no markdown, no extra text."""

USER_PROMPT_TEMPLATE = """## Task
The AWS Compute Optimizer recommends migrating from **{current_type}** to **{recommended_type}**, \
but **{recommended_type}** is NOT in the organization's approved allow-list.

Select the best alternative(s) from the allow-list below.

## Current Instance Details
- **Current Type**: {current_type}
- **Current Monthly Cost**: ${current_monthly_cost}
- **Finding**: {finding}
- **Instance Name**: {instance_name}
- **Instance ID**: {instance_id}

## Compute Optimizer Recommendation
- **Recommended Type**: {recommended_type}
- **Recommended Monthly Cost**: ${recommended_monthly_cost}
- **Estimated Savings**: ${estimated_savings}

## Approved Allow-List
{allowlist_table}

## Selection Criteria (Priority Order)
1. **Price** — closest to or lower than the recommended type's cost
2. **vCPU count** — should meet or exceed the recommended type
3. **Memory** — should meet or exceed the recommended type
4. **Storage/network** — similar or better I/O characteristics
5. **20% headroom rule** — prefer types with ~20% more capacity than minimum required
6. **Favor higher discount tiers** — Tier 1 (50%) over Tier 2 (35%) when specs are comparable

## Required JSON Response Format
{{
  "alternatives": [
    {{
      "instance_type": "<type>",
      "reason": "<brief justification>",
      "rank": 1
    }}
  ],
  "analysis_summary": "<2-3 sentence summary of the analysis>",
  "confidence": "<high|medium|low>"
}}

Provide up to 3 ranked alternatives. Rank 1 is the best match."""


class PromptBuilder:
    """Builds structured prompts for Bedrock validation."""

    @staticmethod
    def build_validation_prompt(
        recommendation: dict[str, Any],
        allowed_types: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """
        Build a validation prompt for a single recommendation.

        Args:
            recommendation: Part 1 recommendation dict (display-key format).
            allowed_types: Output of AllowListChecker.get_all_allowed_types().

        Returns:
            Tuple of (system_prompt, user_prompt).
        """
        allowlist_table = PromptBuilder._format_allowlist_table(allowed_types)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            current_type=recommendation.get("Current Instance Type", "unknown"),
            recommended_type=recommendation.get("Recommended Instance Type", "unknown"),
            current_monthly_cost=recommendation.get("Current Monthly On-Demand Price (USD)", 0),
            recommended_monthly_cost=recommendation.get("Recommended Monthly On-Demand Price (USD)", 0),
            estimated_savings=recommendation.get("Est. Monthly Savings On-Demand (USD)", 0),
            finding=recommendation.get("Finding", "unknown"),
            instance_name=recommendation.get("Instance Name", "unnamed"),
            instance_id=recommendation.get("Instance ID", "unknown"),
            allowlist_table=allowlist_table,
        )

        return SYSTEM_PROMPT, user_prompt

    @staticmethod
    def _format_allowlist_table(allowed_types: list[dict[str, Any]]) -> str:
        """Format allowed types as a readable table for the prompt."""
        lines = ["| Instance Type | Family | Category | Discount |"]
        lines.append("|---|---|---|---|")
        for entry in allowed_types:
            lines.append(
                f"| {entry['instance_type']} | {entry['family']} | "
                f"{entry['category']} | {entry['discount_percent']}% |"
            )
        return "\n".join(lines)

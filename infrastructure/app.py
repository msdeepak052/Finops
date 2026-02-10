"""
CDK App Entry Point

Usage:
  cdk synth
  cdk deploy
  cdk deploy --context account_ids="111111111111,222222222222"
  cdk deploy --context bedrock_model_id="nova" --context bedrock_region="us-west-2"
"""

import aws_cdk as cdk

from infrastructure.stack import FinOpsComputeOptimizerStack


def main() -> None:
    app = cdk.App()

    # Read context values (set in cdk.json or via --context CLI flag)
    schedule = app.node.try_get_context("schedule_expression") or "rate(24 hours)"
    retention = int(app.node.try_get_context("report_retention_days") or 90)
    account_ids_raw = app.node.try_get_context("account_ids") or ""
    account_ids = [a.strip() for a in account_ids_raw.split(",") if a.strip()] if account_ids_raw else []
    bedrock_model_id = app.node.try_get_context("bedrock_model_id") or "claude"
    bedrock_region = app.node.try_get_context("bedrock_region") or "us-east-1"

    FinOpsComputeOptimizerStack(
        app,
        "FinOpsComputeOptimizerStack",
        schedule_expression=schedule,
        report_retention_days=retention,
        account_ids=account_ids,
        bedrock_model_id=bedrock_model_id,
        bedrock_region=bedrock_region,
        description="EC2 Cost Optimization Report — Compute Optimizer + Bedrock AI Validation",
    )

    app.synth()


if __name__ == "__main__":
    main()

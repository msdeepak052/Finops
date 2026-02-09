"""
AWS CDK Stack — EC2 Cost Optimization Report Infrastructure

Deploys:
  - S3 bucket for report storage (encrypted, lifecycle-managed)
  - Lambda function running the analysis pipeline
  - IAM role with least-privilege permissions
  - EventBridge rule for scheduled execution (daily)
  - CloudWatch log group with retention

Why CDK over raw Boto3 for infrastructure?
  - Declarative: infrastructure is version-controlled and repeatable
  - Drift detection: CDK tracks actual vs desired state
  - IAM synthesis: CDK auto-generates least-privilege policies
  - Multi-account: CDK supports cross-account deployments natively
  - Rollback: CloudFormation provides automatic rollback on failure
"""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct


class FinOpsComputeOptimizerStack(Stack):
    """CDK Stack for the EC2 Cost Optimization Report solution."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        schedule_expression: str = "rate(24 hours)",
        report_retention_days: int = 90,
        account_ids: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 Bucket for Reports ───────────────────────────────────
        report_bucket = s3.Bucket(
            self,
            "ReportBucket",
            bucket_name=None,  # Auto-generated unique name
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireOldReports",
                    expiration=Duration.days(report_retention_days),
                    noncurrent_version_expiration=Duration.days(30),
                ),
            ],
        )

        # ── CloudWatch Log Group ────────────────────────────────────
        log_group = logs.LogGroup(
            self,
            "LambdaLogGroup",
            log_group_name="/aws/lambda/finops-compute-optimizer",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── IAM Role for Lambda (Least Privilege) ───────────────────
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for FinOps Compute Optimizer Lambda",
        )

        # CloudWatch Logs — write only
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchLogs",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[log_group.log_group_arn, f"{log_group.log_group_arn}:*"],
            )
        )

        # Compute Optimizer — read-only EC2 recommendations
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="ComputeOptimizerReadOnly",
                effect=iam.Effect.ALLOW,
                actions=[
                    "compute-optimizer:GetEC2InstanceRecommendations",
                    "compute-optimizer:GetEnrollmentStatus",
                    "compute-optimizer:GetRecommendationSummaries",
                ],
                resources=["*"],
            )
        )

        # EC2 — describe instances and tags only
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="EC2DescribeOnly",
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:DescribeInstances",
                    "ec2:DescribeTags",
                ],
                resources=["*"],
            )
        )

        # Pricing API — read-only
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="PricingReadOnly",
                effect=iam.Effect.ALLOW,
                actions=[
                    "pricing:GetProducts",
                    "pricing:DescribeServices",
                ],
                resources=["*"],
            )
        )

        # S3 — write to report bucket only
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3ReportWrite",
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                ],
                resources=[f"{report_bucket.bucket_arn}/*"],
            )
        )

        # ── Lambda Function ─────────────────────────────────────────
        account_ids_csv = ",".join(account_ids) if account_ids else ""

        lambda_fn = _lambda.Function(
            self,
            "ComputeOptimizerLambda",
            function_name="finops-compute-optimizer-report",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambda"),
            role=lambda_role,
            timeout=Duration.minutes(10),
            memory_size=512,
            environment={
                "REPORT_BUCKET": report_bucket.bucket_name,
                "REPORT_PREFIX": "reports",
                "ACCOUNT_IDS": account_ids_csv,
                "POWERTOOLS_SERVICE_NAME": "finops-compute-optimizer",
            },
            log_group=log_group,
        )

        # ── EventBridge Schedule (Daily Trigger) ────────────────────
        rule = events.Rule(
            self,
            "DailySchedule",
            rule_name="finops-compute-optimizer-daily",
            description="Triggers EC2 cost optimization report generation daily",
            schedule=events.Schedule.expression(schedule_expression),
            enabled=True,
        )
        rule.add_target(targets.LambdaFunction(lambda_fn))

        # ── Tags ────────────────────────────────────────────────────
        Tags.of(self).add("Project", "FinOps")
        Tags.of(self).add("Component", "ComputeOptimizer")
        Tags.of(self).add("ManagedBy", "CDK")

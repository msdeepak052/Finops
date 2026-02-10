"""
AWS CDK Stack — EC2 Cost Optimization Report Infrastructure

Deploys:
  Part 1: Compute Optimizer analysis pipeline
    - S3 bucket for report storage (encrypted, lifecycle-managed)
    - Lambda function running the analysis pipeline
    - IAM role with least-privilege permissions
    - EventBridge rule for scheduled execution (daily)
    - CloudWatch log group with retention

  Part 2: Bedrock AI recommendation validation
    - Lambda function for AI-based validation
    - IAM role with Bedrock + S3 read/write permissions
    - S3 event notification to trigger on Part 1 JSON uploads
    - CloudWatch log group with retention
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
    aws_s3_notifications as s3n,
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
        bedrock_model_id: str = "claude",
        bedrock_region: str = "us-east-1",
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

        # ================================================================
        # Part 1: Compute Optimizer Analysis Pipeline
        # ================================================================

        # ── Part 1 CloudWatch Log Group ──────────────────────────────
        part1_log_group = logs.LogGroup(
            self,
            "LambdaLogGroup",
            log_group_name="/aws/lambda/finops-compute-optimizer",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── Part 1 IAM Role (Least Privilege) ────────────────────────
        part1_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for FinOps Compute Optimizer Lambda (Part 1)",
        )

        # CloudWatch Logs — write only
        part1_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchLogs",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[part1_log_group.log_group_arn, f"{part1_log_group.log_group_arn}:*"],
            )
        )

        # Compute Optimizer — read-only EC2 recommendations
        part1_role.add_to_policy(
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
        part1_role.add_to_policy(
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
        part1_role.add_to_policy(
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
        part1_role.add_to_policy(
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

        # ── Part 1 Lambda Function ───────────────────────────────────
        account_ids_csv = ",".join(account_ids) if account_ids else ""

        part1_lambda = _lambda.Function(
            self,
            "ComputeOptimizerLambda",
            function_name="finops-compute-optimizer-report",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("part1"),
            role=part1_role,
            timeout=Duration.minutes(10),
            memory_size=512,
            environment={
                "REPORT_BUCKET": report_bucket.bucket_name,
                "REPORT_PREFIX": "reports",
                "ACCOUNT_IDS": account_ids_csv,
                "POWERTOOLS_SERVICE_NAME": "finops-compute-optimizer",
            },
            log_group=part1_log_group,
        )

        # ── EventBridge Schedule (Daily Trigger) ─────────────────────
        rule = events.Rule(
            self,
            "DailySchedule",
            rule_name="finops-compute-optimizer-daily",
            description="Triggers EC2 cost optimization report generation daily",
            schedule=events.Schedule.expression(schedule_expression),
            enabled=True,
        )
        rule.add_target(targets.LambdaFunction(part1_lambda))

        # ================================================================
        # Part 2: Bedrock AI Recommendation Validation
        # ================================================================

        # ── Part 2 CloudWatch Log Group ──────────────────────────────
        part2_log_group = logs.LogGroup(
            self,
            "Part2LambdaLogGroup",
            log_group_name="/aws/lambda/finops-bedrock-validator",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── Part 2 IAM Role (Least Privilege) ────────────────────────
        part2_role = iam.Role(
            self,
            "Part2LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for FinOps Bedrock Validator Lambda (Part 2)",
        )

        # CloudWatch Logs — write only
        part2_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchLogs",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[part2_log_group.log_group_arn, f"{part2_log_group.log_group_arn}:*"],
            )
        )

        # S3 — read Part 1 reports + write validated reports
        part2_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3ReportReadWrite",
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                ],
                resources=[f"{report_bucket.bucket_arn}/*"],
            )
        )

        # Bedrock — invoke model for AI validation
        part2_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvoke",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:Converse",
                ],
                resources=["*"],
            )
        )

        # ── Part 2 Lambda Function ───────────────────────────────────
        part2_lambda = _lambda.Function(
            self,
            "BedrockValidatorLambda",
            function_name="finops-bedrock-validator",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset(
                "part2",
                exclude=["tests", "__pycache__", "*.pyc"],
            ),
            role=part2_role,
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment={
                "REPORT_BUCKET": report_bucket.bucket_name,
                "REPORT_PREFIX": "reports",
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "BEDROCK_REGION": bedrock_region,
                "POWERTOOLS_SERVICE_NAME": "finops-bedrock-validator",
            },
            log_group=part2_log_group,
        )

        # ── S3 Event Notification → Part 2 Lambda ────────────────────
        report_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(part2_lambda),
            s3.NotificationKeyFilter(prefix="reports/", suffix=".json"),
        )

        # ── Tags ─────────────────────────────────────────────────────
        Tags.of(self).add("Project", "FinOps")
        Tags.of(self).add("Component", "ComputeOptimizer")
        Tags.of(self).add("ManagedBy", "CDK")

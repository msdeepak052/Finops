# FinOps EC2 Cost Optimization Report

Automated AWS solution that analyzes EC2 instances using **AWS Compute Optimizer**, filters out **EKS/Kubernetes workloads**, and generates detailed cost + performance reports in CSV and JSON.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         AWS Account                              │
│                                                                  │
│  ┌─────────────┐    ┌──────────────────────────────────────┐    │
│  │ EventBridge  │───▶│         Lambda Function              │    │
│  │ (Daily Rule) │    │   finops-compute-optimizer-report    │    │
│  └─────────────┘    │                                      │    │
│                      │  ┌────────────────────────────────┐  │    │
│                      │  │ Step 1: Compute Optimizer API  │  │    │
│                      │  │   → Fetch EC2 recommendations  │  │    │
│                      │  └──────────────┬─────────────────┘  │    │
│                      │                 ▼                     │    │
│                      │  ┌────────────────────────────────┐  │    │
│                      │  │ Step 2: EC2 DescribeInstances  │  │    │
│                      │  │   → Fetch tags + instance names│  │    │
│                      │  └──────────────┬─────────────────┘  │    │
│                      │                 ▼                     │    │
│                      │  ┌────────────────────────────────┐  │    │
│                      │  │ Step 3: EKS Filter             │  │    │
│                      │  │   → Exclude k8s-tagged nodes   │  │    │
│                      │  └──────────────┬─────────────────┘  │    │
│                      │                 ▼                     │    │
│                      │  ┌────────────────────────────────┐  │    │
│                      │  │ Step 4: Pricing API            │  │    │
│                      │  │   → On-Demand prices + savings │  │    │
│                      │  └──────────────┬─────────────────┘  │    │
│                      │                 ▼                     │    │
│                      │  ┌────────────────────────────────┐  │    │
│                      │  │ Step 5: Report Builder         │  │    │
│                      │  │   → CSV + JSON generation      │  │    │
│                      │  └──────────────┬─────────────────┘  │    │
│                      └─────────────────┼────────────────────┘    │
│                                        ▼                         │
│                      ┌──────────────────────────────────────┐    │
│                      │           S3 Bucket                   │    │
│                      │  reports/2025-01-15_12-00-00/          │    │
│                      │    ├── ec2_optimization_report.csv     │    │
│                      │    └── ec2_optimization_report.json    │    │
│                      └──────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Services Involved

| Service | Purpose |
|---------|---------|
| **AWS Compute Optimizer** | Source of EC2 right-sizing recommendations |
| **Amazon EC2** | Tag retrieval for instance identification and EKS filtering |
| **AWS Pricing API** | On-Demand pricing for current and recommended instance types |
| **AWS Lambda** | Serverless compute to run the analysis pipeline |
| **Amazon S3** | Encrypted storage for generated reports |
| **Amazon EventBridge** | Daily scheduled trigger |
| **AWS CloudWatch Logs** | Lambda execution logs |
| **AWS IAM** | Least-privilege access control |

### Data Flow

1. **EventBridge** triggers Lambda on a daily schedule (configurable)
2. Lambda calls **Compute Optimizer** `GetEC2InstanceRecommendations` with pagination
3. For each recommended instance, Lambda calls **EC2** `DescribeInstances` to fetch tags
4. **EKS Filter** removes instances tagged with `kubernetes.io/cluster/*` or `eks:cluster-name`
5. **Pricing API** enriches remaining instances with On-Demand hourly/monthly costs
6. **Report Builder** generates CSV + JSON and uploads to **S3** (SSE encrypted)

---

## IAM Permissions (Least Privilege)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ComputeOptimizerReadOnly",
      "Effect": "Allow",
      "Action": [
        "compute-optimizer:GetEC2InstanceRecommendations",
        "compute-optimizer:GetEnrollmentStatus",
        "compute-optimizer:GetRecommendationSummaries"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2DescribeOnly",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PricingReadOnly",
      "Effect": "Allow",
      "Action": [
        "pricing:GetProducts",
        "pricing:DescribeServices"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3ReportWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::REPORT_BUCKET/*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/finops-compute-optimizer:*"
    }
  ]
}
```

---

## Project Structure

```
myFinopsProject/
├── cdk.json                          # CDK configuration
├── requirements.txt                  # CDK + dev dependencies
├── infrastructure/
│   ├── __init__.py
│   ├── app.py                        # CDK app entry point
│   └── stack.py                      # CDK stack (Lambda, S3, EventBridge, IAM)
├── lambda/
│   ├── __init__.py
│   ├── handler.py                    # Lambda entry point (orchestrator)
│   ├── requirements.txt              # Lambda runtime dependencies
│   ├── compute_optimizer/
│   │   ├── __init__.py
│   │   ├── optimizer_client.py       # Compute Optimizer API client
│   │   ├── ec2_tags.py               # EC2 tag fetcher
│   │   ├── eks_filter.py             # EKS/Kubernetes exclusion filter
│   │   ├── cost_calculator.py        # Pricing API + cost calculations
│   │   └── report_builder.py         # CSV/JSON report generator + S3 upload
│   └── tests/
│       ├── __init__.py
│       ├── test_eks_filter.py
│       └── test_report_builder.py
├── scripts/
│   ├── deploy.sh                     # Linux/macOS deployment
│   └── deploy.ps1                    # Windows PowerShell deployment
└── README.md
```

---

## Deployment — End-to-End Steps

### Prerequisites

- Python 3.12+
- AWS CLI configured (`aws configure`)
- AWS CDK CLI (`npm install -g aws-cdk`)
- AWS Compute Optimizer **already enabled** in the target account

### Step 1: Clone and Set Up

```bash
cd myFinopsProject

# Create virtual environment
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate
# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Bootstrap CDK (One-Time)

```bash
# Get your account ID and region
aws sts get-caller-identity --query Account --output text
aws configure get region

# Bootstrap CDK
cdk bootstrap aws://ACCOUNT_ID/REGION
```

### Step 3: Synthesize (Preview)

```bash
# Generate CloudFormation template without deploying
cdk synth
```

Review the template in `cdk.out/FinOpsComputeOptimizerStack.template.json`.

### Step 4: Deploy

```bash
# Deploy the stack
cdk deploy

# Or with multi-account support
cdk deploy --context account_ids="111111111111,222222222222"

# Or use the automated script (does all of the above)
./scripts/deploy.sh                              # Linux/macOS
.\scripts\deploy.ps1                             # Windows
```

### Step 5: Verify

```bash
# Check the stack
aws cloudformation describe-stacks \
  --stack-name FinOpsComputeOptimizerStack \
  --query "Stacks[0].StackStatus"

# Manually invoke to test
aws lambda invoke \
  --function-name finops-compute-optimizer-report \
  --payload '{}' \
  response.json

cat response.json
```

### Step 6: View Reports

```bash
# List generated reports
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name FinOpsComputeOptimizerStack \
  --query "Stacks[0].Outputs[?OutputKey=='ReportBucket'].OutputValue" \
  --output text)

aws s3 ls s3://$BUCKET/reports/ --recursive

# Download latest report
aws s3 cp s3://$BUCKET/reports/LATEST_FOLDER/ec2_optimization_report.csv .
```

---

## Report Columns

| Column | Description |
|--------|-------------|
| Account ID | AWS account the instance belongs to |
| Instance ID | EC2 instance ID (i-xxx) |
| Instance Name | Value of the `Name` tag |
| Finding | OVER_PROVISIONED, UNDER_PROVISIONED, or OPTIMIZED |
| Finding Reasons | All finding reason codes |
| CPU Finding Reasons | CPU-specific reasons |
| Memory Finding Reasons | Memory-specific reasons |
| Recommendation Instance State | State of the recommended action |
| Current Instance Type | Currently running instance type |
| Recommended Instance Type | Compute Optimizer's recommended type |
| Current Performance Risk | Risk level for current configuration |
| Current Hourly Price (USD) | On-Demand hourly rate for current type |
| Recommended Hourly Price (USD) | On-Demand hourly rate for recommended type |
| Current Monthly On-Demand Price | Monthly cost at On-Demand rates |
| Recommended Monthly On-Demand Price | Monthly cost for recommended type |
| Monthly Price Difference | Savings = current - recommended |
| Est. Monthly Savings On-Demand | Compute Optimizer's estimated savings |
| Est. Monthly Savings After Discounts | Savings accounting for RIs/Savings Plans |
| Savings Opportunity (%) | Percentage savings available |
| Migration Effort | Estimated effort to migrate (VeryLow/Low/Medium/High) |

---

## EKS Exclusion Tags

Instances with **any** of these tags are excluded from the report:

| Tag Key | Example |
|---------|---------|
| `eks:cluster-name` | `eks:cluster-name = my-cluster` |
| `eks:nodegroup-name` | `eks:nodegroup-name = ng-1` |
| `aws:eks:cluster-name` | `aws:eks:cluster-name = prod` |
| `kubernetes.io/cluster/<name>` | `kubernetes.io/cluster/my-cluster = owned` |
| `k8s.io/cluster/<name>` | `k8s.io/cluster/dev = shared` |

---

## Configuration

Edit `cdk.json` context values or pass via CLI:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `schedule_expression` | `rate(24 hours)` | EventBridge schedule |
| `report_retention_days` | `90` | S3 lifecycle expiration |
| `account_ids` | `""` | Comma-separated account IDs for multi-account |

```bash
# Custom schedule (weekly)
cdk deploy --context schedule_expression="rate(7 days)"

# Custom retention
cdk deploy --context report_retention_days=180
```

---

## Assumptions

1. **Compute Optimizer is enabled** in the target AWS account(s)
2. Instances have been running long enough for Compute Optimizer to generate recommendations (typically 14+ days)
3. The Pricing API is used for On-Demand rates — actual costs may differ if RIs or Savings Plans are active
4. Lambda timeout of 10 minutes is sufficient for the instance count; for 10,000+ instances, consider Step Functions
5. The solution runs in a single region per deployment; deploy multiple stacks for multi-region

---

## Teardown

```bash
cdk destroy
# or
./scripts/deploy.sh --destroy
```

The S3 bucket uses `RETAIN` removal policy — delete manually if needed:
```bash
aws s3 rb s3://BUCKET_NAME --force
```

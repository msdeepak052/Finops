# FinOps EC2 Cost Optimization Report

Automated AWS solution that analyzes EC2 instances using **AWS Compute Optimizer**, filters out **EKS/Kubernetes workloads**, generates detailed cost reports, and validates recommendations against an organization's **approved instance type allow-list** using **Amazon Bedrock AI**.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                            AWS Account                                │
│                                                                       │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐      │
│  │ EventBridge  │───▶│   Part 1 Lambda                        │      │
│  │ (Daily Rule) │    │   finops-compute-optimizer-report       │      │
│  └─────────────┘    │                                         │      │
│                      │  Step 1: Compute Optimizer API          │      │
│                      │  Step 2: EC2 DescribeInstances (tags)   │      │
│                      │  Step 3: EKS Filter                     │      │
│                      │  Step 4: Pricing API                    │      │
│                      │  Step 5: Report Builder (CSV + JSON)    │      │
│                      └──────────────┬──────────────────────────┘      │
│                                     ▼                                  │
│                      ┌──────────────────────────────────────────┐     │
│                      │              S3 Bucket                    │     │
│                      │  reports/{timestamp}/                     │     │
│                      │    ├── ec2_optimization_report.csv        │     │
│                      │    ├── ec2_optimization_report.json ──────┼──┐  │
│                      │    └── validated/                         │  │  │
│                      │          ├── ec2_validated_report.csv     │  │  │
│                      │          └── ec2_validated_report.json    │  │  │
│                      └──────────────────────────────────────────┘  │  │
│                                                                    │  │
│                      ┌─────────────────────────────────────────┐   │  │
│                      │   Part 2 Lambda                         │◀──┘  │
│                      │   finops-bedrock-validator               │     │
│                      │   (S3 event trigger on .json upload)     │     │
│                      │                                         │      │
│                      │  Step 1: Read Part 1 JSON report        │      │
│                      │  Step 2: Load allow-list + init Bedrock │      │
│                      │  Step 3: Validate recommendations       │      │
│                      │    ├── In allow-list? → Auto-approve    │      │
│                      │    └── Not in list?  → Bedrock AI pick  │      │
│                      │  Step 4: Generate enriched reports      │      │
│                      └─────────────────────────────────────────┘      │
│                                     │                                  │
│                      ┌──────────────▼───────────────────────────┐     │
│                      │         Amazon Bedrock                    │     │
│                      │  Claude / Nova (Converse API)             │     │
│                      └──────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
EventBridge (daily) → Part 1 Lambda → S3 (JSON + CSV)
                                         │
                                    S3 Event (.json suffix)
                                         │
                                         ▼
                                    Part 2 Lambda
                                         │
                              ┌──────────┴──────────┐
                              │                     │
                         In allow-list?         NOT in allow-list?
                              │                     │
                     Approve as-is           Bedrock AI selects
                     + discount tier         alternatives from
                                             allow-list (ranked)
                              │                     │
                              └──────────┬──────────┘
                                         │
                                   Enriched output
                                   (CSV + JSON → S3)
```

### Services Involved

| Service | Purpose |
|---------|---------|
| **AWS Compute Optimizer** | Source of EC2 right-sizing recommendations |
| **Amazon EC2** | Tag retrieval for instance identification and EKS filtering |
| **AWS Pricing API** | On-Demand pricing for current and recommended instance types |
| **Amazon Bedrock** | AI-based validation and alternative selection (Claude / Nova) |
| **AWS Lambda** | Serverless compute (Part 1 + Part 2) |
| **Amazon S3** | Encrypted storage for reports + event trigger |
| **Amazon EventBridge** | Daily scheduled trigger for Part 1 |
| **AWS CloudWatch Logs** | Lambda execution logs (both parts) |
| **AWS IAM** | Least-privilege access control |

---

## Project Structure

```
myFinopsProject/
├── cdk.json                          # CDK configuration (includes Bedrock defaults)
├── requirements.txt                  # CDK + dev dependencies
├── infrastructure/
│   ├── __init__.py
│   ├── app.py                        # CDK app entry point
│   └── stack.py                      # CDK stack (both Lambdas, S3, EventBridge, IAM)
├── part1/                            # Part 1: Compute Optimizer pipeline
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
│       ├── conftest.py
│       ├── test_eks_filter.py
│       └── test_report_builder.py
├── part2/                            # Part 2: Bedrock AI validation
│   ├── __init__.py
│   ├── handler.py                    # Lambda entry point (S3 event trigger)
│   ├── allowlist.yaml                # Approved instance types (Tier 1/2 discounts)
│   ├── requirements.txt              # Lambda runtime dependencies
│   ├── bedrock_validator/
│   │   ├── __init__.py
│   │   ├── s3_reader.py              # Parse S3 event + read Part 1 JSON
│   │   ├── allowlist_checker.py      # Load YAML, check/query allow-list
│   │   ├── bedrock_client.py         # Bedrock Converse API (Claude + Nova)
│   │   ├── prompt_builder.py         # Structured prompt engineering
│   │   ├── recommendation_enricher.py # Orchestrate validation pipeline
│   │   └── report_builder.py         # Enriched CSV/JSON + S3 upload
│   └── tests/
│       ├── conftest.py
│       ├── test_allowlist_checker.py
│       ├── test_bedrock_client.py
│       ├── test_prompt_builder.py
│       ├── test_recommendation_enricher.py
│       ├── test_report_builder.py
│       └── test_handler.py
├── scripts/
│   ├── deploy.sh                     # Linux/macOS deployment
│   └── deploy.ps1                    # Windows PowerShell deployment
└── README.md
```

---

## Part 1: Compute Optimizer Pipeline

1. **EventBridge** triggers Lambda on a daily schedule
2. Lambda calls **Compute Optimizer** `GetEC2InstanceRecommendations` with pagination
3. For each instance, fetches **EC2 tags** for identification
4. **EKS Filter** removes instances tagged with Kubernetes markers
5. **Pricing API** enriches with On-Demand hourly/monthly costs
6. **Report Builder** generates CSV + JSON and uploads to **S3** (SSE encrypted)

---

## Part 2: Bedrock AI Validation

1. **S3 event notification** triggers Part 2 Lambda when Part 1 uploads a `.json` report
2. Lambda reads the Part 1 JSON report from S3
3. For each recommendation:
   - If the recommended type is in the **allow-list** → auto-approve with discount tier
   - If NOT in the allow-list → query **Amazon Bedrock** (Claude or Nova) for alternatives
   - If Bedrock fails → graceful degradation, continue with the batch
4. Generates **enriched CSV + JSON** reports uploaded to `validated/` subfolder

### Allow-List

The allow-list (`part2/allowlist.yaml`) defines approved instance types in two tiers:

| Tier | Discount | Families |
|------|----------|----------|
| **Tier 1** (Enterprise Reserved) | 50% | m5, m6i, m6g, c5, c6i, c6g, r5, r6i |
| **Tier 2** (Standard Reserved) | 35% | m7i, m7g, c7i, r7i, r6g, i3, t3, t3a |

### Bedrock AI Selection Criteria

When a recommended type is not in the allow-list, Bedrock selects alternatives based on:
1. **Price** — closest to or lower than the recommended type
2. **vCPU count** — meets or exceeds the recommendation
3. **Memory** — meets or exceeds the recommendation
4. **20% headroom rule** — prefers types with ~20% more capacity
5. **Higher discount tiers preferred** — Tier 1 over Tier 2 when specs are comparable

---

## IAM Permissions (Least Privilege)

### Part 1 Lambda Role
- `compute-optimizer:GetEC2InstanceRecommendations`, `GetEnrollmentStatus`, `GetRecommendationSummaries`
- `ec2:DescribeInstances`, `ec2:DescribeTags`
- `pricing:GetProducts`, `pricing:DescribeServices`
- `s3:PutObject` (report bucket only)
- `logs:CreateLogStream`, `logs:PutLogEvents`

### Part 2 Lambda Role
- `s3:GetObject`, `s3:PutObject` (report bucket only)
- `bedrock:InvokeModel`, `bedrock:Converse`
- `logs:CreateLogStream`, `logs:PutLogEvents`

---

## Prerequisites

### Tools Required

| Tool | Purpose | Install |
|------|---------|---------|
| **Python 3.12+** | Runtime for Lambdas and CDK | [python.org](https://www.python.org/downloads/) |
| **AWS CLI** | AWS credentials and configuration | `pip install awscli` or [AWS docs](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| **AWS CDK CLI** | Infrastructure deployment | `npm install -g aws-cdk` |
| **Node.js** | Required by CDK CLI | [nodejs.org](https://nodejs.org/) |

### AWS Services That Must Be Enabled

| Service | Action Required |
|---------|-----------------|
| **AWS Compute Optimizer** | Must be **opted in** in the target account via the AWS Console. Recommendations take ~14 days to generate after opt-in. |
| **Amazon Bedrock** | Must **enable model access** for your chosen model (Claude or Nova) in the target region via the Bedrock console under *Model access*. |

### Lambda Environment Variables

**All environment variables are set automatically by CDK** — you do NOT need to set them manually. CDK wires them from the stack resources.

#### Part 1 Lambda (`finops-compute-optimizer-report`)

| Variable | Required | Default | Set By |
|----------|----------|---------|--------|
| `REPORT_BUCKET` | **Yes** | — | CDK (auto from S3 bucket) |
| `REPORT_PREFIX` | No | `reports` | CDK |
| `ACCOUNT_IDS` | No | `""` (current account only) | CDK (from context) |
| `AWS_REGION` | No | Lambda runtime default | AWS Lambda |

#### Part 2 Lambda (`finops-bedrock-validator`)

| Variable | Required | Default | Set By |
|----------|----------|---------|--------|
| `REPORT_BUCKET` | No | Falls back to S3 event bucket | CDK (auto from S3 bucket) |
| `REPORT_PREFIX` | No | `reports` | CDK |
| `BEDROCK_MODEL_ID` | No | `claude` | CDK (from context) |
| `BEDROCK_REGION` | No | `us-east-1` | CDK (from context) |

### CDK Context Parameters

These are the only values you might want to customize at deploy time:

| Parameter | Default | How to Set |
|-----------|---------|------------|
| `schedule_expression` | `rate(24 hours)` | `cdk.json` or `--context schedule_expression="rate(7 days)"` |
| `report_retention_days` | `90` | `cdk.json` or `--context report_retention_days=180` |
| `account_ids` | `""` | `--context account_ids="111111111111,222222222222"` |
| `bedrock_model_id` | `claude` | `--context bedrock_model_id="nova"` |
| `bedrock_region` | `us-east-1` | `--context bedrock_region="us-west-2"` |

---

## Deployment

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
aws sts get-caller-identity --query Account --output text
aws configure get region

cdk bootstrap aws://ACCOUNT_ID/REGION
```

### Step 3: Deploy

```bash
# Deploy with defaults (Claude model, us-east-1)
cdk deploy

# Or with custom Bedrock model
cdk deploy --context bedrock_model_id="nova" --context bedrock_region="us-west-2"

# Or with multi-account support
cdk deploy --context account_ids="111111111111,222222222222"

# Or use the automated scripts
./scripts/deploy.sh                              # Linux/macOS
.\scripts\deploy.ps1                             # Windows
```

### Step 4: Verify

```bash
# Manually invoke Part 1
aws lambda invoke \
  --function-name finops-compute-optimizer-report \
  --payload '{}' \
  response.json

cat response.json

# Part 2 triggers automatically when Part 1 uploads JSON to S3
```

---

## Configuration

Edit `cdk.json` context values or pass via CLI:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `schedule_expression` | `rate(24 hours)` | EventBridge schedule |
| `report_retention_days` | `90` | S3 lifecycle expiration |
| `account_ids` | `""` | Comma-separated account IDs |
| `bedrock_model_id` | `"claude"` | Bedrock model (`claude`, `nova`, or full ID) |
| `bedrock_region` | `"us-east-1"` | AWS region for Bedrock endpoint |

---

## Report Columns

### Part 1 Report (ec2_optimization_report.csv)

| Column | Description |
|--------|-------------|
| Account ID | AWS account |
| Instance ID | EC2 instance ID |
| Instance Name | `Name` tag value |
| Finding | OVER_PROVISIONED, UNDER_PROVISIONED, or OPTIMIZED |
| Current/Recommended Instance Type | Instance types |
| Current/Recommended Monthly Price | On-Demand monthly costs |
| Est. Monthly Savings | On-Demand and after-discount savings |

### Part 2 Report (ec2_validated_report.csv)

| Column | Description |
|--------|-------------|
| Validation Status | Approved (Allowed Instance) / AI-Recommended Alternative / AI Validation Failed |
| Final Recommendation | The validated instance type |
| Discount Tier | Tier 1 or Tier 2 name |
| Discount (%) | 50% or 35% |
| Discounted Monthly Price | Price after applying tier discount |
| Est. Savings With Discount | Savings vs current price after discount |
| AI Confidence | high / medium / low |
| AI Analysis | Summary of the AI's reasoning |
| AI Alternatives | Ranked list of alternatives |
| Bedrock Model | Model ID used for validation |

---

## EKS Exclusion Tags

Instances with **any** of these tags are excluded from Part 1 reports:

| Tag Key | Example |
|---------|---------|
| `eks:cluster-name` | `eks:cluster-name = my-cluster` |
| `eks:nodegroup-name` | `eks:nodegroup-name = ng-1` |
| `aws:eks:cluster-name` | `aws:eks:cluster-name = prod` |
| `kubernetes.io/cluster/<name>` | `kubernetes.io/cluster/my-cluster = owned` |
| `k8s.io/cluster/<name>` | `k8s.io/cluster/dev = shared` |

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

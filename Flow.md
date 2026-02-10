<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 200px 0 20px 0;">

<div style="font-size: 24px; margin-bottom: 12px;"><strong>Amazon Q</strong></div>
<div style="background: rgba(128, 128, 128, 0.15); border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 8px; padding: 8px; margin: 4px 0; text-align: center;">
<div style="font-size: 14px; margin-bottom: 4px;"><strong>Did you know?</strong></div>
<div>Pinned context is always included in future chat messages</div>
</div>

Select code & ask me to explain, debug or optimize it, or type `/` for quick actions

</div>

---

Understand the above repo and let me know the code flow how it executes and what are the python files executed in the order with explanation

---

I'll analyze the repository structure and explain the complete code execution flow.

---


## Code Execution Flow - FinOps EC2 Cost Optimization Report

Based on the repository analysis, here's the complete execution flow:

---

## **Deployment Phase** (One-time setup)

### 1. **infrastructure/app.py** (CDK Entry Point)
- **Purpose**: Initializes the CDK application
- **Execution**: Run via `cdk deploy` command
- **What it does**:
  - Reads configuration from `cdk.json` or CLI context (schedule, retention, account IDs)
  - Instantiates the CloudFormation stack
  - Calls `app.synth()` to generate CloudFormation template

### 2. **infrastructure/stack.py** (Infrastructure Definition)
- **Purpose**: Defines all AWS resources
- **Creates**:
  - S3 bucket (encrypted, versioned, lifecycle rules)
  - Lambda function (Python 3.12, 10-min timeout, 512MB memory)
  - IAM role with least-privilege permissions
  - EventBridge rule (daily trigger)
  - CloudWatch log group
- **Packages**: Bundles `lambda/` directory as Lambda deployment package

---

## **Runtime Phase** (Daily execution)

### 3. **EventBridge Trigger**
- Fires daily (or custom schedule: `rate(24 hours)`)
- Invokes Lambda function with empty event payload

### 4. **lambda/handler.py** (Orchestrator - Entry Point)
**Execution Order**:

```
handler() function
  ↓
  Step 1: ComputeOptimizerClient.get_ec2_recommendations()
  ↓
  Step 2: EC2TagFetcher.enrich_recommendations()
  ↓
  Step 3: EKSFilter.filter_recommendations()
  ↓
  Step 4: CostCalculator.enrich_recommendations()
  ↓
  Step 5: ReportBuilder.build_csv() + build_json() + upload_to_s3()
```

**Environment Variables Used**:
- `REPORT_BUCKET` - S3 bucket name
- `REPORT_PREFIX` - S3 folder prefix (default: "reports")
- `AWS_REGION` - Target region for pricing
- `ACCOUNT_IDS` - Comma-separated account IDs (optional)

---

## **Detailed Step-by-Step Execution**

### **Step 1: Fetch Recommendations**
**File**: `lambda/compute_optimizer/optimizer_client.py`

**Class**: `ComputeOptimizerClient`

**Method**: `get_ec2_recommendations()`

**What it does**:
- Calls AWS Compute Optimizer API: `GetEC2InstanceRecommendations`
- Handles pagination (1000 results per page)
- Supports multi-account queries if `account_ids` provided
- Extracts structured data:
  - Instance ID, ARN, account ID
  - Current instance type
  - Finding (OVER_PROVISIONED, UNDER_PROVISIONED, OPTIMIZED)
  - Finding reasons (CPU/Memory specific)
  - Recommended instance type
  - Performance risk scores
  - Savings opportunity percentage
  - Estimated monthly savings (On-Demand and after discounts)
  - Migration effort

**Returns**: List of dictionaries (one per instance)

---

### **Step 2: Enrich with EC2 Tags**
**File**: `lambda/compute_optimizer/ec2_tags.py`

**Class**: `EC2TagFetcher`

**Method**: `enrich_recommendations()`

**What it does**:
- Extracts all instance IDs from recommendations
- Calls EC2 API: `DescribeInstances` in batches (200 instances per call)
- Handles pagination for large result sets
- Gracefully handles terminated instances (InvalidInstanceID.NotFound)
- Extracts:
  - All tags as key-value dict
  - Instance name from `Name` tag
- Updates each recommendation record in-place with `tags` and `instance_name`

**Returns**: Same list with enriched data

---

### **Step 3: Filter EKS/Kubernetes Instances**
**File**: `lambda/compute_optimizer/eks_filter.py`

**Class**: `EKSFilter`

**Method**: `filter_recommendations()`

**What it does**:
- Checks each instance's tags for EKS/Kubernetes markers:
  - **Exact matches**: `eks:cluster-name`, `eks:nodegroup-name`, `aws:eks:cluster-name`
  - **Prefix matches**: `kubernetes.io/cluster/*`, `k8s.io/cluster/*`
- Splits recommendations into two lists:
  - **non_eks**: Instances to include in report
  - **eks**: Instances to exclude (logged but not reported)

**Returns**: Tuple of (non_eks_list, eks_list)

---

### **Step 4: Enrich with Pricing Data**
**File**: `lambda/compute_optimizer/cost_calculator.py`

**Class**: `CostCalculator`

**Method**: `enrich_recommendations()`

**What it does**:
- Collects unique instance types (current + recommended)
- Calls AWS Pricing API: `GetProducts` (us-east-1 endpoint)
- Filters for:
  - Linux OS
  - Shared tenancy
  - On-Demand pricing
  - Target region
- Caches prices to avoid duplicate API calls
- Calculates for each recommendation:
  - `current_instance_price` (hourly)
  - `recommended_instance_price` (hourly)
  - `current_on_demand_price` (monthly = hourly × 730)
  - `recommended_on_demand_price` (monthly)
  - `price_difference` (monthly savings)

**Returns**: Same list with pricing data added

---

### **Step 5: Generate and Upload Reports**
**File**: `lambda/compute_optimizer/report_builder.py`

**Class**: `ReportBuilder`

**Methods**: `build_csv()`, `build_json()`, `upload_to_s3()`

**What it does**:

#### **build_csv()**:
- Creates CSV with 24 columns (see REPORT_COLUMNS)
- Converts lists to semicolon-separated strings
- Returns CSV string

#### **build_json()**:
- Creates structured JSON with:
  - `report_metadata`: timestamp, totals, finding summary
  - `recommendations`: array of all instances
- Returns formatted JSON string

#### **upload_to_s3()**:
- Generates timestamped S3 keys: `reports/2025-01-15_12-00-00/ec2_optimization_report.{csv,json}`
- Uploads both files with:
  - Server-side encryption (aws:kms)
  - Appropriate content types
- Returns S3 keys

---

## **Final Output**

**Lambda returns**:
```json
{
  "statusCode": 200,
  "body": "Report generated successfully",
  "total_instances_analyzed": 150,
  "eks_excluded": 45,
  "non_eks_included": 105,
  "total_estimated_monthly_savings_on_demand_usd": 12450.75,
  "total_estimated_monthly_savings_after_discounts_usd": 8920.50,
  "s3_csv": "s3://bucket/reports/2025-01-15_12-00-00/ec2_optimization_report.csv",
  "s3_json": "s3://bucket/reports/2025-01-15_12-00-00/ec2_optimization_report.json"
}
```

---

## **Python Files Execution Order Summary**

| Order | File | Purpose | Key Methods |
|-------|------|---------|-------------|
| 1 | `infrastructure/app.py` | CDK initialization | `main()` |
| 2 | `infrastructure/stack.py` | Resource provisioning | `__init__()` |
| 3 | `lambda/handler.py` | Orchestration | `handler()` |
| 4 | `compute_optimizer/optimizer_client.py` | Fetch recommendations | `get_ec2_recommendations()` |
| 5 | `compute_optimizer/ec2_tags.py` | Fetch tags | `enrich_recommendations()` |
| 6 | `compute_optimizer/eks_filter.py` | Filter EKS | `filter_recommendations()` |
| 7 | `compute_optimizer/cost_calculator.py` | Pricing data | `enrich_recommendations()` |
| 8 | `compute_optimizer/report_builder.py` | Generate reports | `build_csv()`, `build_json()`, `upload_to_s3()` |
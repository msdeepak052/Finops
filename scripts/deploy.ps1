# ================================================================
# FinOps Compute Optimizer — Deployment Script (Windows PowerShell)
# ================================================================
# Deploys both Part 1 (Compute Optimizer pipeline) and
# Part 2 (Bedrock AI validation) as a single CDK stack.
#
# Usage:
#   .\scripts\deploy.ps1                              # Deploy with defaults
#   .\scripts\deploy.ps1 -AccountIds "111,222"        # Multi-account
#   .\scripts\deploy.ps1 -BedrockModel "nova"          # Use Amazon Nova
#   .\scripts\deploy.ps1 -Destroy                     # Tear down stack
# ================================================================

param(
    [string]$AccountIds = "",
    [string]$BedrockModel = "claude",
    [string]$BedrockRegion = "us-east-1",
    [switch]$Destroy = $false,
    [switch]$SynthOnly = $false
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " FinOps Compute Optimizer — Deploy" -ForegroundColor Cyan
Write-Host " Part 1: Compute Optimizer Pipeline" -ForegroundColor Cyan
Write-Host " Part 2: Bedrock AI Validation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ── Step 1: Check prerequisites ──────────────────────────────────
Write-Host "`n[1/5] Checking prerequisites..." -ForegroundColor Yellow

$commands = @("python", "cdk", "aws")
foreach ($cmd in $commands) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: '$cmd' not found. Please install it first." -ForegroundColor Red
        exit 1
    }
}

# Verify AWS credentials
try {
    aws sts get-caller-identity | Out-Null
    Write-Host "  AWS credentials: OK" -ForegroundColor Green
} catch {
    Write-Host "ERROR: AWS credentials not configured. Run 'aws configure'." -ForegroundColor Red
    exit 1
}

# ── Step 2: Set up virtual environment ───────────────────────────
Write-Host "`n[2/5] Setting up Python virtual environment..." -ForegroundColor Yellow

$VenvPath = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    python -m venv $VenvPath
    Write-Host "  Created virtual environment at $VenvPath" -ForegroundColor Green
}

$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
. $ActivateScript

pip install -q -r (Join-Path $ProjectRoot "requirements.txt")
Write-Host "  Dependencies installed" -ForegroundColor Green

# ── Step 3: CDK Bootstrap (if needed) ───────────────────────────
Write-Host "`n[3/5] Bootstrapping CDK (if needed)..." -ForegroundColor Yellow

$AccountId = (aws sts get-caller-identity --query Account --output text)
$Region = (aws configure get region 2>$null)
if (-not $Region) { $Region = "us-east-1" }

cdk bootstrap "aws://$AccountId/$Region" 2>&1 | ForEach-Object {
    if ($_ -match "already bootstrapped") {
        Write-Host "  CDK already bootstrapped" -ForegroundColor Green
    }
}

# ── Step 4: Synthesize ──────────────────────────────────────────
Write-Host "`n[4/5] Synthesizing CloudFormation template..." -ForegroundColor Yellow

$CdkArgs = @()
if ($AccountIds) {
    $CdkArgs += "--context"
    $CdkArgs += "account_ids=$AccountIds"
}
$CdkArgs += "--context"
$CdkArgs += "bedrock_model_id=$BedrockModel"
$CdkArgs += "--context"
$CdkArgs += "bedrock_region=$BedrockRegion"

Push-Location $ProjectRoot
cdk synth @CdkArgs
Pop-Location

if ($SynthOnly) {
    Write-Host "`nSynth complete. Template at cdk.out/" -ForegroundColor Green
    exit 0
}

# ── Step 5: Deploy or Destroy ───────────────────────────────────
if ($Destroy) {
    Write-Host "`n[5/5] Destroying stack..." -ForegroundColor Red
    Push-Location $ProjectRoot
    cdk destroy --force @CdkArgs
    Pop-Location
    Write-Host "`nStack destroyed." -ForegroundColor Green
} else {
    Write-Host "`n[5/5] Deploying stack..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    cdk deploy --require-approval broadening @CdkArgs
    Pop-Location
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host " Deployment complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "`nLambda functions deployed:"
    Write-Host "  Part 1: finops-compute-optimizer-report  (EventBridge daily trigger)"
    Write-Host "  Part 2: finops-bedrock-validator          (S3 event trigger)"
    Write-Host "`nTo invoke Part 1 manually:"
    Write-Host "  aws lambda invoke --function-name finops-compute-optimizer-report /dev/stdout"
}

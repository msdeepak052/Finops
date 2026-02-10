"""Tests for EnrichedReportBuilder."""

import csv
import io
import json

from bedrock_validator.report_builder import EnrichedReportBuilder


def _sample_enriched_recommendations():
    return [
        {
            "Account ID": "111111111111",
            "Instance ID": "i-0abc123",
            "Instance Name": "web-server-1",
            "Finding": "OVER_PROVISIONED",
            "Current Instance Type": "m5.2xlarge",
            "Recommended Instance Type": "m5.xlarge",
            "validation_status": "Approved (Allowed Instance)",
            "final_recommendation": "m5.xlarge",
            "discount_tier_name": "Tier 1 — Enterprise Reserved",
            "discount_percent": 50,
            "Current Monthly On-Demand Price (USD)": 280.32,
            "Recommended Monthly On-Demand Price (USD)": 140.16,
            "discounted_monthly_price": 70.08,
            "Est. Monthly Savings On-Demand (USD)": 140.16,
            "estimated_monthly_savings_with_discount": 210.24,
            "ai_confidence": "high",
            "ai_analysis_summary": "Pre-approved instance type.",
            "ai_alternatives": "",
            "bedrock_model": "",
        },
        {
            "Account ID": "111111111111",
            "Instance ID": "i-0def456",
            "Instance Name": "api-server-1",
            "Finding": "OVER_PROVISIONED",
            "Current Instance Type": "c5.4xlarge",
            "Recommended Instance Type": "c5a.2xlarge",
            "validation_status": "AI-Recommended Alternative",
            "final_recommendation": "c5.2xlarge",
            "discount_tier_name": "Tier 1 — Enterprise Reserved",
            "discount_percent": 50,
            "Current Monthly On-Demand Price (USD)": 496.40,
            "Recommended Monthly On-Demand Price (USD)": 248.20,
            "discounted_monthly_price": 124.10,
            "Est. Monthly Savings On-Demand (USD)": 248.20,
            "estimated_monthly_savings_with_discount": 372.30,
            "ai_confidence": "high",
            "ai_analysis_summary": "c5.2xlarge selected as best approved alternative.",
            "ai_alternatives": "#1: c5.2xlarge — Best match; #2: c6i.2xlarge — Newer gen",
            "bedrock_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        },
    ]


class TestBuildCSV:
    def test_csv_has_header_and_data_rows(self):
        builder = EnrichedReportBuilder()
        csv_content = builder.build_csv(_sample_enriched_recommendations())

        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        assert len(rows) == 3  # header + 2 data rows
        assert "Validation Status" in rows[0]
        assert "Final Recommendation" in rows[0]
        assert "Discount Tier" in rows[0]

    def test_csv_contains_instance_data(self):
        builder = EnrichedReportBuilder()
        csv_content = builder.build_csv(_sample_enriched_recommendations())

        assert "i-0abc123" in csv_content
        assert "i-0def456" in csv_content
        assert "Approved (Allowed Instance)" in csv_content
        assert "AI-Recommended Alternative" in csv_content

    def test_empty_recommendations(self):
        builder = EnrichedReportBuilder()
        csv_content = builder.build_csv([])
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 1  # header only


class TestBuildJSON:
    def test_json_structure(self):
        builder = EnrichedReportBuilder()
        json_content = builder.build_json(_sample_enriched_recommendations())
        data = json.loads(json_content)

        assert "report_metadata" in data
        assert "recommendations" in data
        assert data["report_metadata"]["report_type"] == "validated"
        assert data["report_metadata"]["total_instances"] == 2
        assert len(data["recommendations"]) == 2

    def test_json_validation_summary(self):
        builder = EnrichedReportBuilder()
        json_content = builder.build_json(_sample_enriched_recommendations())
        data = json.loads(json_content)

        summary = data["report_metadata"]["validation_summary"]
        assert summary["Approved (Allowed Instance)"] == 1
        assert summary["AI-Recommended Alternative"] == 1
        assert summary["AI Validation Failed"] == 0

    def test_json_savings_total(self):
        builder = EnrichedReportBuilder()
        json_content = builder.build_json(_sample_enriched_recommendations())
        data = json.loads(json_content)

        total = data["report_metadata"]["total_estimated_monthly_savings_with_discount"]
        assert total == 582.54  # 210.24 + 372.30

    def test_json_record_has_display_keys(self):
        builder = EnrichedReportBuilder()
        json_content = builder.build_json(_sample_enriched_recommendations())
        data = json.loads(json_content)

        rec = data["recommendations"][0]
        assert "Validation Status" in rec
        assert "Final Recommendation" in rec
        assert "Discount Tier" in rec
        assert "AI Confidence" in rec


class TestSaveLocal:
    def test_save_creates_files(self, tmp_path):
        builder = EnrichedReportBuilder()
        csv_content = "header\nrow1"
        json_content = '{"key": "value"}'

        result = builder.save_local(csv_content, json_content, str(tmp_path))

        assert (tmp_path / "ec2_validated_report.csv").exists()
        assert (tmp_path / "ec2_validated_report.json").exists()
        assert "csv_path" in result
        assert "json_path" in result

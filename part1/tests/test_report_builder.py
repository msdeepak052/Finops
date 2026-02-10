"""Tests for report generation (CSV and JSON)."""

import csv
import io
import json

from compute_optimizer.report_builder import ReportBuilder


def _sample_recommendations():
    return [
        {
            "account_id": "111111111111",
            "instance_id": "i-0abc123",
            "instance_name": "web-server-1",
            "finding": "OVER_PROVISIONED",
            "finding_reasons": ["CPUOverprovisioned"],
            "cpu_finding_reasons": ["CPUOverprovisioned"],
            "memory_finding_reasons": [],
            "recommendation_instance_state": "running",
            "current_instance_type": "m5.2xlarge",
            "recommended_instance_type": "m5.xlarge",
            "current_performance_risk": "VeryLow",
            "recommended_performance_risk": 1,
            "current_instance_price": 0.384,
            "recommended_instance_price": 0.192,
            "current_on_demand_price": 280.32,
            "recommended_on_demand_price": 140.16,
            "price_difference": 140.16,
            "estimated_monthly_savings_on_demand": 140.16,
            "estimated_monthly_savings_after_discounts": 95.0,
            "savings_opportunity_pct": 50.0,
            "savings_after_discounts_pct": 33.9,
            "savings_currency": "USD",
            "inferred_workload_types": ["WebServer"],
            "recommended_migration_effort": "VeryLow",
            "tags": {"Name": "web-server-1", "Environment": "production"},
        },
    ]


class TestBuildCSV:
    def test_csv_has_header_and_data_rows(self):
        builder = ReportBuilder()
        csv_content = builder.build_csv(_sample_recommendations())

        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        assert len(rows) == 2  # header + 1 data row
        assert "Instance ID" in rows[0]
        assert "i-0abc123" in rows[1]

    def test_csv_list_values_semicolon_separated(self):
        builder = ReportBuilder()
        csv_content = builder.build_csv(_sample_recommendations())

        assert "CPUOverprovisioned" in csv_content
        assert "WebServer" in csv_content

    def test_empty_recommendations(self):
        builder = ReportBuilder()
        csv_content = builder.build_csv([])
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 1  # header only


class TestBuildJSON:
    def test_json_structure(self):
        builder = ReportBuilder()
        json_content = builder.build_json(_sample_recommendations())
        data = json.loads(json_content)

        assert "report_metadata" in data
        assert "recommendations" in data
        assert data["report_metadata"]["total_instances"] == 1
        assert len(data["recommendations"]) == 1

    def test_json_finding_summary(self):
        builder = ReportBuilder()
        json_content = builder.build_json(_sample_recommendations())
        data = json.loads(json_content)

        summary = data["report_metadata"]["finding_summary"]
        assert summary["OVER_PROVISIONED"] == 1

    def test_json_savings_total(self):
        builder = ReportBuilder()
        json_content = builder.build_json(_sample_recommendations())
        data = json.loads(json_content)

        assert data["report_metadata"]["total_estimated_monthly_savings_on_demand"] == 140.16

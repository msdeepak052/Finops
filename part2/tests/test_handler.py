"""Tests for Part 2 Lambda handler."""

import json
from unittest.mock import MagicMock, patch

import pytest

from handler import handler, _extract_timestamp


def _make_s3_event(key="reports/2025-01-15_12-00-00/ec2_optimization_report.json"):
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "my-bucket"},
                    "object": {"key": key},
                }
            }
        ]
    }


class TestGuardClauses:
    def test_skip_non_json_file(self):
        event = _make_s3_event(key="reports/2025-01-15/report.csv")
        result = handler(event, None)
        assert result["statusCode"] == 200
        assert "Skipped non-JSON" in result["body"]

    def test_skip_validated_report(self):
        event = _make_s3_event(key="reports/2025-01-15/validated/ec2_validated_report.json")
        result = handler(event, None)
        assert result["statusCode"] == 200
        assert "Skipped validated" in result["body"]

    def test_invalid_event_returns_400(self):
        result = handler({"Records": []}, None)
        assert result["statusCode"] == 400


class TestExtractTimestamp:
    def test_extracts_timestamp(self):
        ts = _extract_timestamp("reports/2025-01-15_12-00-00/ec2_optimization_report.json")
        assert ts == "2025-01-15_12-00-00"

    def test_no_timestamp_returns_empty(self):
        ts = _extract_timestamp("some/random/path.json")
        assert ts == ""


class TestHandlerPipeline:
    @patch("handler.EnrichedReportBuilder")
    @patch("handler.RecommendationEnricher")
    @patch("handler.BedrockClient")
    @patch("handler.AllowListChecker")
    @patch("handler.S3ReportReader")
    def test_full_pipeline(
        self, mock_reader_cls, mock_checker_cls, mock_bedrock_cls,
        mock_enricher_cls, mock_builder_cls,
    ):
        # Setup mocks
        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.parse_s3_event.return_value = {
            "bucket": "my-bucket",
            "key": "reports/2025-01-15_12-00-00/ec2_optimization_report.json",
        }
        mock_reader.read_report.return_value = [
            {
                "Instance ID": "i-001",
                "validation_status": "Approved (Allowed Instance)",
                "estimated_monthly_savings_with_discount": 100.0,
            }
        ]

        mock_checker = MagicMock()
        mock_checker_cls.return_value.load.return_value = mock_checker

        mock_enricher = MagicMock()
        mock_enricher_cls.return_value = mock_enricher
        mock_enricher.enrich_all.return_value = [
            {
                "Instance ID": "i-001",
                "validation_status": "Approved (Allowed Instance)",
                "estimated_monthly_savings_with_discount": 100.0,
            }
        ]

        mock_builder = MagicMock()
        mock_builder_cls.return_value = mock_builder
        mock_builder.build_csv.return_value = "csv data"
        mock_builder.build_json.return_value = '{"data": "json"}'
        mock_builder.upload_to_s3.return_value = {
            "csv_key": "reports/2025-01-15_12-00-00/validated/ec2_validated_report.csv",
            "json_key": "reports/2025-01-15_12-00-00/validated/ec2_validated_report.json",
        }
        mock_builder.save_local.return_value = {}

        event = _make_s3_event()
        result = handler(event, None)

        assert result["statusCode"] == 200
        assert result["total_instances_validated"] == 1
        assert result["approved_in_allowlist"] == 1
        mock_reader.read_report.assert_called_once()
        mock_enricher.enrich_all.assert_called_once()
        mock_builder.upload_to_s3.assert_called_once()

    @patch("handler.S3ReportReader")
    def test_empty_report_exits_early(self, mock_reader_cls):
        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.parse_s3_event.return_value = {
            "bucket": "my-bucket",
            "key": "reports/2025-01-15_12-00-00/ec2_optimization_report.json",
        }
        mock_reader.read_report.return_value = []

        result = handler(_make_s3_event(), None)
        assert result["statusCode"] == 200
        assert result["total_instances"] == 0

"""Tests for S3ReportReader."""

import json
from unittest.mock import MagicMock, patch

import pytest

from bedrock_validator.s3_reader import S3ReportReader


def _make_s3_event(bucket: str = "my-bucket", key: str = "reports/2025-01-15/report.json"):
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


class TestParseS3Event:
    def test_parses_valid_event(self):
        reader = S3ReportReader()
        result = reader.parse_s3_event(_make_s3_event())
        assert result["bucket"] == "my-bucket"
        assert result["key"] == "reports/2025-01-15/report.json"

    def test_url_decodes_key(self):
        reader = S3ReportReader()
        event = _make_s3_event(key="reports/2025-01-15_12%3A00%3A00/report.json")
        result = reader.parse_s3_event(event)
        assert result["key"] == "reports/2025-01-15_12:00:00/report.json"

    def test_no_records_raises(self):
        reader = S3ReportReader()
        with pytest.raises(ValueError, match="No Records"):
            reader.parse_s3_event({"Records": []})

    def test_missing_bucket_raises(self):
        reader = S3ReportReader()
        event = {"Records": [{"s3": {"bucket": {}, "object": {"key": "k"}}}]}
        with pytest.raises(ValueError, match="Missing bucket"):
            reader.parse_s3_event(event)


class TestReadReport:
    def test_reads_and_parses_json(self):
        report_data = {
            "report_metadata": {"generated_at": "2025-01-15", "total_instances": 1},
            "recommendations": [
                {"Instance ID": "i-001", "Current Instance Type": "m5.2xlarge"}
            ],
        }

        mock_session = MagicMock()
        mock_s3 = MagicMock()
        mock_session.client.return_value = mock_s3
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps(report_data).encode("utf-8")))
        }

        reader = S3ReportReader(session=mock_session)
        result = reader.read_report("my-bucket", "reports/report.json")

        assert len(result) == 1
        assert result[0]["Instance ID"] == "i-001"
        mock_s3.get_object.assert_called_once_with(Bucket="my-bucket", Key="reports/report.json")

    def test_empty_recommendations(self):
        report_data = {"report_metadata": {}, "recommendations": []}

        mock_session = MagicMock()
        mock_s3 = MagicMock()
        mock_session.client.return_value = mock_s3
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps(report_data).encode("utf-8")))
        }

        reader = S3ReportReader(session=mock_session)
        result = reader.read_report("my-bucket", "reports/report.json")
        assert result == []

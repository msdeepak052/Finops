"""Tests for BedrockClient."""

import json
from unittest.mock import MagicMock

import pytest

from bedrock_validator.bedrock_client import BedrockClient, MODEL_ALIASES


class TestModelAliases:
    def test_claude_alias_resolves(self):
        mock_session = MagicMock()
        client = BedrockClient(model_id="claude", session=mock_session)
        assert client.model_id == MODEL_ALIASES["claude"]

    def test_nova_alias_resolves(self):
        mock_session = MagicMock()
        client = BedrockClient(model_id="nova", session=mock_session)
        assert client.model_id == MODEL_ALIASES["nova"]

    def test_full_model_id_passthrough(self):
        mock_session = MagicMock()
        client = BedrockClient(model_id="some.custom-model:v1", session=mock_session)
        assert client.model_id == "some.custom-model:v1"


class TestInvoke:
    def _mock_converse_response(self, text: str, input_tokens: int = 100, output_tokens: int = 50):
        return {
            "output": {
                "message": {
                    "content": [{"text": text}]
                }
            },
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
            },
        }

    def test_invoke_parses_json_response(self):
        mock_session = MagicMock()
        mock_bedrock = MagicMock()
        mock_session.client.return_value = mock_bedrock

        response_json = {"alternatives": [{"instance_type": "m5.xlarge", "rank": 1}]}
        mock_bedrock.converse.return_value = self._mock_converse_response(json.dumps(response_json))

        client = BedrockClient(model_id="claude", session=mock_session)
        result = client.invoke("system prompt", "user prompt")

        assert result["alternatives"][0]["instance_type"] == "m5.xlarge"
        mock_bedrock.converse.assert_called_once()

    def test_invoke_handles_markdown_wrapped_json(self):
        mock_session = MagicMock()
        mock_bedrock = MagicMock()
        mock_session.client.return_value = mock_bedrock

        wrapped = '```json\n{"alternatives": [{"instance_type": "c5.xlarge"}]}\n```'
        mock_bedrock.converse.return_value = self._mock_converse_response(wrapped)

        client = BedrockClient(model_id="claude", session=mock_session)
        result = client.invoke("sys", "user")

        assert result["alternatives"][0]["instance_type"] == "c5.xlarge"

    def test_invoke_empty_response_raises(self):
        mock_session = MagicMock()
        mock_bedrock = MagicMock()
        mock_session.client.return_value = mock_bedrock

        mock_bedrock.converse.return_value = {
            "output": {"message": {"content": []}},
            "usage": {},
        }

        client = BedrockClient(model_id="claude", session=mock_session)
        with pytest.raises(ValueError, match="Empty response"):
            client.invoke("sys", "user")

    def test_invoke_invalid_json_raises(self):
        mock_session = MagicMock()
        mock_bedrock = MagicMock()
        mock_session.client.return_value = mock_bedrock

        mock_bedrock.converse.return_value = self._mock_converse_response("not valid json at all")

        client = BedrockClient(model_id="claude", session=mock_session)
        with pytest.raises(ValueError, match="Could not parse"):
            client.invoke("sys", "user")


class TestParseJsonResponse:
    def test_plain_json(self):
        result = BedrockClient._parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fenced_json(self):
        text = '```json\n{"key": "value"}\n```'
        result = BedrockClient._parse_json_response(text)
        assert result == {"key": "value"}

    def test_markdown_fenced_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        result = BedrockClient._parse_json_response(text)
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            BedrockClient._parse_json_response("this is not json")

"""
Bedrock Client

Wraps the Amazon Bedrock Converse API for model-agnostic inference.
Supports shorthand model aliases (e.g., "claude", "nova").
"""

import json
import logging
import re
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOTO_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "adaptive"},
)

# Shorthand model aliases → full Bedrock model IDs
MODEL_ALIASES = {
    "claude": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "nova": "amazon.nova-pro-v1:0",
}


class BedrockClient:
    """Amazon Bedrock Converse API client for AI-based validation."""

    def __init__(
        self,
        model_id: str = "claude",
        region: str = "us-east-1",
        session: boto3.Session | None = None,
    ):
        """
        Args:
            model_id: Bedrock model ID or shorthand alias ("claude", "nova").
            region: AWS region for Bedrock endpoint.
            session: Optional boto3 session.
        """
        self._session = session or boto3.Session()
        self._model_id = MODEL_ALIASES.get(model_id, model_id)
        self._client = self._session.client(
            "bedrock-runtime", region_name=region, config=BOTO_CONFIG
        )
        logger.info("BedrockClient initialized: model=%s, region=%s", self._model_id, region)

    @property
    def model_id(self) -> str:
        return self._model_id

    def invoke(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """
        Send a prompt to Bedrock via the Converse API and return parsed JSON.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User message with the validation request.

        Returns:
            Parsed JSON dict from the model response.

        Raises:
            ValueError: If the response cannot be parsed as JSON.
            Exception: On Bedrock API errors.
        """
        logger.info("Invoking Bedrock model %s", self._model_id)

        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system_prompt}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_prompt}],
                }
            ],
            inferenceConfig={
                "maxTokens": 2048,
                "temperature": 0.1,
            },
        )

        # Extract text from Converse API response
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        raw_text = ""
        for block in content_blocks:
            if "text" in block:
                raw_text += block["text"]

        if not raw_text:
            raise ValueError("Empty response from Bedrock")

        result = self._parse_json_response(raw_text)

        usage = response.get("usage", {})
        logger.info(
            "Bedrock response: input_tokens=%s, output_tokens=%s",
            usage.get("inputTokens", "?"),
            usage.get("outputTokens", "?"),
        )

        return result

    @staticmethod
    def _parse_json_response(raw_text: str) -> dict[str, Any]:
        """
        Parse JSON from model response, handling markdown code fences.

        Supports responses wrapped in ```json ... ``` or plain JSON.
        """
        # Try to extract JSON from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_text, re.DOTALL)
        json_str = match.group(1).strip() if match else raw_text.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response: %s", raw_text[:500])
            raise ValueError(f"Could not parse Bedrock response as JSON: {e}") from e

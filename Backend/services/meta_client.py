"""Meta Llama chat client for reasoning and explanation tasks.

The client talks to an OpenAI-compatible ``/chat/completions`` endpoint so
the deployment can point at Meta's Llama API (or any compatible gateway)
without code changes. All three settings come from the environment so no
endpoint, key, or model identifier is hardcoded:

- ``META_API_URL``: base URL copied from the Meta developer console
  (the client appends ``/chat/completions`` and ``/models``).
- ``META_API_KEY``: API key (never logged, never echoed in errors).
- ``META_MODEL``: model identifier as listed in the Meta console.

Responses are strictly validated: the reply must carry a string message
that parses as a JSON object, otherwise a ``MetaClientError`` is raised
and callers fall back to deterministic output.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60


class MetaClientError(RuntimeError):
    """Raised when the Meta API call fails or returns an invalid reply."""


def _truncate(text: str, limit: int = 300) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


class MetaClient:
    """Minimal JSON-chat client for a Meta Llama deployment."""

    def __init__(self, *, api_key: str, api_url: str, model: str) -> None:
        if not api_key or not api_url or not model:
            raise ValueError("api_key, api_url, and model are all required.")
        self._api_key = api_key
        self._api_url = api_url.rstrip("/")
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @classmethod
    def from_env(cls) -> "MetaClient | None":
        """Build a client from the environment, or None when unconfigured."""
        api_key = (os.getenv("META_API_KEY") or "").strip()
        api_url = (os.getenv("META_API_URL") or "").strip()
        model = (os.getenv("META_MODEL") or "").strip()
        if not api_key or not api_url or not model:
            return None
        return cls(api_key=api_key, api_url=api_url, model=model)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def generate_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Send chat messages and return the reply parsed as a JSON object."""
        if not messages:
            raise MetaClientError("No messages supplied for Meta generation.")
        try:
            response = requests.post(
                f"{self._api_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.RequestException as error:
            raise MetaClientError(f"Meta API request failed: {error}") from error

        if response.status_code != 200:
            raise MetaClientError(
                f"Meta API returned HTTP {response.status_code}: "
                f"{_truncate(response.text)}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise MetaClientError(
                f"Meta API returned non-JSON output: {_truncate(response.text)}"
            ) from error

        choices = payload.get("choices") if isinstance(payload, dict) else None
        content = None
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise MetaClientError(
                "Meta API reply had no message content: "
                f"{_truncate(response.text)}"
            )
        try:
            parsed = json.loads(content)
        except ValueError as error:
            raise MetaClientError(
                f"Meta API reply was not valid JSON: {_truncate(content)}"
            ) from error
        if not isinstance(parsed, dict):
            raise MetaClientError("Meta API reply JSON was not an object.")
        return parsed

    def list_models(self) -> list[str]:
        """List model identifiers advertised by the endpoint."""
        try:
            response = requests.get(
                f"{self._api_url}/models",
                headers=self._headers(),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.RequestException as error:
            raise MetaClientError(f"Meta API request failed: {error}") from error
        if response.status_code != 200:
            raise MetaClientError(
                f"Meta API returned HTTP {response.status_code}: "
                f"{_truncate(response.text)}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise MetaClientError("Meta API returned non-JSON output.") from error
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise MetaClientError("Meta API model list had an unexpected shape.")
        return [str(entry.get("id")) for entry in entries if isinstance(entry, dict)]

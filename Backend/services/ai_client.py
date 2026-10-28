"""Shared reasoning client for the 3P Intelligence backend.

Meta Llama (via ``services.meta_client``) provides text reasoning,
summaries, and explanations. ``client`` is None unless ``META_API_KEY``,
``META_API_URL``, and ``META_MODEL`` are all configured; callers must
treat a None client (or a ``MetaClientError``) as "AI unavailable" and
fall back to deterministic output.
"""

from services.meta_client import MetaClient

client = MetaClient.from_env()

"""List model identifiers advertised by the configured Meta endpoint."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.meta_client import MetaClient, MetaClientError  # noqa: E402

load_dotenv()

client = MetaClient.from_env()
if client is None:
    raise SystemExit(
        "Set META_API_KEY, META_API_URL, and META_MODEL in your environment."
    )

try:
    models = client.list_models()
except MetaClientError as error:
    raise SystemExit(f"Meta API error: {error}")

print("Available Meta Models:")
for name in models:
    print(name)
print(f"\nCurrently configured META_MODEL={os.getenv('META_MODEL')}")

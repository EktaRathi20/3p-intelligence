"""Local JSON-file database for the 3P Intelligence backend.

Each collection is stored as one JSON file inside the ``database/`` directory
at the repository root (see ``database/README.md``). Files map document id to
document fields; read helpers inject the ``id`` key, matching the API shapes
previously produced from Firestore snapshots.

All access is funneled through this module so writes stay atomic (temp file +
rename) and read-modify-write sequences stay thread-safe via a process-wide
lock. Reads are cached in memory and invalidated by file modification time;
call :func:`clear_cache` after swapping ``DATABASE_DIR`` (tests do this).
"""

from __future__ import annotations

import json
import os
import secrets
import string
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_DIR = BACKEND_DIR.parent / "database"

# Logical collection name -> JSON file. Legacy Firestore collection names are
# accepted as aliases so existing code keeps working unchanged.
COLLECTION_FILES = {
    "users": "users.json",
    "dm_users": "users.json",
    "roles": "roles.json",
    "dm_roles": "roles.json",
    "regions": "regions.json",
    "hazards": "hazards.json",
    "hazardTypes": "hazards.json",
    "countries": "countries.json",
    "states": "states.json",
    "cities": "cities.json",
    "settings": "settings.json",
    "tasks": "tasks.json",
    "notifications": "notifications.json",
}

_ID_ALPHABET = string.ascii_letters + string.digits

_lock = threading.RLock()
# {(database_dir, filename): (mtime_ns, data)}; data is never mutated in place.
_file_cache: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}


class UnknownCollectionError(KeyError):
    """Raised when a collection name has no mapped JSON file."""


class DocumentNotFoundError(KeyError):
    """Raised when updating a document that does not exist."""


def get_database_dir() -> Path:
    """Resolve the database directory (``DATABASE_DIR`` env override)."""
    override = os.getenv("DATABASE_DIR")
    if override:
        return Path(override).expanduser()
    return DEFAULT_DATABASE_DIR


def clear_cache() -> None:
    """Drop cached file contents (used when ``DATABASE_DIR`` changes)."""
    with _lock:
        _file_cache.clear()


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string (replaces SERVER_TIMESTAMP)."""
    return datetime.now(timezone.utc).isoformat()


def generate_id(length: int = 20) -> str:
    """Generate a random alphanumeric document id (Firestore-style)."""
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(length))


def _collection_file(collection: str) -> str:
    try:
        return COLLECTION_FILES[collection]
    except KeyError:
        raise UnknownCollectionError(
            f"Unknown collection {collection!r}. "
            f"Known collections: {sorted(set(COLLECTION_FILES))}."
        ) from None


def _collection_path(collection: str) -> Path:
    return get_database_dir() / _collection_file(collection)


def _load_file(path: Path) -> dict[str, Any]:
    """Read and validate one collection file (missing file == empty)."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Database file {path} must contain a JSON object mapping "
            f"document id to fields."
        )
    for doc_id, fields in data.items():
        if not isinstance(fields, dict):
            raise ValueError(
                f"Database file {path} has a non-object record "
                f"for id {doc_id!r}."
            )
    return data


def read_collection(collection: str) -> dict[str, dict[str, Any]]:
    """Return a copy of every document in a collection, keyed by id.

    Results are cached by file modification time; every caller receives its
    own per-document copies, so mutating the result never corrupts the cache.
    """
    path = _collection_path(collection)
    cache_key = (str(path.parent), path.name)
    with _lock:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except FileNotFoundError:
            mtime_ns = -1
        cached = _file_cache.get(cache_key)
        if cached is not None and cached[0] == mtime_ns:
            data = cached[1]
        else:
            data = _load_file(path)
            _file_cache[cache_key] = (mtime_ns, data)
        return {doc_id: dict(fields) for doc_id, fields in data.items()}


def write_collection(collection: str, data: dict[str, dict[str, Any]]) -> None:
    """Replace a whole collection atomically (temp file + rename)."""
    path = _collection_path(collection)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_name, path)
            mtime_ns = path.stat().st_mtime_ns
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        _file_cache[(str(path.parent), path.name)] = (
            mtime_ns,
            {doc_id: dict(fields) for doc_id, fields in data.items()},
        )


def list_documents(
    collection: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """List documents with their ids injected, optionally capped."""
    docs = [
        {"id": doc_id, **fields}
        for doc_id, fields in read_collection(collection).items()
    ]
    if limit is not None:
        docs = docs[: max(0, limit)]
    return docs


def get_document(collection: str, doc_id: str) -> dict[str, Any] | None:
    """Return one document (with id) or None when it does not exist."""
    fields = read_collection(collection).get(str(doc_id))
    if fields is None:
        return None
    return {"id": str(doc_id), **fields}


def document_exists(collection: str, doc_id: str) -> bool:
    """Check whether a document id exists in a collection."""
    return str(doc_id) in read_collection(collection)


def count_documents(collection: str) -> int:
    """Return the number of documents in a collection."""
    return len(read_collection(collection))


def set_document(
    collection: str,
    doc_id: str,
    data: dict[str, Any],
    merge: bool = False,
) -> dict[str, Any]:
    """Create or replace a document; with ``merge`` keep other fields."""
    doc_id = str(doc_id)
    payload = {key: value for key, value in dict(data).items() if key != "id"}
    with _lock:
        docs = read_collection(collection)
        if merge and doc_id in docs:
            merged = dict(docs[doc_id])
            merged.update(payload)
            payload = merged
        docs[doc_id] = payload
        write_collection(collection, docs)
        return {"id": doc_id, **payload}


def update_document(collection: str, doc_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Merge fields into an existing document (KeyError when missing)."""
    doc_id = str(doc_id)
    payload = {key: value for key, value in dict(data).items() if key != "id"}
    with _lock:
        docs = read_collection(collection)
        if doc_id not in docs:
            raise DocumentNotFoundError(
                f"Document {doc_id!r} not found in collection {collection!r}."
            )
        merged = dict(docs[doc_id])
        merged.update(payload)
        docs[doc_id] = merged
        write_collection(collection, docs)
        return {"id": doc_id, **merged}


def delete_document(collection: str, doc_id: str) -> bool:
    """Delete a document; return True when it existed."""
    doc_id = str(doc_id)
    with _lock:
        docs = read_collection(collection)
        if doc_id not in docs:
            return False
        del docs[doc_id]
        write_collection(collection, docs)
        return True

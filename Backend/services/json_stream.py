"""Streaming parser for top-level JSON arrays of objects (stdlib only).

The full cities export is ~199MB uncompressed, so it cannot be parsed with
``json.load`` on small machines. This module scans the array incrementally
and decodes one object at a time, keeping memory proportional to a single
object plus one read chunk.

Only arrays of objects are supported (the shape of the dataset's
``countries.json``/``states.json``/``json-cities.json`` files); anything
else raises ``ValueError`` with the offending location.
"""

from __future__ import annotations

import gzip
import json
from typing import Any, Iterator

# Single-object sanity cap (real records are a few KB at most).
MAX_OBJECT_CHARS = 64 * 1024 * 1024


def iter_json_array(
    path,
    gzipped: bool = False,
    chunk_size: int = 1 << 20,
) -> Iterator[Any]:
    """Yield decoded objects from a top-level JSON array file."""
    opener = gzip.open if gzipped else open
    with opener(path, "rt", encoding="utf-8") as handle:
        yield from _iter_objects(handle, chunk_size, str(path))


def _iter_objects(handle, chunk_size: int, source_name: str) -> Iterator[Any]:
    seeking_start = True
    seeking_value = False
    trailing = False
    capturing = False

    depth = 0
    in_string = False
    escape = False
    span: list[str] = []
    index = 0

    def fail(message: str) -> ValueError:
        return ValueError(f"{message} in {source_name}")

    def finish_span():
        nonlocal index, capturing, seeking_value, span
        text = "".join(span)
        span = []
        capturing = False
        seeking_value = True
        if len(text) > MAX_OBJECT_CHARS:
            raise fail(f"JSON object #{index} exceeds the size cap")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise fail(
                f"Invalid JSON object #{index}: {exc}. "
                f"Snippet: {text[:200]!r}"
            ) from exc
        index += 1
        return value

    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            break
        for ch in chunk:
            if capturing:
                span.append(ch)
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                elif ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        yield finish_span()
                continue

            if seeking_start:
                if ch in " \t\r\n":
                    continue
                if ch != "[":
                    raise fail("Expected a JSON array")
                seeking_start = False
                seeking_value = True
                continue

            if trailing:
                if ch in " \t\r\n":
                    continue
                raise fail("Unexpected data after JSON array")

            # Seeking the next value (or the closing bracket).
            if ch in " \t\r\n,":
                continue
            if ch == "]":
                seeking_value = False
                trailing = True
                continue
            if ch != "{":
                raise fail(f"Expected a JSON object at index {index}")
            capturing = True
            seeking_value = False
            depth = 1
            in_string = False
            escape = False
            span = [ch]

    if seeking_start:
        raise fail("Expected a JSON array")
    if capturing:
        raise fail(f"Truncated JSON object #{index}")
    if seeking_value:
        raise fail("Truncated JSON array")

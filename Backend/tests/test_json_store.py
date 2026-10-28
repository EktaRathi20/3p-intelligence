"""Unit tests for the local JSON-file database store.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
Uses a temporary ``DATABASE_DIR`` (no repository data is touched).
"""

import json
import os
import shutil
import string
import tempfile
from pathlib import Path
import unittest
from datetime import datetime
from unittest import mock

from services import json_store


class JsonStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="json_store_test_")
        patcher = mock.patch.dict(
            os.environ, {"DATABASE_DIR": self.tmpdir}
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        json_store.clear_cache()
        self.addCleanup(json_store.clear_cache)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _raw_file(self, filename):
        path = os.path.join(self.tmpdir, filename)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_missing_collection_reads_as_empty(self):
        self.assertEqual(json_store.read_collection("regions"), {})
        self.assertEqual(json_store.list_documents("regions"), [])
        self.assertIsNone(json_store.get_document("regions", "nope"))
        self.assertEqual(json_store.count_documents("regions"), 0)
        self.assertFalse(json_store.document_exists("regions", "nope"))

    def test_set_and_get_roundtrip(self):
        record = json_store.set_document(
            "regions", "r1", {"name": "Vizag", "active": True}
        )
        self.assertEqual(
            record, {"id": "r1", "name": "Vizag", "active": True}
        )
        self.assertEqual(
            json_store.get_document("regions", "r1"), record
        )
        self.assertTrue(json_store.document_exists("regions", "r1"))
        self.assertEqual(json_store.count_documents("regions"), 1)

    def test_id_is_not_persisted_in_fields(self):
        json_store.set_document("regions", "r1", {"id": "ignored", "n": 1})
        self.assertEqual(self._raw_file("regions.json"), {"r1": {"n": 1}})

    def test_set_replaces_by_default(self):
        json_store.set_document("regions", "r1", {"a": 1, "b": 2})
        json_store.set_document("regions", "r1", {"a": 9})
        self.assertEqual(
            json_store.get_document("regions", "r1"), {"id": "r1", "a": 9}
        )

    def test_set_merge_preserves_unrelated_fields(self):
        json_store.set_document("regions", "r1", {"a": 1, "custom": True})
        json_store.set_document("regions", "r1", {"a": 2}, merge=True)
        self.assertEqual(
            json_store.get_document("regions", "r1"),
            {"id": "r1", "a": 2, "custom": True},
        )

    def test_update_merges_and_returns_full_record(self):
        json_store.set_document("regions", "r1", {"a": 1, "b": 2})
        record = json_store.update_document("regions", "r1", {"b": 3})
        self.assertEqual(record, {"id": "r1", "a": 1, "b": 3})

    def test_update_missing_raises(self):
        with self.assertRaises(json_store.DocumentNotFoundError):
            json_store.update_document("regions", "nope", {"a": 1})
        with self.assertRaises(KeyError):
            json_store.update_document("regions", "nope", {"a": 1})

    def test_delete_document(self):
        json_store.set_document("regions", "r1", {"a": 1})
        self.assertTrue(json_store.delete_document("regions", "r1"))
        self.assertFalse(json_store.document_exists("regions", "r1"))
        self.assertFalse(json_store.delete_document("regions", "r1"))

    def test_list_documents_limit(self):
        for index in range(5):
            json_store.set_document(
                "regions", f"r{index}", {"n": index}
            )
        self.assertEqual(
            len(json_store.list_documents("regions")), 5
        )
        self.assertEqual(
            len(json_store.list_documents("regions", limit=2)), 2
        )
        for record in json_store.list_documents("regions"):
            self.assertIn("id", record)

    def test_legacy_collection_aliases_share_files(self):
        json_store.set_document("dm_users", "u1", {"name": "A"})
        self.assertEqual(
            json_store.get_document("users", "u1"),
            {"id": "u1", "name": "A"},
        )
        json_store.set_document("hazardTypes", "h1", {"name": "Flood"})
        self.assertEqual(
            json_store.get_document("hazards", "h1"),
            {"id": "h1", "name": "Flood"},
        )
        json_store.set_document("dm_roles", "role_1", {"name": "R"})
        self.assertEqual(
            json_store.get_document("roles", "role_1"),
            {"id": "role_1", "name": "R"},
        )

    def test_unknown_collection_raises(self):
        with self.assertRaises(json_store.UnknownCollectionError):
            json_store.read_collection("nope")
        with self.assertRaises(KeyError):
            json_store.get_document("nope", "x")

    def test_non_object_file_raises(self):
        path = os.path.join(self.tmpdir, "regions.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([1, 2, 3], handle)
        with self.assertRaises(ValueError):
            json_store.read_collection("regions")

    def test_writes_leave_no_temp_files(self):
        json_store.set_document("regions", "r1", {"a": 1})
        leftovers = [
            name
            for name in os.listdir(self.tmpdir)
            if name.endswith(".tmp") or ".tmp" in name
        ]
        self.assertEqual(leftovers, [])

    def test_readers_get_independent_copies(self):
        json_store.set_document("regions", "r1", {"a": 1})
        first = json_store.read_collection("regions")
        first["r1"]["a"] = 999
        self.assertEqual(
            json_store.get_document("regions", "r1"), {"id": "r1", "a": 1}
        )

    def test_external_edits_are_picked_up(self):
        json_store.set_document("regions", "r1", {"a": 1})
        self.assertEqual(json_store.count_documents("regions"), 1)
        path = os.path.join(self.tmpdir, "regions.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"r2": {"a": 2}}, handle)
        # Force a distinct mtime so the change is visible on any filesystem.
        stat = os.stat(path)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
        self.assertEqual(
            json_store.get_document("regions", "r2"), {"id": "r2", "a": 2}
        )
        self.assertIsNone(json_store.get_document("regions", "r1"))

    def test_generate_id_format_and_uniqueness(self):
        seen = set()
        for _ in range(200):
            value = json_store.generate_id()
            self.assertEqual(len(value), 20)
            self.assertTrue(
                all(char in string.ascii_letters + string.digits for char in value)
            )
            seen.add(value)
        self.assertEqual(len(seen), 200)

    def test_utcnow_iso_is_parseable(self):
        stamp = json_store.utcnow_iso()
        parsed = datetime.fromisoformat(stamp)
        self.assertIsNotNone(parsed.tzinfo)

    def test_database_dir_override_and_default(self):
        self.assertEqual(
            json_store.get_database_dir(), Path(self.tmpdir)
        )
        with mock.patch.dict(os.environ):
            os.environ.pop("DATABASE_DIR", None)
            self.assertEqual(
                json_store.get_database_dir(),
                json_store.DEFAULT_DATABASE_DIR,
            )


if __name__ == "__main__":
    unittest.main()

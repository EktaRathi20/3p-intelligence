"""Unit tests for the JSON geo sync script.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
Uses a temporary ``DATABASE_DIR`` plus tiny JSON fixtures (no network or
live dataset downloads).
"""

import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "scripts")
)

import sync_geo_data
from services import json_store


def write_json_fixture(records):
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(records, handle)
    handle.close()
    return handle.name


def write_gz_fixture(records):
    handle = tempfile.NamedTemporaryFile(suffix=".json.gz", delete=False)
    handle.close()
    with gzip.open(handle.name, "wt", encoding="utf-8") as out:
        json.dump(records, out)
    return handle.name


SAMPLE_COUNTRIES = [
    {"iso2": "IN", "name": "India", "emoji": "IN-flag",
     "region": "Asia", "iso3": "IND"},
    {"iso2": "us", "name": "  United States  "},
    {"iso2": "X", "name": "Bad code"},
    {"iso2": "XX", "name": ""},
    "not-a-dict",
]

SAMPLE_STATES = [
    {"id": 2, "country_code": "IN", "iso2": "rj", "name": "Rajasthan",
     "type": "state", "latitude": "26.0", "longitude": 74.0},
    {"id": "3", "country_code": "us", "iso2": "CA", "name": "California"},
    {"id": None, "country_code": "IN", "name": "Missing id"},
    {"id": 9, "country_code": "USA", "name": "Bad country"},
    {"id": 10, "country_code": "IN", "name": "  "},
]

SAMPLE_CITIES = [
    {"id": 102, "country_code": "IN", "state_code": "rj",
     "state_name": "Rajasthan", "name": "Jodhpur",
     "latitude": 26.2, "longitude": "73.0"},
    {"id": "105", "country_code": "US", "state_code": "CA",
     "state_name": "California", "name": "San Francisco"},
    {"id": 106, "country_code": "US", "name": "No State City"},
    {"id": None, "country_code": "IN", "name": "Missing id"},
    {"id": 108, "country_code": "XX1", "name": "Bad country"},
]


class DocumentBuilderTest(unittest.TestCase):
    def test_build_country_doc(self):
        doc_id, data = sync_geo_data.build_country_doc(SAMPLE_COUNTRIES[0])
        self.assertEqual(doc_id, "IN")
        self.assertEqual(data["code"], "IN")
        self.assertEqual(data["name"], "India")
        self.assertEqual(data["nameLower"], "india")
        self.assertEqual(data["flag"], "IN-flag")

    def test_build_country_doc_normalizes(self):
        doc_id, data = sync_geo_data.build_country_doc(SAMPLE_COUNTRIES[1])
        self.assertEqual(doc_id, "US")
        self.assertEqual(data["name"], "United States")

    def test_build_country_doc_skips_invalid(self):
        # Builders take dicts (non-dict rows are skipped by sync_*).
        for record in SAMPLE_COUNTRIES[2:4]:
            self.assertIsNone(sync_geo_data.build_country_doc(record))

    def test_build_state_doc_uses_provider_id(self):
        doc_id, data = sync_geo_data.build_state_doc(SAMPLE_STATES[0])
        self.assertEqual(doc_id, "2")
        self.assertEqual(data["providerId"], 2)
        self.assertEqual(data["countryCode"], "IN")
        self.assertEqual(data["code"], "RJ")
        self.assertEqual(data["name"], "Rajasthan")
        self.assertEqual(data["nameLower"], "rajasthan")
        self.assertEqual(data["latitude"], 26.0)
        self.assertEqual(data["longitude"], 74.0)

    def test_build_state_doc_accepts_string_id(self):
        doc_id, data = sync_geo_data.build_state_doc(SAMPLE_STATES[1])
        self.assertEqual(doc_id, "3")
        self.assertEqual(data["providerId"], 3)

    def test_build_state_doc_skips_invalid(self):
        for record in SAMPLE_STATES[2:]:
            self.assertIsNone(sync_geo_data.build_state_doc(record))

    def test_build_city_doc_uses_provider_id(self):
        doc_id, data = sync_geo_data.build_city_doc(SAMPLE_CITIES[0])
        self.assertEqual(doc_id, "102")
        self.assertEqual(data["providerId"], 102)
        self.assertEqual(data["countryCode"], "IN")
        self.assertEqual(data["stateCode"], "RJ")
        self.assertEqual(data["stateName"], "Rajasthan")
        self.assertEqual(data["nameLower"], "jodhpur")

    def test_build_city_doc_allows_missing_state(self):
        doc_id, data = sync_geo_data.build_city_doc(SAMPLE_CITIES[2])
        self.assertEqual(doc_id, "106")
        self.assertIsNone(data["stateCode"])
        self.assertIsNone(data["stateName"])

    def test_build_city_doc_skips_invalid(self):
        for record in SAMPLE_CITIES[3:]:
            self.assertIsNone(sync_geo_data.build_city_doc(record))

    def test_builders_stamp_iso_updated_at(self):
        for built in (
            sync_geo_data.build_country_doc(SAMPLE_COUNTRIES[0]),
            sync_geo_data.build_state_doc(SAMPLE_STATES[0]),
            sync_geo_data.build_city_doc(SAMPLE_CITIES[0]),
        ):
            assert built is not None
            stamp = built[1]["updatedAt"]
            self.assertIsNotNone(datetime.fromisoformat(stamp).tzinfo)


class TempDatabaseMixin:
    def _use_temp_database(self):
        tmpdir = tempfile.mkdtemp(prefix="sync_geo_test_")
        self.addCleanup(shutil.rmtree, tmpdir, True)
        patcher = mock.patch.dict(os.environ, {"DATABASE_DIR": tmpdir})
        self.addCleanup(patcher.stop)
        patcher.start()
        json_store.clear_cache()
        self.addCleanup(json_store.clear_cache)
        return tmpdir


class SyncFunctionsTest(TempDatabaseMixin, unittest.TestCase):
    def test_sync_countries(self):
        self._use_temp_database()
        path = write_json_fixture(SAMPLE_COUNTRIES)
        try:
            result = sync_geo_data.sync_countries(path)
        finally:
            os.unlink(path)
        self.assertEqual(result, {"written": 2, "skipped": 3})
        stored = json_store.read_collection("countries")
        self.assertEqual(sorted(stored), ["IN", "US"])
        self.assertEqual(stored["US"]["name"], "United States")

    def test_sync_states(self):
        self._use_temp_database()
        path = write_json_fixture(SAMPLE_STATES)
        try:
            result = sync_geo_data.sync_states(path)
        finally:
            os.unlink(path)
        self.assertEqual(result, {"written": 2, "skipped": 3})
        self.assertEqual(sorted(json_store.read_collection("states")),
                         ["2", "3"])

    def test_sync_states_respects_max_records(self):
        self._use_temp_database()
        path = write_json_fixture(SAMPLE_STATES)
        try:
            result = sync_geo_data.sync_states(path, max_records=1)
        finally:
            os.unlink(path)
        self.assertEqual(result["written"], 1)

    def test_sync_cities_streams_gzip(self):
        self._use_temp_database()
        path = write_gz_fixture(SAMPLE_CITIES)
        try:
            result = sync_geo_data.sync_cities(path)
        finally:
            os.unlink(path)
        self.assertEqual(result, {"written": 3, "skipped": 2})
        stored = json_store.read_collection("cities")
        self.assertEqual(sorted(stored), ["102", "105", "106"])
        self.assertEqual(stored["102"]["nameLower"], "jodhpur")

    def test_sync_cities_respects_max_records(self):
        self._use_temp_database()
        path = write_gz_fixture(SAMPLE_CITIES)
        try:
            result = sync_geo_data.sync_cities(path, max_records=2)
        finally:
            os.unlink(path)
        self.assertEqual(result["written"], 2)

    def test_sync_rejects_non_list_payload(self):
        self._use_temp_database()
        path = write_json_fixture({"not": "a list"})
        try:
            with self.assertRaises(ValueError):
                sync_geo_data.sync_countries(path)
        finally:
            os.unlink(path)

    def test_sync_merges_and_preserves_unrelated_fields(self):
        self._use_temp_database()
        json_store.set_document(
            "countries", "IN", {"name": "Old", "custom": True}
        )
        path = write_json_fixture(SAMPLE_COUNTRIES)
        try:
            sync_geo_data.sync_countries(path)
        finally:
            os.unlink(path)
        stored = json_store.get_document("countries", "IN")
        assert stored is not None
        self.assertEqual(stored["name"], "India")
        self.assertTrue(stored["custom"])

    def test_dry_run_counts_without_writes(self):
        tmpdir = self._use_temp_database()
        path = write_json_fixture(SAMPLE_COUNTRIES)
        try:
            result = sync_geo_data.sync_countries(path, dry_run=True)
        finally:
            os.unlink(path)
        self.assertEqual(result, {"written": 2, "skipped": 3})
        self.assertEqual(os.listdir(tmpdir), [])

    def test_write_sync_meta_merges_counts(self):
        self._use_temp_database()
        json_store.write_collection("settings", {
            "geoSync": {"countries": 250, "states": 5000, "cities": 150000}
        })
        meta = sync_geo_data.write_sync_meta("v1", {"countries": 251})
        self.assertEqual(meta["countries"], 251)
        self.assertEqual(meta["states"], 5000)
        self.assertEqual(meta["cities"], 150000)
        self.assertEqual(meta["datasetRef"], "v1")
        stored = json_store.get_document("settings", "geoSync")
        assert stored is not None
        self.assertEqual(stored["countries"], 251)

    def test_write_sync_meta_dry_run_writes_nothing(self):
        tmpdir = self._use_temp_database()
        meta = sync_geo_data.write_sync_meta("v1", {"countries": 1},
                                             dry_run=True)
        self.assertEqual(meta["countries"], 1)
        self.assertEqual(os.listdir(tmpdir), [])


class ResolveCollectionsTest(unittest.TestCase):
    def _args(self, **overrides):
        args = mock.Mock(
            collections="countries,states,cities",
            skip_cities=False,
            countries_only=False,
        )
        for key, value in overrides.items():
            setattr(args, key, value)
        return args

    def test_defaults_to_all(self):
        self.assertEqual(
            sync_geo_data.resolve_collections(self._args()),
            {"countries", "states", "cities"},
        )

    def test_subset_and_case_insensitive(self):
        self.assertEqual(
            sync_geo_data.resolve_collections(
                self._args(collections="Countries, STATES")
            ),
            {"countries", "states"},
        )

    def test_skip_cities(self):
        self.assertEqual(
            sync_geo_data.resolve_collections(self._args(skip_cities=True)),
            {"countries", "states"},
        )

    def test_countries_only(self):
        self.assertEqual(
            sync_geo_data.resolve_collections(
                self._args(countries_only=True)
            ),
            {"countries"},
        )

    def test_unknown_and_empty_rejected(self):
        with self.assertRaises(ValueError):
            sync_geo_data.resolve_collections(
                self._args(collections="countries,bogus")
            )
        with self.assertRaises(ValueError):
            sync_geo_data.resolve_collections(self._args(collections="  "))


class CheckStatusTest(TempDatabaseMixin, unittest.TestCase):
    def test_empty_database_reports_missing(self):
        self._use_temp_database()
        with mock.patch("builtins.print"):
            self.assertEqual(sync_geo_data.check_status(), 1)

    def test_synced_database_reports_ok(self):
        self._use_temp_database()
        json_store.write_collection("countries", {"IN": {"name": "India"}})
        json_store.write_collection("states", {"2": {"name": "Rajasthan"}})
        json_store.write_collection("cities", {"102": {"name": "Jodhpur"}})
        sync_geo_data.write_sync_meta(
            "test", {"countries": 1, "states": 1, "cities": 1}
        )
        with mock.patch("builtins.print"):
            self.assertEqual(
                sync_geo_data.check_status(verify_counts=True), 0
            )


if __name__ == "__main__":
    unittest.main()

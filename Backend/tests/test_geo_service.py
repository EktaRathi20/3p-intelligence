"""Unit tests for the JSON-backed geo service.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
Uses a temporary ``DATABASE_DIR`` (no repository data or network access).
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from services import geo_service, json_store


def seed_store():
    json_store.write_collection("countries", {
        "IN": {"code": "IN", "name": "India", "region": "Asia"},
        "US": {"code": "US", "name": "United States",
               "region": "Americas"},
    })
    json_store.write_collection("states", {
        "1": {"countryCode": "IN", "code": "MH", "name": "Maharashtra",
              "type": "state", "latitude": 19.0, "longitude": 73.0},
        "2": {"countryCode": "IN", "code": "RJ", "name": "Rajasthan",
              "type": "state", "latitude": 26.0, "longitude": 74.0},
        "3": {"countryCode": "US", "code": "CA", "name": "California",
              "type": "state", "latitude": 37.0, "longitude": -120.0},
    })
    json_store.write_collection("cities", {
        "101": {"countryCode": "IN", "stateCode": "RJ",
                "stateName": "Rajasthan", "name": "Jaipur",
                "nameLower": "jaipur", "latitude": 26.9,
                "longitude": 75.8},
        "102": {"countryCode": "IN", "stateCode": "RJ",
                "stateName": "Rajasthan", "name": "Jodhpur",
                "nameLower": "jodhpur", "latitude": 26.2,
                "longitude": 73.0},
        # Duplicate city name with a distinct stable id.
        "103": {"countryCode": "IN", "stateCode": "RJ",
                "stateName": "Rajasthan", "name": "Jodhpur",
                "nameLower": "jodhpur", "latitude": 26.3,
                "longitude": 73.1},
        "104": {"countryCode": "IN", "stateCode": "MH",
                "stateName": "Maharashtra", "name": "Mumbai",
                "nameLower": "mumbai", "latitude": 19.0,
                "longitude": 72.8},
        "105": {"countryCode": "US", "stateCode": "CA",
                "stateName": "California", "name": "San Francisco",
                "nameLower": "san francisco", "latitude": 37.7,
                "longitude": -122.4},
        "106": {"countryCode": "US", "stateCode": "CA",
                "stateName": "California", "name": "100% Cotton Town",
                "nameLower": "100% cotton town", "latitude": 37.0,
                "longitude": -121.0},
        "107": {"countryCode": "IN", "stateCode": "MH",
                "stateName": "Maharashtra", "name": "Old Jaipur",
                "nameLower": "old jaipur", "latitude": 19.1,
                "longitude": 72.9},
    })
    json_store.write_collection("settings", {
        "geoSync": {"countries": 2, "states": 3, "cities": 7,
                    "datasetRef": "test-fixture",
                    "syncedAt": "2026-01-01T00:00:00+00:00"},
    })


class GeoServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="geo_service_test_")
        patcher = mock.patch.dict(
            os.environ, {"DATABASE_DIR": self.tmpdir}
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        geo_service.clear_cache()
        self.addCleanup(geo_service.clear_cache)
        seed_store()

    def _counted_reads(self):
        """Patch read_collection with a call counter; return the mock."""
        original = json_store.read_collection
        counter = mock.Mock(side_effect=lambda *a, **k: original(*a, **k))
        patcher = mock.patch.object(json_store, "read_collection", counter)
        self.addCleanup(patcher.stop)
        patcher.start()
        return counter

    def test_list_countries_sorted_and_shaped(self):
        countries = geo_service.list_countries()
        self.assertEqual(
            [country["name"] for country in countries],
            ["India", "United States"],
        )
        self.assertEqual(countries[0]["id"], "IN")
        self.assertEqual(countries[0]["code"], "IN")

    def test_list_countries_search_and_limit(self):
        self.assertEqual(len(geo_service.list_countries(search="united")), 1)
        self.assertEqual(len(geo_service.list_countries(search="in")), 1)
        self.assertEqual(geo_service.list_countries(search="nope"), [])
        self.assertEqual(len(geo_service.list_countries(limit=1)), 1)

    def test_list_countries_is_cached(self):
        counter = self._counted_reads()
        geo_service.list_countries()
        reads_after_first = counter.call_count
        self.assertGreater(reads_after_first, 0)
        geo_service.list_countries(search="in")
        self.assertEqual(counter.call_count, reads_after_first)
        geo_service.clear_cache()
        geo_service.list_countries()
        self.assertGreater(counter.call_count, reads_after_first)

    def test_list_states_sorted_and_shaped(self):
        states = geo_service.list_states("in")
        self.assertEqual(
            [state["name"] for state in states],
            ["Maharashtra", "Rajasthan"],
        )
        self.assertEqual(states[1]["code"], "RJ")
        self.assertEqual(states[1]["countryCode"], "IN")
        self.assertEqual(states[1]["type"], "state")
        self.assertEqual(states[1]["latitude"], 26.0)

    def test_list_states_search_filters_by_name_or_code(self):
        self.assertEqual(len(geo_service.list_states("IN", search="rajas")), 1)
        self.assertEqual(len(geo_service.list_states("IN", search="mh")), 1)
        self.assertEqual(geo_service.list_states("IN", search="nope"), [])

    def test_list_states_is_cached_per_country(self):
        counter = self._counted_reads()
        geo_service.list_states("IN")
        reads_after_first = counter.call_count
        geo_service.list_states("IN", search="raj")
        self.assertEqual(counter.call_count, reads_after_first)
        geo_service.list_states("US")
        self.assertGreater(counter.call_count, reads_after_first)

    def test_country_has_subdivisions(self):
        self.assertTrue(geo_service.country_has_subdivisions("IN"))
        self.assertFalse(geo_service.country_has_subdivisions("XX"))

    def test_country_has_subdivisions_reuses_state_cache(self):
        counter = self._counted_reads()
        geo_service.list_states("IN")
        reads = counter.call_count
        self.assertTrue(geo_service.country_has_subdivisions("IN"))
        self.assertEqual(counter.call_count, reads)

    def test_get_state(self):
        state = geo_service.get_state("IN", "rj")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state["name"], "Rajasthan")
        self.assertIsNone(geo_service.get_state("IN", "ZZ"))
        self.assertIsNone(geo_service.get_state("US", "RJ"))

    def test_get_state_reuses_state_cache(self):
        counter = self._counted_reads()
        geo_service.list_states("IN")
        reads = counter.call_count
        self.assertIsNotNone(geo_service.get_state("IN", "RJ"))
        self.assertEqual(counter.call_count, reads)

    def test_search_cities_filters_and_paginates(self):
        first = geo_service.search_cities("IN", state_code="RJ", limit=2,
                                          page=1)
        self.assertEqual(first["total"], 3)
        self.assertEqual(first["totalPages"], 2)
        self.assertEqual(len(first["items"]), 2)
        second = geo_service.search_cities("IN", state_code="RJ", limit=2,
                                           page=2)
        self.assertEqual(len(second["items"]), 1)
        first_ids = {item["id"] for item in first["items"]}
        second_ids = {item["id"] for item in second["items"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_search_cities_prefix_matches_from_name_start(self):
        result = geo_service.search_cities("IN", search="Jodh")
        self.assertEqual(result["total"], 2)
        ids = sorted(item["id"] for item in result["items"])
        self.assertEqual(ids, ["102", "103"])
        # Prefix search: a mid-name substring does not match.
        mid = geo_service.search_cities("IN", search="odhpur")
        self.assertEqual(mid["total"], 0)
        self.assertEqual(mid["items"], [])

    def test_search_cities_is_case_insensitive(self):
        result = geo_service.search_cities("US", search="sAn")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["name"], "San Francisco")

    def test_search_cities_without_state_searches_country(self):
        result = geo_service.search_cities("IN", search="Mumbai")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["stateCode"], "MH")

    def test_search_cities_treats_search_literally(self):
        result = geo_service.search_cities("US", search="100%")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["name"], "100% Cotton Town")

    def test_search_cities_limit_is_capped(self):
        result = geo_service.search_cities("IN", limit=10000)
        self.assertEqual(result["limit"], geo_service.MAX_CITY_LIMIT)

    def test_search_cities_empty_result_shape(self):
        result = geo_service.search_cities("XX")
        self.assertEqual(
            result,
            {"items": [], "page": 1, "limit": 20, "total": 0,
             "totalPages": 0},
        )

    def test_search_cities_reuses_city_index_cache(self):
        counter = self._counted_reads()
        geo_service.search_cities("IN", state_code="RJ")
        reads = counter.call_count
        self.assertGreater(reads, 0)
        geo_service.search_cities("US", search="san")
        self.assertEqual(counter.call_count, reads)

    def test_get_city(self):
        city = geo_service.get_city("102")
        self.assertIsNotNone(city)
        assert city is not None
        self.assertEqual(city["name"], "Jodhpur")
        self.assertEqual(city["stateCode"], "RJ")
        self.assertIsNone(geo_service.get_city("999999"))
        self.assertIsNone(geo_service.get_city(""))
        self.assertIsNone(geo_service.get_city("a/b"))
        self.assertIsNone(geo_service.get_city(True))

    def test_status_reports_coverage(self):
        status = geo_service.get_status()
        self.assertTrue(status["synced"])
        self.assertEqual(status["countries"], 2)
        self.assertEqual(status["states"], 3)
        self.assertEqual(status["cities"], 7)
        self.assertEqual(status["meta"]["dataset_ref"], "test-fixture")
        self.assertIn("Countries States Cities Database", status["attribution"])

    def test_status_is_cached(self):
        counter = self._counted_reads()
        geo_service.get_status()
        reads = counter.call_count
        geo_service.get_status()
        self.assertEqual(counter.call_count, reads)

    def test_missing_sync_meta_reports_unavailable(self):
        json_store.write_collection("settings", {})
        geo_service.clear_cache()
        status = geo_service.get_status()
        self.assertFalse(status["synced"])
        self.assertIn("sync_geo_data.py", status["error"])
        with self.assertRaises(geo_service.GeoDataUnavailable):
            geo_service.list_states("IN")
        with self.assertRaises(geo_service.GeoDataUnavailable):
            geo_service.search_cities("IN")
        with self.assertRaises(geo_service.GeoDataUnavailable):
            geo_service.get_city("102")
        with self.assertRaises(geo_service.GeoDataUnavailable):
            geo_service.get_state("IN", "RJ")
        with self.assertRaises(geo_service.GeoDataUnavailable):
            geo_service.country_has_subdivisions("IN")

    def test_empty_database_reports_unavailable(self):
        for filename in os.listdir(self.tmpdir):
            os.unlink(os.path.join(self.tmpdir, filename))
        geo_service.clear_cache()
        status = geo_service.get_status()
        self.assertFalse(status["synced"])
        self.assertIn("sync_geo_data.py", status["error"])

    def test_list_countries_works_without_sync_meta(self):
        # Countries were always readable without the states/cities sync.
        json_store.write_collection("settings", {})
        geo_service.clear_cache()
        self.assertEqual(len(geo_service.list_countries()), 2)

    def test_status_survives_corrupt_settings_file(self):
        path = os.path.join(self.tmpdir, "settings.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        # Force a distinct mtime so the change is visible on any filesystem.
        stat = os.stat(path)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
        geo_service.clear_cache()
        status = geo_service.get_status()
        self.assertFalse(status["synced"])
        self.assertIn("unavailable", status["error"].lower())

    def test_sync_meta_has_no_injected_id(self):
        meta = geo_service.get_sync_meta()
        assert meta is not None
        self.assertNotIn("id", meta)
        self.assertEqual(meta["datasetRef"], "test-fixture")


if __name__ == "__main__":
    unittest.main()

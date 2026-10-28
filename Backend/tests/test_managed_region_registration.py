import unittest
from unittest import mock

from ingestion_layer.constant import (
    REGION_COORDS,
    REGION_DATA,
    register_managed_regions,
)


class ManagedRegionRegistrationTests(unittest.TestCase):
    def tearDown(self):
        REGION_COORDS.pop("in-rj-jdh", None)
        REGION_DATA.pop("in-rj-jdh", None)

    @mock.patch("services.geo_service.get_city")
    @mock.patch("services.json_store.list_documents")
    def test_registers_managed_city_by_lowercase_region_code(
        self, list_documents, get_city
    ):
        list_documents.return_value = [{
            "id": "managed-region-id",
            "code": "IN-RJ-JDH",
            "name": "Jodhpur",
            "active": True,
            "cityId": "city-id",
        }]
        get_city.return_value = {
            "id": "city-id",
            "name": "Jodhpur",
            "latitude": 26.2389,
            "longitude": 73.0243,
        }

        register_managed_regions()

        self.assertEqual(
            REGION_COORDS["in-rj-jdh"],
            {"lat": 26.2389, "lon": 73.0243},
        )
        self.assertEqual(REGION_DATA["in-rj-jdh"]["name"], "Jodhpur")


if __name__ == "__main__":
    unittest.main()

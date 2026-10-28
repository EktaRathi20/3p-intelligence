"""Unit tests for pure region/geo validation helpers.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
No credentials or network access required.
"""

import unittest

from services.geo_validation import (
    build_default_region_code,
    is_valid_region_code,
    normalize_city_id,
    normalize_country_code,
    normalize_region_code,
    normalize_state_code,
    region_code_error,
    slug_token,
    suggest_region_name,
)


class NormalizeHelpersTest(unittest.TestCase):
    def test_normalize_country_code(self):
        self.assertEqual(normalize_country_code("in"), "IN")
        self.assertEqual(normalize_country_code("  US "), "US")
        self.assertIsNone(normalize_country_code(None))
        self.assertIsNone(normalize_country_code("   "))

    def test_normalize_state_code(self):
        self.assertEqual(normalize_state_code("rj"), "RJ")
        self.assertIsNone(normalize_state_code(""))
        self.assertIsNone(normalize_state_code(None))

    def test_normalize_city_id(self):
        self.assertEqual(normalize_city_id(126938), "126938")
        self.assertEqual(normalize_city_id(" 42 "), "42")
        self.assertIsNone(normalize_city_id(None))
        self.assertIsNone(normalize_city_id(""))
        self.assertIsNone(normalize_city_id(True))

    def test_normalize_region_code(self):
        self.assertEqual(normalize_region_code(" in-rj-jod "), "IN-RJ-JOD")
        self.assertIsNone(normalize_region_code(None))
        self.assertIsNone(normalize_region_code("  "))


class RegionCodeFormatTest(unittest.TestCase):
    def test_valid_codes(self):
        for code in ("AB", "IN-RJ-JOD", "US_CA_SF1", "A1", "X" * 24):
            with self.subTest(code=code):
                self.assertTrue(is_valid_region_code(code), code)
                self.assertIsNone(region_code_error(code))

    def test_lowercase_is_normalized_before_validation(self):
        self.assertTrue(is_valid_region_code("in-rj-jod"))

    def test_invalid_codes(self):
        for code in (
            "A",  # too short
            "X" * 25,  # too long
            "-AB",  # leading hyphen
            "AB-",  # trailing hyphen
            "AB CD",  # interior space
            "AB.CD",  # dot not allowed
            "",  # blank
            None,
        ):
            with self.subTest(code=code):
                self.assertFalse(is_valid_region_code(code))
                self.assertIsNotNone(region_code_error(code))


class DefaultCodeGenerationTest(unittest.TestCase):
    def test_full_hierarchy(self):
        self.assertEqual(
            build_default_region_code("in", "rj", "Jodhpur"), "IN-RJ-JDH"
        )

    def test_without_city(self):
        self.assertEqual(build_default_region_code("IN", "RJ", None), "IN-RJ")

    def test_without_state(self):
        self.assertEqual(
            build_default_region_code("SG", None, "Singapore"), "SG-SNG"
        )

    def test_country_only(self):
        self.assertEqual(build_default_region_code("fr", None, None), "FR")

    def test_slug_token_prefers_consonants(self):
        self.assertEqual(slug_token("Jodhpur"), "JDH")
        self.assertEqual(slug_token("Mumbai"), "MMB")

    def test_slug_token_folds_accents(self):
        self.assertEqual(slug_token("São Paulo"), "SPL")

    def test_slug_token_short_and_empty_names(self):
        self.assertEqual(slug_token("Go"), "GO")
        self.assertEqual(slug_token(""), "XXX")
        self.assertEqual(slug_token("123"), "XXX")

    def test_suggest_region_name(self):
        self.assertEqual(suggest_region_name("  Jodhpur "), "Jodhpur")
        self.assertEqual(suggest_region_name(None, fallback="Manual"), "Manual")
        self.assertEqual(suggest_region_name("   "), "")


if __name__ == "__main__":
    unittest.main()

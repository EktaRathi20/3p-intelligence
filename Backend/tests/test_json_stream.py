"""Unit tests for the streaming JSON-array parser.

Run from ``Backend/``: ``python -m unittest discover -s tests -v``.
No credentials or network access required.
"""

import gzip
import tempfile
import unittest
from pathlib import Path

from services.json_stream import iter_json_array


def write_fixture(content: str, gzipped: bool = False) -> Path:
    suffix = ".json.gz" if gzipped else ".json"
    handle = tempfile.NamedTemporaryFile(
        mode="wb", suffix=suffix, delete=False
    )
    path = Path(handle.name)
    handle.close()
    if gzipped:
        with gzip.open(path, "wt", encoding="utf-8") as out:
            out.write(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


class IterJsonArrayTest(unittest.TestCase):
    def test_compact_and_pretty_arrays(self):
        cases = [
            '[{"a": 1}, {"b": [1, 2, {"c": null}]}]',
            '[\n  {"a": 1},\n  {"b": [1, 2, {"c": null}]}\n]\n',
            '[{"x": ""}]',
        ]
        for chunk_size in (1, 7, 1 << 20):
            for content in cases:
                path = write_fixture(content)
                try:
                    with self.subTest(chunk_size=chunk_size, content=content):
                        self.assertEqual(
                            list(iter_json_array(path, chunk_size=chunk_size)),
                            [{"a": 1}, {"b": [1, 2, {"c": None}]}]
                            if '"a"' in content
                            else [{"x": ""}],
                        )
                finally:
                    path.unlink()

    def test_escapes_unicode_and_braces_in_strings(self):
        content = (
            '[{"name": "a\\"b\\\\c{d[e]f}g", "native": "Sarandí \\u5409", '
            '"emoji": "\\ud83c\\udde6\\ud83c\\uddeb"}, '
            '{"empty": {}, "list": ["}", "{", ","]}]'
        )
        for chunk_size in (3, 64):
            path = write_fixture(content)
            try:
                with self.subTest(chunk_size=chunk_size):
                    items = list(iter_json_array(path, chunk_size=chunk_size))
                    self.assertEqual(len(items), 2)
                    self.assertEqual(items[0]["name"], 'a"b\\c{d[e]f}g')
                    self.assertIn("Sarandí", items[0]["native"])
                    self.assertEqual(items[1]["list"], ["}", "{", ","])
            finally:
                path.unlink()

    def test_gzipped_input(self):
        path = write_fixture('[{"id": 1}, {"id": 2}]', gzipped=True)
        try:
            for chunk_size in (5, 1 << 20):
                items = list(
                    iter_json_array(path, gzipped=True, chunk_size=chunk_size)
                )
                self.assertEqual(items, [{"id": 1}, {"id": 2}])
        finally:
            path.unlink()

    def test_empty_array(self):
        for content in ("[]", "  [ \n\t]  \n"):
            path = write_fixture(content)
            try:
                self.assertEqual(list(iter_json_array(path)), [])
            finally:
                path.unlink()

    def test_many_objects_with_tiny_chunks(self):
        expected = [{"id": i, "name": f"city-{i}"} for i in range(3000)]
        content = "[" + ",".join(
            f'{{"id": {i}, "name": "city-{i}"}}' for i in range(3000)
        ) + "]"
        path = write_fixture(content)
        try:
            items = list(iter_json_array(path, chunk_size=13))
            self.assertEqual(items, expected)
        finally:
            path.unlink()

    def test_malformed_inputs_raise_value_error(self):
        cases = [
            '{"a": 1}',  # not an array
            "",  # empty file
            '[{"a": 1}',  # truncated array
            '[{"a": 1}, {"b": 2',  # truncated object
            '[{"a": }]',  # invalid object
            '[{"a": 1}] trailing',  # trailing garbage
            '[1, 2]',  # non-object elements
            '[{"a": 1},]',  # trailing comma is tolerated, then EOF ok
        ]
        for content in cases:
            path = write_fixture(content)
            try:
                with self.subTest(content=content):
                    if content.endswith(",]"):
                        self.assertEqual(
                            list(iter_json_array(path)), [{"a": 1}]
                        )
                    else:
                        with self.assertRaises(ValueError):
                            list(iter_json_array(path))
            finally:
                path.unlink()

    def test_error_reports_object_index(self):
        path = write_fixture('[{"ok": 1}, {"bad": }]')
        try:
            with self.assertRaises(ValueError) as ctx:
                list(iter_json_array(path))
            self.assertIn("#1", str(ctx.exception))
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()

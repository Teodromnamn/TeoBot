"""Regression checks; no camera or Tesseract DLL initialization required."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from test_obs_tesseract import parse_reading
from test_obs_pipeline import publish


class ReadingsTests(unittest.TestCase):
    def parse(self, text):
        return parse_reading(SimpleNamespace(txts=[text], scores=[.9]))['value']

    def test_suffix_is_irrelevant(self):
        for text in ('85/85', '85/85(0/', '85/85(anything)', '85/85 (294 XP'):
            self.assertEqual(self.parse(text)['current'], 85)

    def test_maximum_can_grow(self):
        value = self.parse('10200/10200')
        self.assertEqual(value['maximum'], 10200)

    def test_no_search_for_unrelated_numbers(self):
        for text in (')294', 'XP 85/85', '85/', '90/85', '0/0', '85/85 XP', '(0/0)'):
            self.assertIsNone(self.parse(text))

    def test_independent_resources_and_expiry(self):
        value = self.parse('85/85')
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'latest.json'
            publish(path, 'BRAK_ODCZYTU', [{'value': None}, {'value': value}],
                    100, 250, ['unreadable', 'ok'])
            data = json.loads(path.read_text())
            self.assertIsNone(data['hp'])
            self.assertEqual(data['mp']['current'], 85)
            self.assertFalse(data['valid'])
            saved = data['resources']['mp']['last_known']
            publish(path, 'BRAK_KLATEK')
            data = json.loads(path.read_text())
            self.assertIsNone(data['mp'])
            self.assertEqual(data['resources']['mp']['quality'], 'stale')
            self.assertEqual(data['resources']['mp']['last_known'], saved)

    def test_old_and_pending_are_not_current(self):
        value = self.parse('85/85')
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'latest.json'
            for status, age, guards in (
                ('WYNIK_ZBYT_STARY', 300, ['ok', 'ok']),
                ('POTWIERDZANIE_MAKSIMUM', 100, ['maximum_pending', 'ok']),
            ):
                publish(path, status, [{'value': value}, {'value': value}], age, 250, guards)
                self.assertIsNone(json.loads(path.read_text())['hp'])


if __name__ == '__main__':
    unittest.main()

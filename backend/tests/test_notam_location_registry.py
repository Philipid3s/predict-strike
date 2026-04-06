from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.config.notam_location_registry import resolve_notam_location_context  # noqa: E402


class NotamLocationRegistryTests(unittest.TestCase):
    def test_resolves_exact_location_context(self) -> None:
        icao_code, fir_name, country_name = resolve_notam_location_context("KZLC")

        self.assertEqual(icao_code, "KZLC")
        self.assertEqual(fir_name, "Salt Lake City ARTCC / FIR")
        self.assertEqual(country_name, "United States")

    def test_resolves_prefix_location_context(self) -> None:
        icao_code, fir_name, country_name = resolve_notam_location_context("ZBAA")

        self.assertEqual(icao_code, "ZBAA")
        self.assertEqual(fir_name, "Chinese FIR system")
        self.assertEqual(country_name, "China")

    def test_returns_unknown_for_unmapped_location(self) -> None:
        icao_code, fir_name, country_name = resolve_notam_location_context("XXXX")

        self.assertEqual(icao_code, "XXXX")
        self.assertIsNone(fir_name)
        self.assertIsNone(country_name)


if __name__ == "__main__":
    unittest.main()

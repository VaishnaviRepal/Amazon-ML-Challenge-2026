import unittest

import pandas as pd

from src.common.normalize import (
    normalize_business_address,
    normalize_business_addresses,
    normalize_business_name,
    normalize_business_names,
    normalize_country,
    normalize_countries,
)


class NormalizeScalarTests(unittest.TestCase):
    def test_representative_business_name(self):
        self.assertEqual(normalize_business_name("Orelee's Barbershop"), "orelees barbershop")

    def test_name_punctuation_and_ampersand(self):
        self.assertEqual(normalize_business_name("  A&B  Co., Ltd.  "), "a&b co ltd")

    def test_unicode_name_is_casefolded(self):
        self.assertEqual(normalize_business_name("  Café   Élan  "), "café élan")

    def test_representative_address_preserves_numbers(self):
        self.assertEqual(
            normalize_business_address("1795 Westchester Drive, High Point, NC"),
            "1795 westchester drive high point nc",
        )

    def test_address_separators_do_not_drop_tokens(self):
        self.assertEqual(
            normalize_business_address("KH NO. -570/13, NEW DELHI"),
            "kh no 570 13 new delhi",
        )

    def test_country(self):
        self.assertEqual(normalize_country("  India  "), "india")

    def test_missing_values_are_empty(self):
        self.assertEqual(normalize_business_name(None), "")
        self.assertEqual(normalize_business_address("   "), "")
        self.assertEqual(normalize_country(float("nan")), "")


class NormalizeVectorizedTests(unittest.TestCase):
    def test_vectorized_name_normalization(self):
        values = pd.Series(["Orelee's Barbershop", None, "  A&B  Co. "])
        self.assertEqual(normalize_business_names(values).tolist(), ["orelees barbershop", "", "a&b co"])

    def test_vectorized_address_and_country_normalization(self):
        addresses = pd.Series(["1795 Westchester Drive, High Point, NC", ""])
        countries = pd.Series(["US", None])
        self.assertEqual(normalize_business_addresses(addresses).tolist(), ["1795 westchester drive high point nc", ""])
        self.assertEqual(normalize_countries(countries).tolist(), ["us", ""])


if __name__ == "__main__":
    unittest.main()

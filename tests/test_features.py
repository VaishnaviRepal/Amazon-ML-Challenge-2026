import unittest

from src.vaishnavi.feature_schema import FEATURE_NAMES
from src.vaishnavi.features import compute_pair_features


SOURCE1 = {
    "entity_id": "S1-925783039",
    "business_name": "Orelee's Barbershop",
    "business_address": "1795 Westchester Drive, High Point, NC",
    "country": "US",
}

S2 = {
    "entity_id": "S2-166376419",
    "business_name": "Orelee's Barbershop",
    "business_address": "1795 Westchester Drive, High Point, NC",
    "country": "US",
}

S3 = {
    "entity_id": "S3-202863386",
    "business_name": "Wilford-Hancock.com",
    "business_address": "Mack Rd, Haltom City, Texas",
    "country": "US",
}


class FeatureTests(unittest.TestCase):
    def test_contract_and_exact_match_features(self):
        features = compute_pair_features(SOURCE1, S2)
        self.assertEqual(tuple(features), FEATURE_NAMES)
        self.assertEqual(set(features), set(FEATURE_NAMES))
        self.assertEqual(features["name_exact_match"], 1.0)
        self.assertEqual(features["address_similarity"], 1.0)
        self.assertEqual(features["country_exact_match"], 1.0)
        self.assertTrue(all(isinstance(value, float) for value in features.values()))

    def test_s3_candidate_is_supported(self):
        features = compute_pair_features(SOURCE1, S3)
        self.assertEqual(features["country_exact_match"], 1.0)
        self.assertLess(features["name_exact_match"], 1.0)
        self.assertGreaterEqual(features["name_similarity"], 0.0)
        self.assertLessEqual(features["name_similarity"], 1.0)

    def test_missing_values_are_not_matches(self):
        candidate = {**S2, "business_name": None, "business_address": "", "country": None}
        features = compute_pair_features(SOURCE1, candidate)
        self.assertEqual(features["name_exact_match"], 0.0)
        self.assertEqual(features["name_similarity"], 0.0)
        self.assertEqual(features["name_candidate_missing"], 1.0)
        self.assertEqual(features["address_candidate_missing"], 1.0)
        self.assertEqual(features["country_candidate_missing"], 1.0)

    def test_invalid_candidate_source_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_pair_features(SOURCE1, {**S2, "entity_id": "S1-123"})

    def test_required_columns_are_checked(self):
        with self.assertRaises(ValueError):
            compute_pair_features(SOURCE1, {"entity_id": "S2-1"})


if __name__ == "__main__":
    unittest.main()

"""Stable feature contract for Source-1 to Source-2/Source-3 matching."""

FEATURE_NAMES = (
    "name_exact_match",
    "name_similarity",
    "name_token_similarity",
    "name_character_similarity",
    "name_source1_missing",
    "name_candidate_missing",
    "address_similarity",
    "address_token_similarity",
    "address_source1_missing",
    "address_candidate_missing",
    "country_exact_match",
    "country_source1_missing",
    "country_candidate_missing",
)

FEATURE_DESCRIPTIONS = {
    "name_exact_match": "1 when normalized non-empty business names are equal, otherwise 0.",
    "name_similarity": "Normalized business-name edit similarity in [0, 1].",
    "name_token_similarity": "Token-sorted normalized business-name similarity in [0, 1].",
    "name_character_similarity": "Character-sequence similarity for normalized business names in [0, 1].",
    "name_source1_missing": "1 when Source-1 business_name is missing, otherwise 0.",
    "name_candidate_missing": "1 when candidate business_name is missing, otherwise 0.",
    "address_similarity": "Normalized address edit similarity in [0, 1].",
    "address_token_similarity": "Token-sorted normalized address similarity in [0, 1].",
    "address_source1_missing": "1 when Source-1 business_address is missing, otherwise 0.",
    "address_candidate_missing": "1 when candidate business_address is missing, otherwise 0.",
    "country_exact_match": "1 when normalized non-empty countries are equal, otherwise 0.",
    "country_source1_missing": "1 when Source-1 country is missing, otherwise 0.",
    "country_candidate_missing": "1 when candidate country is missing, otherwise 0.",
}

assert tuple(FEATURE_DESCRIPTIONS) == FEATURE_NAMES

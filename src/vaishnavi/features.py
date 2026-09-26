"""Pairwise numerical features for entity matching.

The input records use the columns in ``src.common.data_schema.SOURCE_COLUMNS``.
No ground-truth data is consulted. The optional RapidFuzz backend is preferred;
the standard-library fallback keeps the same deterministic feature semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any

from src.common.normalize import (
    normalize_business_address,
    normalize_business_name,
    normalize_country,
)
from src.vaishnavi.feature_schema import FEATURE_NAMES

try:  # RapidFuzz is substantially faster for large candidate sets.
    from rapidfuzz import fuzz as _fuzz
except ImportError:  # pragma: no cover - exercised when RapidFuzz is unavailable.
    _fuzz = None


SOURCE_RECORD_FIELDS = ("entity_id", "business_name", "business_address", "country")


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if _fuzz is not None:
        return float(_fuzz.ratio(left, right)) / 100.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _token_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_tokens = " ".join(sorted(left.split()))
    right_tokens = " ".join(sorted(right.split()))
    if _fuzz is not None:
        return float(_fuzz.ratio(left_tokens, right_tokens)) / 100.0
    return SequenceMatcher(None, left_tokens, right_tokens, autojunk=False).ratio()


def _record_value(record: Mapping[str, Any], field: str) -> Any:
    # Mapping.get keeps missing optional values safe without mutating records.
    return record.get(field)


def _validate_records(source1: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    missing_source1 = set(SOURCE_RECORD_FIELDS) - set(source1)
    missing_candidate = set(SOURCE_RECORD_FIELDS) - set(candidate)
    if missing_source1:
        raise ValueError(f"Source-1 record is missing columns: {', '.join(sorted(missing_source1))}")
    if missing_candidate:
        raise ValueError(f"Candidate record is missing columns: {', '.join(sorted(missing_candidate))}")
    candidate_id = str(candidate["entity_id"] or "")
    if not (candidate_id.startswith("S2-") or candidate_id.startswith("S3-")):
        raise ValueError("Candidate entity_id must be an S2-* or S3-* ID")


def compute_pair_features(source1: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, float]:
    """Return stable numeric features for one Source-1/candidate pair.

    Missing values produce a zero comparison score plus explicit missingness
    indicators; missing values are never treated as exact matches.
    """
    _validate_records(source1, candidate)
    source1_name = normalize_business_name(_record_value(source1, "business_name"))
    candidate_name = normalize_business_name(_record_value(candidate, "business_name"))
    source1_address = normalize_business_address(_record_value(source1, "business_address"))
    candidate_address = normalize_business_address(_record_value(candidate, "business_address"))
    source1_country = normalize_country(_record_value(source1, "country"))
    candidate_country = normalize_country(_record_value(candidate, "country"))

    features = {
        "name_exact_match": float(bool(source1_name and candidate_name and source1_name == candidate_name)),
        "name_similarity": _similarity(source1_name, candidate_name),
        "name_token_similarity": _token_similarity(source1_name, candidate_name),
        "name_character_similarity": _similarity(source1_name, candidate_name),
        "name_source1_missing": float(not source1_name),
        "name_candidate_missing": float(not candidate_name),
        "address_similarity": _similarity(source1_address, candidate_address),
        "address_token_similarity": _token_similarity(source1_address, candidate_address),
        "address_source1_missing": float(not source1_address),
        "address_candidate_missing": float(not candidate_address),
        "country_exact_match": float(bool(source1_country and candidate_country and source1_country == candidate_country)),
        "country_source1_missing": float(not source1_country),
        "country_candidate_missing": float(not candidate_country),
    }
    # Protect the public contract from accidental insertion/reordering.
    return {name: float(features[name]) for name in FEATURE_NAMES}


__all__ = ["compute_pair_features", "FEATURE_NAMES"]

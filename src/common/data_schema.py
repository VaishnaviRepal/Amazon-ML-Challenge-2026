"""Reusable schema and path configuration for the entity-resolution datasets.

This module contains no I/O, modelling, blocking, or matching logic.
"""

from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
TRAIN_DIR = DATA_DIR / "train"
TEST_DIR = DATA_DIR / "test"

TSV_SEPARATOR = "\t"
TEXT_ENCODING = "utf-8"

SOURCE_COLUMNS = (
    "entity_id",
    "business_name",
    "business_address",
    "country",
)
GROUND_TRUTH_COLUMNS = (
    "source1_entity_id",
    "matched_entity_ids",
)

TRAIN_SOURCE_PATHS = {
    "source1": TRAIN_DIR / "train_source1.tsv",
    "source2": TRAIN_DIR / "train_source2.tsv",
    "source3": TRAIN_DIR / "train_source3.tsv",
}
TEST_SOURCE_PATHS = {
    "source1": TEST_DIR / "test_source1.tsv",
    "source2": TEST_DIR / "test_source2.tsv",
    "source3": TEST_DIR / "test_source3.tsv",
}
TRAIN_GROUND_TRUTH_PATH = TRAIN_DIR / "train_ground_truth.tsv"

SOURCE_ID_PREFIXES = {
    "source1": "S1",
    "source2": "S2",
    "source3": "S3",
}
ENTITY_ID_PATTERN = re.compile(r"^S[123]-\d+$")
SOURCE1_ID_PATTERN = re.compile(r"^S1-\d+$")
MATCHED_ENTITY_ID_PATTERN = re.compile(r"^S[23]-\d+$")
MATCH_LIST_SEPARATOR = ","

# Observed source fields that can be empty in the supplied TSVs.
OPTIONAL_SOURCE_COLUMNS = frozenset({"business_address"})

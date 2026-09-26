"""Build leakage-safe labelled pairs for the entity matching model.

The source TSVs are indexed in a temporary SQLite database so the multi-million
row files are never loaded into Python memory. Ground truth is used only to
create the target label and to exclude known positives from sampled negatives;
it is never passed to the feature engine.
"""

from __future__ import annotations

import argparse
import csv
import logging
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from typing import Iterable

from src.common.data_schema import (
    GROUND_TRUTH_COLUMNS,
    SOURCE_COLUMNS,
    TEST_SOURCE_PATHS,
    TRAIN_GROUND_TRUTH_PATH,
    TRAIN_SOURCE_PATHS,
    TSV_SEPARATOR,
)
from src.common.normalize import normalize_business_name, normalize_country
from src.vaishnavi.feature_schema import FEATURE_NAMES
from src.vaishnavi.features import compute_pair_features


INDEX_COLUMNS = SOURCE_COLUMNS + ("source_type", "name_prefix", "country_norm")
OUTPUT_COLUMNS = ("source1_entity_id", "candidate_entity_id", "source_type", *FEATURE_NAMES, "target")

LOGGER = logging.getLogger(__name__)

MISSING_FEATURES = (
    'name_source1_missing',
    'name_candidate_missing',
    'address_source1_missing',
    'address_candidate_missing',
    'country_source1_missing',
    'country_candidate_missing',
)


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle, delimiter=TSV_SEPARATOR), None)
    if header is None:
        raise ValueError(f"{path} is empty")
    return header


def _validate_source_header(path: Path) -> None:
    header = _read_header(path)
    if header != list(SOURCE_COLUMNS):
        raise ValueError(f"{path} has schema {header!r}; expected {list(SOURCE_COLUMNS)!r}")


def _name_prefix(value: str) -> str:
    return "".join(normalize_business_name(value).split())[:3]


def _country_key(value: str) -> str:
    return normalize_country(value)


def _create_index(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY,
            business_name TEXT NOT NULL,
            business_address TEXT NOT NULL,
            country TEXT NOT NULL,
            source_type TEXT NOT NULL,
            name_prefix TEXT NOT NULL,
            country_norm TEXT NOT NULL
        );
        CREATE INDEX entities_country_prefix ON entities(source_type, country_norm, name_prefix, entity_id);
        CREATE INDEX entities_country ON entities(source_type, country_norm, entity_id);
        CREATE TABLE seen_ground_truth (source1_entity_id TEXT PRIMARY KEY);
        """
    )


def _index_source(connection: sqlite3.Connection, path: Path, source_type: str) -> int:
    _validate_source_header(path)
    insert_sql = """
        INSERT INTO entities(entity_id, business_name, business_address, country,
                             source_type, name_prefix, country_norm)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    count = 0
    batch = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=TSV_SEPARATOR)
        for row in reader:
            entity_id = row["entity_id"]
            if not entity_id.startswith(f"{source_type}-"):
                raise ValueError(f"Unexpected {source_type} ID {entity_id!r} in {path}")
            business_name = row.get("business_name") or ""
            business_address = row.get("business_address") or ""
            country = row.get("country") or ""
            batch.append((entity_id, business_name, business_address, country, source_type, _name_prefix(business_name), _country_key(country)))
            count += 1
            if len(batch) >= 10_000:
                connection.executemany(insert_sql, batch)
                connection.commit()
                batch.clear()
    if batch:
        connection.executemany(insert_sql, batch)
        connection.commit()
    return count


def inspect_ground_truth(path: Path) -> dict[str, int]:
    """Validate and summarize the actual ground-truth representation."""
    if _read_header(path) != list(GROUND_TRUTH_COLUMNS):
        raise ValueError(f"{path} must contain exactly {list(GROUND_TRUTH_COLUMNS)!r}")
    rows = empty_lists = links = 0
    source2_links = source3_links = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=TSV_SEPARATOR)
        for row in reader:
            source_id = row["source1_entity_id"]
            if not source_id.startswith("S1-"):
                raise ValueError(f"Invalid ground-truth Source-1 ID: {source_id}")
            values = [value.strip() for value in row["matched_entity_ids"].split(",") if value.strip()]
            if not values:
                empty_lists += 1
            for candidate_id in values:
                if not (candidate_id.startswith("S2-") or candidate_id.startswith("S3-")):
                    raise ValueError(f"Invalid ground-truth candidate ID: {candidate_id}")
                links += 1
                source2_links += candidate_id.startswith("S2-")
                source3_links += candidate_id.startswith("S3-")
            rows += 1
    return {"ground_truth_rows": rows, "empty_match_lists": empty_lists, "labelled_links": links, "s2_links": source2_links, "s3_links": source3_links}


def _candidate_rows(connection: sqlite3.Connection, country: str, prefix: str, excluded: set[str], limit: int):
    if limit <= 0:
        return []
    placeholders = ",".join("?" for _ in excluded)
    exclusion = f"AND entity_id NOT IN ({placeholders})" if excluded else ""
    base = ["S2", "S3", country, prefix, *sorted(excluded)]
    sql = f"""
        SELECT entity_id, business_name, business_address, country, source_type
        FROM entities
        WHERE source_type IN (?, ?) AND country_norm = ? AND name_prefix = ? {exclusion}
        ORDER BY entity_id LIMIT ?
    """
    rows = connection.execute(sql, (*base, limit)).fetchall()
    if len(rows) < limit:
        already = {row[0] for row in rows}
        excluded_for_fallback = excluded | already
        placeholders = ",".join("?" for _ in excluded_for_fallback)
        exclusion = f"AND entity_id NOT IN ({placeholders})" if excluded_for_fallback else ""
        sql = f"""
            SELECT entity_id, business_name, business_address, country, source_type
            FROM entities
            WHERE source_type IN (?, ?) AND country_norm = ? {exclusion}
            ORDER BY entity_id LIMIT ?
        """
        params = ["S2", "S3", country, *sorted(excluded_for_fallback), limit - len(rows)]
        rows.extend(connection.execute(sql, params).fetchall())
    return rows


def _write_pair(writer, source1: dict[str, str], candidate: dict[str, str], target: int, counters: Counter) -> None:
    features = compute_pair_features(source1, candidate)
    writer.writerow({"source1_entity_id": source1["entity_id"], "candidate_entity_id": candidate["entity_id"], "source_type": candidate["source_type"], **features, "target": target})
    counters["positive" if target else "negative"] += 1
    for feature in MISSING_FEATURES:
        counters[f"missing_{feature}"] += int(features[feature])



def _summary(counters: Counter) -> dict:
    total_pairs = counters["positive"] + counters["negative"]
    result = dict(counters)
    result["features"] = len(FEATURE_NAMES)
    result["total_pairs"] = total_pairs
    result["positive_negative_ratio"] = counters["positive"] / counters["negative"] if counters["negative"] else None
    result["missing_value_statistics"] = {feature: {"count": counters[f"missing_{feature}"], "rate": counters[f"missing_{feature}"] / total_pairs if total_pairs else 0.0} for feature in MISSING_FEATURES}
    return result
def build_training_data(train_sources: dict[str, Path], ground_truth: Path, output_dir: Path, negative_ratio: float = 1.0) -> dict:
    """Build a TSV of positives and plausible, deterministic negatives."""
    if negative_ratio <= 0:
        raise ValueError("negative_ratio must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    gt_summary = inspect_ground_truth(ground_truth)
    output_path = output_dir / "training_pairs.tsv"
    counters = Counter()
    with tempfile.TemporaryDirectory(prefix="matching_index_", dir=output_dir) as temporary:
        connection = sqlite3.connect(Path(temporary) / "entities.sqlite")
        _create_index(connection)
        indexed = {source: _index_source(connection, path, f"S{source[-1]}") for source, path in train_sources.items()}
        with ground_truth.open("r", encoding="utf-8-sig", newline="") as gt_handle, output_path.open("w", encoding="utf-8", newline="") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=OUTPUT_COLUMNS, delimiter=TSV_SEPARATOR, lineterminator="\n")
            writer.writeheader()
            reader = csv.DictReader(gt_handle, delimiter=TSV_SEPARATOR)
            for row_number, row in enumerate(reader, start=1):
                source1_row = connection.execute("SELECT entity_id, business_name, business_address, country, source_type FROM entities WHERE entity_id = ?", (row["source1_entity_id"],)).fetchone()
                if source1_row is None:
                    raise ValueError(f"Ground-truth Source-1 ID not found in train_source1.tsv: {row['source1_entity_id']}")
                source1 = dict(zip(("entity_id", "business_name", "business_address", "country", "source_type"), source1_row))
                positive_ids = {value.strip() for value in row["matched_entity_ids"].split(",") if value.strip()}
                for candidate_id in sorted(positive_ids):
                    candidate_row = connection.execute("SELECT entity_id, business_name, business_address, country, source_type FROM entities WHERE entity_id = ?", (candidate_id,)).fetchone()
                    if candidate_row is None:
                        raise ValueError(f"Ground-truth candidate ID not found in indexed sources: {candidate_id}")
                    _write_pair(writer, source1, dict(zip(("entity_id", "business_name", "business_address", "country", "source_type"), candidate_row)), 1, counters)
                negative_count = max(1, round(len(positive_ids) * negative_ratio))
                prefix, country = _name_prefix(source1["business_name"]), _country_key(source1["country"])
                negative_rows = _candidate_rows(connection, country, prefix, positive_ids, negative_count)
                counters["negative_candidates_unavailable"] += max(0, negative_count - len(negative_rows))
                for candidate_row in negative_rows:
                    _write_pair(writer, source1, dict(zip(("entity_id", "business_name", "business_address", "country", "source_type"), candidate_row)), 0, counters)
                counters["source1_entities_processed"] += 1
                if row_number % 100_000 == 0:
                    output_handle.flush()
        connection.close()
    counters["indexed_source_rows"] = sum(indexed.values())
    counters.update({f"ground_truth_{key}": value for key, value in gt_summary.items()})
    # Only supplied training files are indexed; test records and labels are never used.
    counters["test_source_files_read"] = 0
    counters["ground_truth_used_as_feature"] = 0
    summary = _summary(counters)
    log_path = output_dir / "training_data.log"
    log_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %s: positives=%d negatives=%d ratio=%.4f features=%d missing=%s", output_path, summary["positive"], summary["negative"], summary["positive_negative_ratio"] or 0.0, summary["features"], summary["missing_value_statistics"])
    return {"output_path": str(output_path), **summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build labelled matching pairs from train TSVs.")
    parser.add_argument("--train-source1", type=Path, default=TRAIN_SOURCE_PATHS["source1"])
    parser.add_argument("--train-source2", type=Path, default=TRAIN_SOURCE_PATHS["source2"])
    parser.add_argument("--train-source3", type=Path, default=TRAIN_SOURCE_PATHS["source3"])
    parser.add_argument("--ground-truth", type=Path, default=TRAIN_GROUND_TRUTH_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/training_features"))
    parser.add_argument("--negative-ratio", type=float, default=1.0)
    args = parser.parse_args()
    summary = build_training_data({"source1": args.train_source1, "source2": args.train_source2, "source3": args.train_source3}, args.ground_truth, args.output_dir, args.negative_ratio)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Deterministic, disk-backed candidate generation for entity resolution.

The module creates only Source-1-to-Source-2/Source-3 candidate pairs.  It
does not use labels, a matcher model, probabilities, or a final threshold.
Candidate records are indexed in SQLite rather than held in Python memory.

Output contract (UTF-8 TSV): ``source1_entity_id``, ``candidate_entity_id``,
``source_type``.  A Source-1 row with no candidates is represented by one row
with empty ``candidate_entity_id`` and ``source_type``; this preserves coverage
without inventing an ID.  All non-empty candidates are valid S2/S3 IDs.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import tempfile
from collections.abc import Iterable
from pathlib import Path

from src.common.data_schema import SOURCE_COLUMNS, TEST_SOURCE_PATHS, TSV_SEPARATOR
from src.common.normalize import normalize_business_address, normalize_business_name, normalize_country


OUTPUT_COLUMNS = ("source1_entity_id", "candidate_entity_id", "source_type")
EXACT_RULES = frozenset({"country_name_exact", "country_name_token_signature", "country_address_exact"})
POSTING_CAPS = {
    "country_name_token_prefix4": 100,
    "country_address_number": 100,
    "country_name_prefix4": 100,
}
LOW_INFORMATION_NAME_TOKENS = frozenset({
    "and", "co", "company", "corp", "corporation", "enterprise", "enterprises",
    "group", "inc", "international", "limited", "llc", "ltd", "of", "private",
    "pvt", "service", "services", "the",
})


def _keys(record: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """Create deterministic normalized blocking keys from source attributes."""
    country = normalize_country(record.get("country"))
    name = normalize_business_name(record.get("business_name"))
    address = normalize_business_address(record.get("business_address"))
    if not country:
        return {rule: () for rule in (*EXACT_RULES, *POSTING_CAPS)}
    compact_name = "".join(name.split())
    signature = " ".join(sorted(name.split()))
    token_prefixes = tuple(sorted({token[:4] for token in name.split() if len(token) >= 4 and token not in LOW_INFORMATION_NAME_TOKENS}))
    number_tokens = tuple(sorted({token for token in address.split() if token.isdigit() and len(token) >= 3}))
    return {
        "country_name_exact": (f"{country}\x1f{name}",) if name else (),
        "country_name_token_signature": (f"{country}\x1f{signature}",) if signature else (),
        "country_address_exact": (f"{country}\x1f{address}",) if address else (),
        "country_name_token_prefix4": tuple(f"{country}\x1f{token}" for token in token_prefixes),
        "country_address_number": tuple(f"{country}\x1f{token}" for token in number_tokens),
        "country_name_prefix4": (f"{country}\x1f{compact_name[:4]}",) if len(compact_name) >= 4 else (),
    }


def _validate_header(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle, delimiter=TSV_SEPARATOR), None)
    if header != list(SOURCE_COLUMNS):
        raise ValueError(f"{path} has schema {header!r}; expected {list(SOURCE_COLUMNS)!r}")


def _create_index(connection: sqlite3.Connection) -> None:
    cursor = connection.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = FILE;
        CREATE TABLE candidate_keys (
            source_type TEXT NOT NULL,
            rule TEXT NOT NULL,
            block_key TEXT NOT NULL,
            candidate_entity_id TEXT NOT NULL,
            PRIMARY KEY(source_type, rule, block_key, candidate_entity_id)
        ) WITHOUT ROWID;
        CREATE INDEX candidate_keys_lookup
            ON candidate_keys(source_type, rule, block_key, candidate_entity_id);
        """
    )
    cursor.close()


def _index_candidate_source(connection: sqlite3.Connection, path: Path, source_type: str) -> tuple[int, int]:
    """Index one candidate source without retaining source records in memory."""
    _validate_header(path)
    insert = "INSERT OR IGNORE INTO candidate_keys VALUES (?, ?, ?, ?)"
    records = entries = 0
    batch: list[tuple[str, str, str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=TSV_SEPARATOR):
            candidate_id = row["entity_id"]
            if not candidate_id.startswith(f"{source_type}-"):
                raise ValueError(f"Unexpected {source_type} candidate ID {candidate_id!r} in {path}")
            records += 1
            for rule, keys in _keys(row).items():
                for key in keys:
                    batch.append((source_type, rule, key, candidate_id))
                    entries += 1
            if len(batch) >= 50_000:
                cursor = connection.executemany(insert, batch)
                try:
                    connection.commit()
                finally:
                    cursor.close()
                batch.clear()
    if batch:
        cursor = connection.executemany(insert, batch)
        try:
            connection.commit()
        finally:
            cursor.close()
    return records, entries


def _lookup_candidates(connection: sqlite3.Connection, source_type: str, record: dict[str, str]) -> set[str]:
    """Retrieve exact-key candidates and bounded frequency-aware fallback keys."""
    candidates: set[str] = set()
    for rule, keys in _keys(record).items():
        cap = None if rule in EXACT_RULES else POSTING_CAPS[rule]
        for key in keys:
            sql = "SELECT candidate_entity_id FROM candidate_keys WHERE source_type = ? AND rule = ? AND block_key = ? ORDER BY candidate_entity_id"
            cursor = connection.execute(
                sql + " LIMIT ?" if cap is not None else sql,
                (source_type, rule, key, cap + 1) if cap is not None else (source_type, rule, key),
            )
            try:
                rows = cursor.fetchall()
            finally:
                cursor.close()
            if cap is not None and len(rows) > cap:
                continue
            candidates.update(row[0] for row in rows)
    return candidates


def _candidate_rows(connection: sqlite3.Connection, source1_path: Path) -> Iterable[tuple[str, str, str]]:
    _validate_header(source1_path)
    with source1_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=TSV_SEPARATOR):
            source1_id = record["entity_id"]
            if not source1_id.startswith("S1-"):
                raise ValueError(f"Unexpected Source-1 ID {source1_id!r} in {source1_path}")
            candidate_ids = _lookup_candidates(connection, "S2", record) | _lookup_candidates(connection, "S3", record)
            if not candidate_ids:
                yield source1_id, "", ""
                continue
            for candidate_id in sorted(candidate_ids):
                yield source1_id, candidate_id, candidate_id.split("-", 1)[0]


def build_candidate_pairs(
    source1_path: Path,
    source2_path: Path,
    source3_path: Path,
    output_path: Path,
    work_dir: Path | None = None,
) -> dict[str, int]:
    """Build a deterministic candidate TSV from three source TSVs.

    ``work_dir`` may point to a disk with adequate temporary capacity. The
    temporary SQLite index is removed on successful or failed completion.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = work_dir if work_dir is not None else output_path.parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    counters = {"source1_entities": 0, "candidate_pairs": 0, "source1_zero_candidate_rows": 0, "source2_records": 0, "source3_records": 0, "index_key_entries": 0}
    with tempfile.TemporaryDirectory(prefix="blocking_index_", dir=temporary_parent) as temporary:
        connection = sqlite3.connect(Path(temporary) / "candidate_index.sqlite")
        try:
            _create_index(connection)
            for source_type, path, count_key in (("S2", source2_path, "source2_records"), ("S3", source3_path, "source3_records")):
                records, entries = _index_candidate_source(connection, path, source_type)
                counters[count_key] = records
                counters["index_key_entries"] += entries
            with output_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=TSV_SEPARATOR, lineterminator="\n")
                writer.writerow(OUTPUT_COLUMNS)
                for row in _candidate_rows(connection, source1_path):
                    counters["source1_entities"] += row[1] == "" or row[0] != "" and row[1].startswith("S2-")
                    # Count entities exactly once: S2 is emitted before S3 under lexical ID order;
                    # blank rows cover the zero-candidate case.
                    if row[1] == "":
                        counters["source1_zero_candidate_rows"] += 1
                    counters["candidate_pairs"] += bool(row[1])
                    writer.writerow(row)
        finally:
            connection.close()
    # source1_entities is derived more reliably from the file itself because a
    # source can have only S3 candidates. This pass is streaming and cheap.
    with source1_path.open("r", encoding="utf-8-sig", newline="") as handle:
        counters["source1_entities"] = sum(1 for _ in csv.DictReader(handle, delimiter=TSV_SEPARATOR))
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic Source-1 to Source-2/Source-3 candidate pairs.")
    parser.add_argument("--source1", type=Path, default=TEST_SOURCE_PATHS["source1"])
    parser.add_argument("--source2", type=Path, default=TEST_SOURCE_PATHS["source2"])
    parser.add_argument("--source3", type=Path, default=TEST_SOURCE_PATHS["source3"])
    parser.add_argument("--output", type=Path, default=Path("outputs/candidate_pairs.tsv"))
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--write-output", action="store_true", help="Required acknowledgement before creating a full candidate-pairs file.")
    args = parser.parse_args()
    if not args.write_output:
        parser.error("Refusing to create candidate_pairs.tsv without --write-output; run Phase-5 validation first for full test generation.")
    print(build_candidate_pairs(args.source1, args.source2, args.source3, args.output, args.work_dir))


if __name__ == "__main__":
    main()

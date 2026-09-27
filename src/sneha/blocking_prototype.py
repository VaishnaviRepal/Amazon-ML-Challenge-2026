"""Deterministic, bounded blocking prototype for Phase 2 design evaluation.

This module deliberately evaluates only training data.  It selects a stable
subset of Source-1 ground-truth rows, creates multiple normalized blocking
keys, streams Source-2 and Source-3 once, and measures link retrieval recall.
It does not train a model, score candidate probabilities, or write test
``candidate_pairs.tsv``.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from src.common.data_schema import SOURCE_COLUMNS, TSV_SEPARATOR, TRAIN_GROUND_TRUTH_PATH, TRAIN_SOURCE_PATHS
from src.common.normalize import normalize_business_address, normalize_business_name, normalize_country


RULES = ("country_name_exact", "country_name_token_signature", "country_name_prefix4", "country_address_exact")


def _compact_name(value: str) -> str:
    return "".join(normalize_business_name(value).split())


def _token_signature(value: str) -> str:
    return " ".join(sorted(normalize_business_name(value).split()))


def blocking_keys(row: dict[str, str]) -> dict[str, str | None]:
    """Return compatible, deterministic keys; ``None`` is never indexed."""
    country = normalize_country(row.get("country"))
    name = normalize_business_name(row.get("business_name"))
    compact_name = "".join(name.split())
    signature = " ".join(sorted(name.split()))
    address = normalize_business_address(row.get("business_address"))
    return {
        "country_name_exact": f"{country}\x1f{name}" if country and name else None,
        "country_name_token_signature": f"{country}\x1f{signature}" if country and signature else None,
        "country_name_prefix4": f"{country}\x1f{compact_name[:4]}" if country and len(compact_name) >= 4 else None,
        "country_address_exact": f"{country}\x1f{address}" if country and address else None,
    }


def _validate_header(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle, delimiter=TSV_SEPARATOR), None)
    if header != list(SOURCE_COLUMNS):
        raise ValueError(f"{path} has schema {header!r}; expected {list(SOURCE_COLUMNS)!r}")


def select_ground_truth_subset(path: Path, modulus: int, remainder: int) -> dict[str, set[str]]:
    """Select Source-1 labels by numeric ID modulo, independent of file order."""
    if modulus <= 0 or not 0 <= remainder < modulus:
        raise ValueError("remainder must be in [0, modulus)")
    selected: dict[str, set[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=TSV_SEPARATOR)
        if reader.fieldnames != ["source1_entity_id", "matched_entity_ids"]:
            raise ValueError(f"Unexpected ground-truth schema: {reader.fieldnames!r}")
        for row in reader:
            source1_id = row["source1_entity_id"]
            if int(source1_id.split("-", 1)[1]) % modulus != remainder:
                continue
            selected[source1_id] = {value.strip() for value in row["matched_entity_ids"].split(",") if value.strip()}
    return selected


def load_source1_records(path: Path, wanted_ids: set[str]) -> dict[str, dict[str, str]]:
    """Stream Source-1 and retain records chosen by the ground-truth subset."""
    _validate_header(path)
    records: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=TSV_SEPARATOR):
            if row["entity_id"] in wanted_ids:
                records[row["entity_id"]] = row
    missing = wanted_ids - set(records)
    if missing:
        raise ValueError(f"{len(missing)} selected ground-truth IDs were not found in Source-1")
    return records


def build_requested_key_index(records: dict[str, dict[str, str]]) -> dict[str, dict[str, list[str]]]:
    """Map only needed keys to Source-1 IDs, bounding prototype memory."""
    index: dict[str, dict[str, list[str]]] = {rule: defaultdict(list) for rule in RULES}
    for source1_id, row in records.items():
        for rule, key in blocking_keys(row).items():
            if key is not None:
                index[rule][key].append(source1_id)
    return index


def stream_candidates(
    paths: Iterable[tuple[str, Path]],
    key_index: dict[str, dict[str, list[str]]],
    truth: dict[str, set[str]],
) -> tuple[dict[str, set[str]], Counter, Counter]:
    """Stream candidates once and collect only pairs matching requested keys."""
    candidates: dict[str, set[str]] = {source1_id: set() for source1_id in truth}
    rule_pair_counts: Counter = Counter()
    rule_link_hits: Counter = Counter()
    for source_type, path in paths:
        _validate_header(path)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, delimiter=TSV_SEPARATOR):
                candidate_id = row["entity_id"]
                if not candidate_id.startswith(f"{source_type}-"):
                    raise ValueError(f"Unexpected {source_type} ID {candidate_id!r} in {path}")
                for rule, key in blocking_keys(row).items():
                    if key is None:
                        continue
                    for source1_id in key_index[rule].get(key, ()):
                        rule_pair_counts[rule] += 1
                        if candidate_id in truth[source1_id]:
                            rule_link_hits[rule] += 1
                        candidates[source1_id].add(candidate_id)
    return candidates, rule_pair_counts, rule_link_hits


def run_prototype(modulus: int = 1000, remainder: int = 0) -> dict:
    """Run the bounded training-only experiment and return serialisable results."""
    truth = select_ground_truth_subset(TRAIN_GROUND_TRUTH_PATH, modulus, remainder)
    records = load_source1_records(TRAIN_SOURCE_PATHS["source1"], set(truth))
    key_index = build_requested_key_index(records)
    candidates, rule_pair_counts, rule_link_hits = stream_candidates(
        (("S2", TRAIN_SOURCE_PATHS["source2"]), ("S3", TRAIN_SOURCE_PATHS["source3"])), key_index, truth
    )
    total_links = sum(len(ids) for ids in truth.values())
    union_hits = sum(len(truth[source1_id] & candidate_ids) for source1_id, candidate_ids in candidates.items())
    candidate_counts = [len(ids) for ids in candidates.values()]
    source_counts = {"source1_entities": len(records), "with_zero_candidates": sum(count == 0 for count in candidate_counts)}
    return {
        "experiment": {
            "split": "training only; deterministic Source-1 numeric-ID modulo subset",
            "modulus": modulus,
            "remainder": remainder,
            "rules": list(RULES),
            "ground_truth_used_only_for": "post-generation candidate-recall measurement",
        },
        "source1": source_counts,
        "candidate_pairs": {
            "total_deduplicated_pairs": sum(candidate_counts),
            "average_per_source1": sum(candidate_counts) / len(candidate_counts) if candidate_counts else 0.0,
            "maximum_per_source1": max(candidate_counts, default=0),
        },
        "candidate_recall": {
            "true_links": total_links,
            "true_links_retrieved_by_union": union_hits,
            "union_recall": union_hits / total_links if total_links else 0.0,
            "per_rule_link_hits": {rule: int(rule_link_hits[rule]) for rule in RULES},
            "per_rule_recall": {rule: rule_link_hits[rule] / total_links if total_links else 0.0 for rule in RULES},
            "per_rule_generated_pairs_before_union_deduplication": {rule: int(rule_pair_counts[rule]) for rule in RULES},
        },
        "comparison_reduction": {
            "subset_cartesian_pairs": len(records) * (5_034_616 + 5_285_603),
            "reduction_factor": (len(records) * (5_034_616 + 5_285_603)) / sum(candidate_counts) if sum(candidate_counts) else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate deterministic blocking keys on a bounded train subset.")
    parser.add_argument("--modulus", type=int, default=1000)
    parser.add_argument("--remainder", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("experiments/sneha_blocking_subset_metrics.json"))
    args = parser.parse_args()
    result = run_prototype(args.modulus, args.remainder)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

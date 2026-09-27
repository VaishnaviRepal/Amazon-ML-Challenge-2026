import csv
import tempfile
import unittest
from pathlib import Path

from src.sneha.blocking import OUTPUT_COLUMNS, build_candidate_pairs


SOURCE_HEADER = ["entity_id", "business_name", "business_address", "country"]


def write_tsv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(SOURCE_HEADER)
        writer.writerows(rows)


class BlockingTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        source1, source2, source3 = (root / "s1.tsv", root / "s2.tsv", root / "s3.tsv")
        write_tsv(source1, [
            ["S1-1", "Alpha Cafe", "1 Main St", "US"],
            ["S1-2", "", "2 Main St", "US"],
            ["S1-3", "Bravo Shop", "", "US"],
            ["S1-4", "No Country", "4 Main St", ""],
        ])
        write_tsv(source2, [
            ["S2-1", "Alpha Cafe", "1 Main St", "US"],
            ["S2-2", "Alpha Cafe", "9 Other St", "US"],
            ["S2-3", "Different Name", "2 Main St", "US"],
            ["S2-4", "", "", "US"],
        ])
        write_tsv(source3, [
            ["S3-1", "Alpha Cafe", "1 Main St", "US"],
            ["S3-2", "Bravo Shop", "", "US"],
        ])
        return source1, source2, source3

    def _read_output(self, path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_generates_s2_s3_multiple_and_deduplicated_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source1, source2, source3 = self._fixture(root)
            output = root / "pairs.tsv"
            summary = build_candidate_pairs(source1, source2, source3, output)
            rows = self._read_output(output)
            self.assertEqual(tuple(rows[0]), OUTPUT_COLUMNS)
            by_source = {}
            for row in rows:
                by_source.setdefault(row["source1_entity_id"], []).append(row)
            self.assertEqual({row["candidate_entity_id"] for row in by_source["S1-1"]}, {"S2-1", "S2-2", "S3-1"})
            self.assertEqual({row["candidate_entity_id"] for row in by_source["S1-2"]}, {"S2-3"})
            self.assertEqual({row["candidate_entity_id"] for row in by_source["S1-3"]}, {"S3-2"})
            self.assertEqual(by_source["S1-4"], [{"source1_entity_id": "S1-4", "candidate_entity_id": "", "source_type": ""}])
            self.assertEqual(len(rows), len({(row["source1_entity_id"], row["candidate_entity_id"]) for row in rows}))
            self.assertEqual(summary["source1_entities"], 4)
            self.assertEqual(summary["source1_zero_candidate_rows"], 1)

    def test_missing_fields_and_repeated_execution_are_safe_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source1, source2, source3 = self._fixture(root)
            first, second = root / "first.tsv", root / "second.tsv"
            build_candidate_pairs(source1, source2, source3, first)
            build_candidate_pairs(source1, source2, source3, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            rows = self._read_output(first)
            self.assertIn("S2-3", {row["candidate_entity_id"] for row in rows if row["source1_entity_id"] == "S1-2"})
            self.assertIn("S3-2", {row["candidate_entity_id"] for row in rows if row["source1_entity_id"] == "S1-3"})

    def test_invalid_source_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source1, source2, source3 = self._fixture(root)
            write_tsv(source2, [["S1-99", "Wrong", "1 Main St", "US"]])
            with self.assertRaises(ValueError):
                build_candidate_pairs(source1, source2, source3, root / "out.tsv")
            source1, source2, source3 = self._fixture(root)
            write_tsv(source1, [["S9-1", "Wrong", "1 Main St", "US"]])
            with self.assertRaises(ValueError):
                build_candidate_pairs(source1, source2, source3, root / "out2.tsv")


if __name__ == "__main__":
    unittest.main()

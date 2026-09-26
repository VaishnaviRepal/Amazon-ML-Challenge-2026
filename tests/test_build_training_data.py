import csv
import tempfile
import unittest
from pathlib import Path

from src.vaishnavi.build_training_data import build_training_data


SOURCE_HEADER = ["entity_id", "business_name", "business_address", "country"]


def write_tsv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


class TrainingDataTests(unittest.TestCase):
    def test_builds_balanced_positive_and_plausible_negative_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source1 = root / "train_source1.tsv"
            source2 = root / "train_source2.tsv"
            source3 = root / "train_source3.tsv"
            ground_truth = root / "train_ground_truth.tsv"
            write_tsv(source1, SOURCE_HEADER, [["S1-1", "Alpha Cafe", "1 Main St", "US"], ["S1-2", "Beta Shop", "2 Main St", "US"]])
            write_tsv(source2, SOURCE_HEADER, [["S2-1", "Alpha Cafe", "1 Main St", "US"], ["S2-2", "Alpha Catering", "9 Main St", "US"], ["S2-3", "Other", "3 Main St", "GB"]])
            write_tsv(source3, SOURCE_HEADER, [["S3-1", "Beta Shop", "2 Main St", "US"], ["S3-2", "Beta Store", "8 Main St", "US"]])
            write_tsv(ground_truth, ["source1_entity_id", "matched_entity_ids"], [["S1-1", "S2-1"], ["S1-2", "S3-1"]])
            summary = build_training_data({"source1": source1, "source2": source2, "source3": source3}, ground_truth, root / "output")
            self.assertEqual(summary["positive"], 2)
            self.assertEqual(summary["negative"], 2)
            with (root / "output" / "training_pairs.tsv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(len(rows), 4)
            self.assertEqual(set(row["target"] for row in rows), {"0", "1"})
            self.assertEqual(set(row["source_type"] for row in rows), {"S2", "S3"})
            self.assertTrue(all(row["candidate_entity_id"] not in {"S2-1", "S3-1"} for row in rows if row["target"] == "0"))

    def test_ground_truth_schema_is_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source, source_id in (("source1", "S1-1"), ("source2", "S2-1"), ("source3", "S3-1")):
                write_tsv(root / f"{source}.tsv", SOURCE_HEADER, [[source_id, "Name", "Address", "US"]])
            ground_truth = root / "ground_truth.tsv"
            write_tsv(ground_truth, ["source1_entity_id", "wrong_column"], [["S1-1", "S2-1"]])
            with self.assertRaises(ValueError):
                build_training_data({"source1": root / "source1.tsv", "source2": root / "source2.tsv", "source3": root / "source3.tsv"}, ground_truth, root / "output")


if __name__ == "__main__":
    unittest.main()

"""Select an entity-matcher decision threshold using validation data only.

The validation partition is reconstructed with the same deterministic
``GroupShuffleSplit`` used for training: all candidates for one Source-1 entity
are held out together.  This script never opens test files or test ground
truth.  It evaluates both pair-level errors and the number of predicted
candidates per Source-1 entity, because a pair-level F1 score alone cannot
describe whether a threshold creates too many zero-match or multi-match cases.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from src.vaishnavi.feature_schema import FEATURE_NAMES
from src.vaishnavi.train_baseline import (
    DEFAULT_FEATURE_PATH,
    grouped_holdout,
    load_training_features,
    metrics_at_threshold,
)


DEFAULT_MODEL_PATH = Path("models/entity_matcher.joblib")
DEFAULT_OUTPUT_PATH = Path("experiments/threshold_analysis.csv")
DEFAULT_THRESHOLD_PATH = Path("models/threshold.json")


def entity_match_counts(predictions: np.ndarray, groups: np.ndarray) -> dict[str, int]:
    """Count validation Source-1 entities with zero, one, or many predictions."""
    match_counts = np.bincount(groups, weights=predictions, minlength=int(groups.max()) + 1)
    # Group labels are globally encoded, so only count group IDs present in this
    # validation partition (not unobserved IDs in the bincount array).
    validation_counts = match_counts[np.unique(groups)]
    return {
        "source1_entities_zero_matches": int((validation_counts == 0).sum()),
        "source1_entities_one_match": int((validation_counts == 1).sum()),
        "source1_entities_multiple_matches": int((validation_counts > 1).sum()),
    }


def analyse_thresholds(y_validation: np.ndarray, scores: np.ndarray, validation_groups: np.ndarray, thresholds: np.ndarray) -> list[dict[str, Any]]:
    """Return pair-level and Source-1-level validation outcomes per threshold."""
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        predictions = (scores >= threshold).astype(np.int8)
        row = metrics_at_threshold(y_validation, scores, float(threshold))
        row["number_predicted_matches"] = row.pop("predicted_positive")
        row.update(entity_match_counts(predictions, validation_groups))
        rows.append(row)
    return rows


def select_threshold(rows: list[dict[str, Any]], f1_tolerance: float = 0.001) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use validation F1, then precision and threshold, rather than a blind default.

    First retain thresholds within ``f1_tolerance`` of the best validation F1.
    Within that practically equivalent band, prefer greater precision (fewer
    false matches); use the higher threshold as the final deterministic tie
    breaker.  The policy is recorded with the selected row for review.
    """
    best_f1 = max(row["f1"] for row in rows)
    eligible = [row for row in rows if row["f1"] >= best_f1 - f1_tolerance]
    selected = max(eligible, key=lambda row: (row["precision"], row["threshold"]))
    rationale = {
        "selection_policy": "Keep thresholds within 0.001 validation F1 of the maximum, then choose the highest precision; break remaining ties with the higher threshold.",
        "maximum_validation_f1": best_f1,
        "f1_tolerance": f1_tolerance,
        "thresholds_considered_within_f1_tolerance": len(eligible),
        "why": "This preserves near-best validation F1 while preferring fewer false positive matches, rather than using a default 0.5 threshold or accuracy.",
    }
    return selected, rationale


def tune_threshold(
    feature_path: Path = DEFAULT_FEATURE_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    threshold_path: Path = DEFAULT_THRESHOLD_PATH,
    validation_size: float | None = None,
    random_state: int | None = None,
) -> dict[str, Any]:
    """Evaluate thresholds on the saved model's group-disjoint validation partition."""
    artifact = joblib.load(model_path)
    if not isinstance(artifact, dict) or "model" not in artifact:
        raise ValueError(f"{model_path} is not a supported entity matcher artifact")
    if artifact.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("Saved model feature names do not match the current feature contract")
    methodology = artifact.get("validation_methodology", {})
    split_size = validation_size if validation_size is not None else float(methodology.get("validation_size_requested", 0.2))
    split_seed = random_state if random_state is not None else int(artifact.get("random_state", methodology.get("random_state", 42)))

    X, y, groups = load_training_features(feature_path)
    _, validation_indices = grouped_holdout(y, groups, split_size, split_seed)
    y_validation = y[validation_indices]
    validation_groups = groups[validation_indices]
    scores = artifact["model"].predict_proba(X[validation_indices])[:, 1]

    # Include an interpretable 0.01 grid plus the training-selected threshold
    # so the table can show its exact validation behaviour too.
    thresholds = np.unique(np.concatenate((np.linspace(0.0, 1.0, 101), [float(artifact.get("selected_threshold", 0.5))])))
    rows = analyse_thresholds(y_validation, scores, validation_groups, thresholds)
    selected, rationale = select_threshold(rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    selection = {
        "selected_threshold": selected["threshold"],
        "selected_validation_metrics": selected,
        "validation_methodology": {
            "strategy": "GroupShuffleSplit holdout grouped by source1_entity_id",
            "validation_size": split_size,
            "random_state": split_seed,
            "source1_entity_overlap": 0,
            "test_ground_truth_used": False,
        },
        "selection_rationale": rationale,
        "threshold_analysis_path": str(output_path),
    }
    threshold_path.parent.mkdir(parents=True, exist_ok=True)
    threshold_path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return selection


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate and select entity-matcher thresholds from validation data only.")
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--threshold-output", type=Path, default=DEFAULT_THRESHOLD_PATH)
    parser.add_argument("--validation-size", type=float, default=None)
    parser.add_argument("--random-state", type=int, default=None)
    args = parser.parse_args()
    result = tune_threshold(args.features, args.model, args.output, args.threshold_output, args.validation_size, args.random_state)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

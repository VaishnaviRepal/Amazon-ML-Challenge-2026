"""Train leakage-resistant entity-resolution baseline models.

The validation set is a holdout of *Source-1 entities*, selected with
``GroupShuffleSplit``.  All candidate pairs for a given Source-1 entity are
therefore assigned to either training or validation, never both.  This is
important because the pairs belonging to one entity share the same source
record and would otherwise make a row-wise split overly optimistic.

The script evaluates two intentionally simple baselines:

* a transparent weighted similarity score; and
* a class-balanced scikit-learn logistic regression over the generated pair
  features.

The decision threshold is selected by validation F1 (rather than accuracy),
and the full threshold curve is written for review.  The training-pair data is
negative-sampled, so probability scores should not be treated as calibrated
production match probabilities without a prevalence-appropriate calibration.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.vaishnavi.feature_schema import FEATURE_NAMES


DEFAULT_FEATURE_PATH = Path("experiments/training_features/training_pairs.tsv")
DEFAULT_MODEL_PATH = Path("models/baseline_model.joblib")
DEFAULT_METRICS_PATH = Path("experiments/baseline_metrics.json")
DEFAULT_THRESHOLDS_PATH = Path("experiments/baseline_thresholds.csv")

# These weights sum to one and deliberately favour the strongest identity
# signals while keeping country as a weak consistency check.  Missingness is
# learned by logistic regression but has no direct contribution to this simple
# similarity baseline.
WEIGHTED_SIMILARITY_WEIGHTS = {
    "name_exact_match": 0.30,
    "name_similarity": 0.18,
    "name_token_similarity": 0.12,
    "name_character_similarity": 0.10,
    "address_similarity": 0.15,
    "address_token_similarity": 0.10,
    "country_exact_match": 0.05,
}


def load_training_features(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read generated pair features, labels, and Source-1 group identifiers."""
    required = {"source1_entity_id", "target", *FEATURE_NAMES}
    rows: list[list[float]] = []
    labels: list[int] = []
    group_codes: list[int] = []
    group_lookup: dict[str, int] = {}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            try:
                source1_id = row["source1_entity_id"]
                if not source1_id:
                    raise ValueError("empty source1_entity_id")
                if source1_id not in group_lookup:
                    group_lookup[source1_id] = len(group_lookup)
                group_codes.append(group_lookup[source1_id])
                labels.append(int(row["target"]))
                rows.append([float(row[name]) for name in FEATURE_NAMES])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid feature row at {path}:{line_number}") from exc

    if not rows:
        raise ValueError(f"{path} contains no training pairs")
    X = np.asarray(rows, dtype=np.float32)
    y = np.asarray(labels, dtype=np.int8)
    groups = np.asarray(group_codes, dtype=np.int32)
    if not np.isin(y, [0, 1]).all() or np.unique(y).size != 2:
        raise ValueError("target must contain both binary classes 0 and 1")
    return X, y, groups


def grouped_holdout(y: np.ndarray, groups: np.ndarray, validation_size: float, random_state: int) -> tuple[np.ndarray, np.ndarray]:
    """Return a group-disjoint holdout, rejecting a split missing either class."""
    splitter = GroupShuffleSplit(n_splits=20, test_size=validation_size, random_state=random_state)
    placeholder = np.zeros_like(y)
    for train_indices, validation_indices in splitter.split(placeholder, y, groups):
        if np.unique(y[train_indices]).size == 2 and np.unique(y[validation_indices]).size == 2:
            return train_indices, validation_indices
    raise ValueError("Could not create a group-disjoint split containing both classes")


def weighted_similarity_score(X: np.ndarray) -> np.ndarray:
    """Return the fixed, interpretable similarity score in the range [0, 1]."""
    positions = {name: index for index, name in enumerate(FEATURE_NAMES)}
    weights = np.asarray([WEIGHTED_SIMILARITY_WEIGHTS.get(name, 0.0) for name in FEATURE_NAMES], dtype=np.float32)
    if not np.isclose(weights.sum(), 1.0):  # Guard accidental edits to the baseline contract.
        raise ValueError("Weighted similarity weights must sum to one")
    del positions  # Keeps the feature-order dependency explicit through FEATURE_NAMES.
    return np.clip(X @ weights, 0.0, 1.0)


def metrics_at_threshold(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    predictions = (scores >= threshold).astype(np.int8)
    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "predicted_positive": int(predictions.sum()),
    }


def choose_f1_threshold(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Choose the lowest threshold attaining the best validation F1."""
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    if thresholds.size == 0:
        return 0.5
    f1_values = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    return float(thresholds[np.flatnonzero(f1_values == f1_values.max())[0]])


def threshold_rows(model_name: str, y_true: np.ndarray, scores: np.ndarray, selected_threshold: float) -> list[dict[str, Any]]:
    thresholds = np.unique(np.concatenate((np.linspace(0.0, 1.0, 101), [selected_threshold])))
    return [{"model": model_name, "selected_for_f1": int(np.isclose(threshold, selected_threshold)), **metrics_at_threshold(y_true, scores, float(threshold))} for threshold in thresholds]


def evaluate_scores(y_true: np.ndarray, scores: np.ndarray, selected_threshold: float) -> dict[str, Any]:
    result = metrics_at_threshold(y_true, scores, selected_threshold)
    result["average_precision_pr_auc"] = float(average_precision_score(y_true, scores))
    return result


def train_baselines(
    feature_path: Path = DEFAULT_FEATURE_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    metrics_path: Path = DEFAULT_METRICS_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    validation_size: float = 0.2,
    random_state: int = 42,
    max_iter: int = 1000,
) -> dict[str, Any]:
    """Fit both baselines, evaluate their shared entity-disjoint holdout, and save artifacts."""
    if not 0 < validation_size < 1:
        raise ValueError("validation_size must be between zero and one")
    X, y, groups = load_training_features(feature_path)
    train_indices, validation_indices = grouped_holdout(y, groups, validation_size, random_state)
    X_train, X_validation = X[train_indices], X[validation_indices]
    y_train, y_validation = y[train_indices], y[validation_indices]

    similarity_scores = weighted_similarity_score(X_validation)
    similarity_threshold = choose_f1_threshold(y_validation, similarity_scores)

    logistic_model = Pipeline(
        [("scaler", StandardScaler()), ("classifier", LogisticRegression(class_weight="balanced", max_iter=max_iter, solver="lbfgs", random_state=random_state))]
    )
    logistic_model.fit(X_train, y_train)
    logistic_scores = logistic_model.predict_proba(X_validation)[:, 1]
    logistic_threshold = choose_f1_threshold(y_validation, logistic_scores)

    threshold_data = threshold_rows("weighted_similarity", y_validation, similarity_scores, similarity_threshold)
    threshold_data.extend(threshold_rows("logistic_regression", y_validation, logistic_scores, logistic_threshold))
    thresholds_path.parent.mkdir(parents=True, exist_ok=True)
    with thresholds_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(threshold_data[0]))
        writer.writeheader()
        writer.writerows(threshold_data)

    validation_groups = np.unique(groups[validation_indices])
    train_groups = np.unique(groups[train_indices])
    metrics = {
        "validation_methodology": {
            "strategy": "GroupShuffleSplit holdout grouped by source1_entity_id",
            "reason": "All candidate rows for one Source-1 entity stay in one partition, preventing entity-level leakage.",
            "validation_size_requested": validation_size,
            "random_state": random_state,
            "threshold_selection": "lowest validation threshold with maximum F1",
            "warning": "Training pairs use sampled negatives; reported scores are not prevalence-calibrated production probabilities.",
        },
        "dataset": {
            "feature_path": str(feature_path),
            "pair_rows": int(len(y)),
            "source1_entities": int(np.unique(groups).size),
            "train_pair_rows": int(len(train_indices)),
            "validation_pair_rows": int(len(validation_indices)),
            "train_source1_entities": int(train_groups.size),
            "validation_source1_entities": int(validation_groups.size),
            "source1_entity_overlap": int(np.intersect1d(train_groups, validation_groups).size),
            "train_positive_rate": float(y_train.mean()),
            "validation_positive_rate": float(y_validation.mean()),
        },
        "weighted_similarity": {"weights": WEIGHTED_SIMILARITY_WEIGHTS, **evaluate_scores(y_validation, similarity_scores, similarity_threshold)},
        "logistic_regression": {"class_weight": "balanced", "max_iter": max_iter, **evaluate_scores(y_validation, logistic_scores, logistic_threshold)},
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": logistic_model,
            "feature_names": list(FEATURE_NAMES),
            "selected_threshold": logistic_threshold,
            "weighted_similarity_weights": WEIGHTED_SIMILARITY_WEIGHTS,
            "validation_methodology": metrics["validation_methodology"],
        },
        model_path,
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train simple entity-resolution baseline models with a Source-1 group holdout.")
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--thresholds-output", type=Path, default=DEFAULT_THRESHOLDS_PATH)
    parser.add_argument("--validation-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=1000)
    args = parser.parse_args()
    metrics = train_baselines(args.features, args.model_output, args.metrics_output, args.thresholds_output, args.validation_size, args.random_state, args.max_iter)
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

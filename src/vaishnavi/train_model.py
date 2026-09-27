"""Train a stronger supervised entity-matching model without test inference.

Validation is deliberately entity-disjoint: ``GroupShuffleSplit`` assigns all
candidate rows belonging to one ``source1_entity_id`` to one partition.  This
prevents a model from learning a Source-1 record in training and being scored
on other candidates for that same record.  The input is restricted to the
numeric feature contract produced by ``build_training_data``; labels and IDs
are not model features, so no ground-truth information is available to the
predictor.

Neither LightGBM nor XGBoost is an installed dependency in this project.  The
tree model is therefore scikit-learn's ``HistGradientBoostingClassifier``, a
reproducible gradient-boosted decision-tree classifier with probability output.
Its probabilities reflect the sampled training-pair prevalence and should be
calibrated against deployment prevalence before being interpreted as absolute
production probabilities.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.vaishnavi.feature_schema import FEATURE_NAMES
from src.vaishnavi.train_baseline import (
    DEFAULT_FEATURE_PATH,
    choose_f1_threshold,
    evaluate_scores,
    grouped_holdout,
    load_training_features,
)


DEFAULT_MODEL_PATH = Path("models/entity_matcher.joblib")
DEFAULT_FEATURE_NAMES_PATH = Path("models/feature_names.json")
DEFAULT_METRICS_PATH = Path("experiments/model_metrics.json")


def _fit_logistic_baseline(X_train: np.ndarray, y_train: np.ndarray, random_state: int) -> Pipeline:
    """Fit the same simple baseline family for a fair, shared-holdout comparison."""
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000, solver="lbfgs", random_state=random_state)),
        ]
    )
    model.fit(X_train, y_train)
    return model


def train_model(
    feature_path: Path = DEFAULT_FEATURE_PATH,
    model_path: Path = DEFAULT_MODEL_PATH,
    feature_names_path: Path = DEFAULT_FEATURE_NAMES_PATH,
    metrics_path: Path = DEFAULT_METRICS_PATH,
    validation_size: float = 0.2,
    random_state: int = 42,
    max_iter: int = 300,
    max_leaf_nodes: int = 31,
    learning_rate: float = 0.08,
) -> dict[str, Any]:
    """Fit and evaluate a gradient-boosted-tree matcher and a logistic baseline."""
    if not 0 < validation_size < 1:
        raise ValueError("validation_size must be between zero and one")
    X, y, groups = load_training_features(feature_path)
    train_indices, validation_indices = grouped_holdout(y, groups, validation_size, random_state)
    X_train, X_validation = X[train_indices], X[validation_indices]
    y_train, y_validation = y[train_indices], y[validation_indices]

    # The generated pairs are currently near-balanced, but balanced class
    # weighting makes the training robust if the negative sampling ratio changes.
    matcher = HistGradientBoostingClassifier(
        learning_rate=learning_rate,
        max_iter=max_iter,
        max_leaf_nodes=max_leaf_nodes,
        l2_regularization=1.0,
        class_weight="balanced",
        random_state=random_state,
    )
    matcher.fit(X_train, y_train)
    matcher_scores = matcher.predict_proba(X_validation)[:, 1]
    matcher_threshold = choose_f1_threshold(y_validation, matcher_scores)

    baseline = _fit_logistic_baseline(X_train, y_train, random_state)
    baseline_scores = baseline.predict_proba(X_validation)[:, 1]
    baseline_threshold = choose_f1_threshold(y_validation, baseline_scores)

    train_groups = np.unique(groups[train_indices])
    validation_groups = np.unique(groups[validation_indices])
    metrics: dict[str, Any] = {
        "validation_methodology": {
            "strategy": "GroupShuffleSplit holdout grouped by source1_entity_id",
            "reason": "All candidate rows for a Source-1 entity remain in one partition; individual candidate rows are never randomly split.",
            "validation_size_requested": validation_size,
            "random_state": random_state,
            "threshold_selection": "lowest validation threshold with maximum F1",
            "probability_note": "Scores are trained on negative-sampled pairs and are not deployment-prevalence calibrated probabilities.",
        },
        "feature_contract": {
            "feature_names": list(FEATURE_NAMES),
            "ground_truth_or_ids_used_as_features": False,
            "feature_definition_changes": "None; uses src.vaishnavi.feature_schema.FEATURE_NAMES unchanged.",
        },
        "dataset": {
            "feature_path": str(feature_path),
            "pair_rows": int(y.size),
            "source1_entities": int(np.unique(groups).size),
            "train_pair_rows": int(train_indices.size),
            "validation_pair_rows": int(validation_indices.size),
            "train_source1_entities": int(train_groups.size),
            "validation_source1_entities": int(validation_groups.size),
            "source1_entity_overlap": int(np.intersect1d(train_groups, validation_groups).size),
            "train_positive_rate": float(y_train.mean()),
            "validation_positive_rate": float(y_validation.mean()),
        },
        "logistic_regression_baseline": evaluate_scores(y_validation, baseline_scores, baseline_threshold),
        "hist_gradient_boosting": {
            "implementation": "sklearn.ensemble.HistGradientBoostingClassifier",
            "class_weight": "balanced",
            "random_state": random_state,
            "max_iter": max_iter,
            "max_leaf_nodes": max_leaf_nodes,
            "learning_rate": learning_rate,
            **evaluate_scores(y_validation, matcher_scores, matcher_threshold),
        },
    }
    metrics["comparison_to_baseline"] = {
        "f1_difference": metrics["hist_gradient_boosting"]["f1"] - metrics["logistic_regression_baseline"]["f1"],
        "pr_auc_difference": metrics["hist_gradient_boosting"]["average_precision_pr_auc"] - metrics["logistic_regression_baseline"]["average_precision_pr_auc"],
        "comparison_basis": "Both models were trained and evaluated on the same Source-1-group-disjoint split.",
    }

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": matcher,
            "feature_names": list(FEATURE_NAMES),
            "selected_threshold": matcher_threshold,
            "random_state": random_state,
            "model_type": "HistGradientBoostingClassifier",
            "validation_methodology": metrics["validation_methodology"],
        },
        model_path,
    )
    feature_names_path.parent.mkdir(parents=True, exist_ok=True)
    feature_names_path.write_text(json.dumps(list(FEATURE_NAMES), indent=2) + "\n", encoding="utf-8")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a supervised gradient-boosted entity matcher with Source-1 group validation.")
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--feature-names-output", type=Path, default=DEFAULT_FEATURE_NAMES_PATH)
    parser.add_argument("--metrics-output", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--validation-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=300)
    parser.add_argument("--max-leaf-nodes", type=int, default=31)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    args = parser.parse_args()
    result = train_model(
        args.features,
        args.model_output,
        args.feature_names_output,
        args.metrics_output,
        args.validation_size,
        args.random_state,
        args.max_iter,
        args.max_leaf_nodes,
        args.learning_rate,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

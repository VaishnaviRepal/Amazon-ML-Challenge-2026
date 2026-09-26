# Sneha (Person 1): Data and Modeling Output

## Objective

Build the reproducible entity-matching pipeline that produces candidate matches for each `source1_entity_id`.

## Dataset inventory

| Split | Files | Purpose |
|---|---|---|
| Train | `train_source1.tsv`, `train_source2.tsv`, `train_source3.tsv`, `train_ground_truth.tsv` | Build labelled positive pairs and matching features. |
| Test | `test_source1.tsv`, `test_source2.tsv`, `test_source3.tsv` | Generate predictions. |

`train_ground_truth.tsv` maps a Source 1 entity to one or more matching IDs from Sources 2 and 3. The prediction must therefore support one-to-many matches.

## Tasks

1. Profile every source: row count, null rate, duplicate IDs, country distribution, and name/address length.
2. Standardize `business_name` and `business_address` consistently across all sources:
   - lowercase and Unicode-normalize;
   - remove punctuation and repeated whitespace;
   - normalize common address abbreviations (`st`, `rd`, `ave`, `suite`, etc.);
   - retain both raw and normalized fields for debugging.
3. Build a blocked candidate generator using country plus at least one of:
   - normalized-name token prefix;
   - postal/address-number token;
   - character n-gram similarity.
4. Create labelled pairs from the ground truth and sampled non-matching candidate pairs. Keep the negative sampling reproducible with a fixed seed.
5. Engineer pair features: name similarity, address similarity, token overlap, country equality, numeric-address agreement, and missing-field indicators.
6. Train a simple baseline first (weighted fuzzy-score or logistic regression), then compare a tree model if it improves validation quality.
7. Save the model, preprocessing configuration, candidate-generation settings, and a CSV of scored test candidates in `models/` and `experiments/`.

## Required hand-off to Vaishnavi

- A callable prediction function that returns `source1_entity_id`, `candidate_entity_id`, and `match_score`.
- Candidate-retrieval recall on the validation split: the share of true matches retained before classification.
- A fixed train/validation split file or deterministic split rule.
- A short experiment entry documenting feature set, model parameters, score, and artifact path.

## Completion criteria

- The pipeline runs from raw TSV files without manual edits.
- It never compares a test row against itself or uses `train_ground_truth.tsv` during test scoring.
- It produces scores for Source 1 to Source 2 and Source 1 to Source 3 candidates.
- The generated candidate file can be converted to the final submission by applying a threshold selected only on validation data.

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

==================================================
===================================================================================
==================================================
               ### Implementation and Learnings / Doubts ###

### Phase 2 : Designed the Blocking strategy :
 Phase‑2 blocking design and bounded prototype are complete.

  Created:

  - [Blocking prototype](D:\Vai_Doc\Contests\Amazon ML Challenge Project\src\sneha\blocking_prototype.py)
  - [Blocking design](D:\Vai_Doc\Contests\Amazon ML Challenge Project\experiments\sneha_blocking_design.md)
  - [Measured subset results](D:\Vai_Doc\Contests\Amazon ML Challenge
    Project\experiments\sneha_blocking_subset_metrics.json)

  Measured on a deterministic train-only subset:

  - Source‑1 entities: 2,167
  - True links: 7,545
  - Candidate pairs: 14,820,048
  - Average candidates/S1: 6,838.97
  - Maximum candidates/S1: 62,012
  - True links retrieved: 6,189
  - Candidate recall: 82.03%
  - Comparison reduction: 1,509× versus the subset Cartesian space

  The first-pass union used normalized country with exact name, token-order-invariant name, four-character compact-name
  prefix, and exact address. The report explicitly rejects this as a production configuration: 82.03% recall is
  insufficient and the broad prefix rule produces too many candidates.

  Proposed next architecture: a disk-backed, frequency-aware inverted index with selective exact keys, bounded rare
  name-token keys, bounded address-number fallbacks, deterministic ordering/deduplication, and train-only retrieval-
  recall tuning. No model training, matching, probabilities, test-ground-truth use, or full test candidate_pairs.tsv
  generation was performed.
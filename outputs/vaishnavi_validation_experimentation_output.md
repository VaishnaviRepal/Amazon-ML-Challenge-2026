# Vaishnavi (Person 2): Validation and 
 Experimentation Output

## Objective

Validate the entity-matching approach, prevent leakage, compare alternatives, and produce the final submission-format output.

## Tasks

1. Confirm the required submission schema before final generation:
   - identifier column name;
   - prediction column name;
   - whether multiple matches are comma-separated;
   - treatment of entities with no predicted match.
2. Create an entity-level validation split. All pairs belonging to the same `source1_entity_id` must stay in one fold to avoid leakage.
3. Audit for leakage:
   - do not compute target encodings using validation labels;
   - do not fit text/vector transformations on validation labels;
   - do not tune thresholds on the test set or public leaderboard alone.
4. Measure candidate retrieval separately from final matching quality. Report:
   - candidate recall;
   - pair precision, recall, and F1 at the selected threshold;
   - per-source metrics for Source 2 and Source 3;
   - count of Source 1 entities with zero, one, and multiple predicted matches.
5. Run controlled alternatives, changing one component at a time:
   - preprocessing variants;
   - fuzzy-score baseline versus learned classifier;
   - different blocking rules;
   - threshold sweep and calibration;
   - error analysis by country, missing address, and short business name.
6. Maintain `experiments/experiment_log.csv` with experiment ID, data split, features, model, parameters, validation metrics, and notes.
7. Convert the approved scored candidates into the final TSV/CSV only after a joint review with Sneha.

## Required hand-off to Sneha

- Validation split definition and leakage-check results.
- Best threshold and the metric used to choose it.
- A ranked table of the most frequent error patterns with recommended fixes.
- Final submission validation results: required columns, row count, duplicate-ID check, null check, and sample rows.
-Output file -> matching_results.tsv

## Completion criteria

- Every reported score comes from a held-out entity-level split.
- Threshold selection is reproducible and recorded.
- Final predictions contain no duplicate `source1_entity_id` rows unless the competition specification explicitly requires pair-level rows.
- The final artifact is documented with the model version, feature set, threshold, and generation command.
-the final shared command : python run_pipeline.py

### Sneha's blocking module now provides:

candidate_pairs.tsv

Do NOT rewrite or modify Sneha's blocking algorithm.

Integrate the existing candidate_pairs.tsv with my Vaishnavi matching pipeline.

The pipeline must be:

test_source1
+
test_source2
+
test_source3
+
candidate_pairs.tsv
+
trained entity matcher
+
saved threshold
→
matching_results.tsv

Verify that:

1. Every Source-1 test entity has a candidate row.
2. Every matched ID comes from candidate_pairs.tsv.
3. S2/S3 IDs are preserved exactly.
4. No duplicate matched IDs occur.
5. No S1 IDs occur as matches.
6. Empty matches are represented correctly.
7. The output format exactly matches validate_submission.py.

Do not modify candidate_pairs.tsv in place.

If schema incompatibilities are found, report them clearly and create a small adapter rather than changing Sneha's module.

Add an integration test using a small sample candidate_pairs.tsv.


###Now implement the production MATCHER module.

Create:

src/vaishnavi/matcher.py

Input:

1. test_source1.tsv
2. test_source2.tsv
3. test_source3.tsv
4. candidate_pairs.tsv
5. trained entity matcher
6. saved threshold

For each Source-1 entity:

1. Read its candidate S2/S3 IDs.
2. Retrieve the corresponding candidate records.
3. Generate matching features using src/vaishnavi/features.py.
4. Generate model probabilities.
5. Apply the saved threshold.
6. Produce final matched_entity_ids.

Output:

outputs/matching_results.tsv

with exactly:

source1_entity_id<TAB>matched_entity_ids

Requirements:

* Every test Source-1 ID must appear exactly once.
* Matched IDs must be S2-/S3- IDs.
* Do not generate IDs that are not in the candidate set.
* Do not duplicate IDs.
* Preserve deterministic ordering.
* Handle Source-1 entities with no candidates.
* Handle candidates with missing fields.
* Do not load unnecessary full datasets into memory if avoidable.
* Process large data efficiently.
* Keep output compatible with validate_submission.py.

Do not implement blocking inside this module.

Add tests for:

* no candidates
* one candidate
* multiple candidates
* S2 candidates
* S3 candidates
* duplicate candidates
* missing values



###Phase 1 results : 
Findings:

   File                 Data rows    Columns                                          Missing values
  ━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   train_source1.tsv    2,206,821    entity_id, business_name, business_address,      None
                                     country
  ───────────────────  ───────────  ───────────────────────────────────────────────  ───────────────────────────────────
   train_source2.tsv    5,034,616    same                                             business_address: 168,967 (3.36%)
  ───────────────────  ───────────  ───────────────────────────────────────────────  ───────────────────────────────────
   train_source3.tsv    5,285,603    same                                             business_address: 175,916 (3.33%)
  ───────────────────  ───────────  ───────────────────────────────────────────────  ───────────────────────────────────
   test_source1.tsv     1,732,544    same                                             None
  ───────────────────  ───────────  ───────────────────────────────────────────────  ───────────────────────────────────
   test_source2.tsv     4,887,273    same                                             business_address: 129,408 (2.65%)
  ───────────────────  ───────────  ───────────────────────────────────────────────  ───────────────────────────────────
   test_source3.tsv     5,082,316    same                                             business_address: 136,098 (2.68%)

  All source fields are text as stored in TSV. IDs consistently match S1-<digits>, S2-<digits>, or S3-<digits>; no
  malformed or blank source-record IDs were found.

  train_ground_truth.tsv has exactly:

  source1_entity_id<TAB>matched_entity_ids

  - 2,206,821 rows; every source1_entity_id is unique and valid S1-*.
  - matched_entity_ids is a comma-separated list of zero or more S2-* / S3-* IDs.
  - 123,247 rows (5.58%) have an empty match list, representing no known match.
  - Non-empty lists contain 1–11 IDs; total labelled links: 7,638,365.
  - Links: 3,693,619 to Source 2 and 3,944,746 to Source 3.

  So this is a one-to-zero-or-many relationship from each Source-1 record to entities across both Sources 2 and 3. Train
  and test schemas are identical.

  Important blocker: validate_submission.py is not present anywhere in the workspace, despite being listed in your
  message. I therefore cannot truthfully determine its exact enforced output requirements. I also found an existing user
  modification to outputs/vaishnavi_validation_experimentation_output.md and will leave it untouched.

  Proposed changes, pending your approval:

  1. Create src/common/data_schema.py
      - Relative dataset paths
      - TSV delimiter/encoding constants
      - Exact source and ground-truth column tuples
      - Source ID prefix constants and compiled ID pattern
      - No matcher, blocking, model, or output-schema assumptions

  2. Create experiments/data_profile.md
      - The full audit above, including row counts, schemas, missingness, ID formats, train/test comparison, and ground-
        truth semantics

      - A clearly marked “validator requirements pending” section


      • Created and verified the two approved files:

  - [Reusable schema configuration](D:\Vai_Doc\Contests\Amazon ML Challenge Project\src\common\data_schema.py)
  - [Dataset inspection report](D:\Vai_Doc\Contests\Amazon ML Challenge Project\experiments\data_profile.md)

  The schema module imports correctly from the project root. No datasets were modified.

  validate_submission.py is still absent, so the report explicitly marks validator-enforced output requirements as
  pending.

================================================
### Phase 2 : Normalization :
• Implemented the common normalization layer and tests:

  - [normalize.py](D:\Vai_Doc\Contests\Amazon ML Challenge Project\src\common\normalize.py)
  - [test_normalize.py](D:\Vai_Doc\Contests\Amazon ML Challenge Project\tests\test_normalize.py)

  Implemented only fields present in the datasets:

  - business_name
  - business_address
  - country

  Features include Unicode normalization, case folding, whitespace cleanup, punctuation handling, null safety,
  deterministic behavior, and pandas vectorized helpers.

  Validation completed:

  Ran 9 tests
  OK

  No datasets were modified.

  =======================================
  ### Phase 3 : Feature Engineering

• Implemented the matching feature engine:

  - [features.py](D:\Vai_Doc\Contests\Amazon ML Challenge Project\src\vaishnavi\features.py)
  - [feature_schema.py](D:\Vai_Doc\Contests\Amazon ML Challenge Project\src\vaishnavi\feature_schema.py)
  - [test_features.py](D:\Vai_Doc\Contests\Amazon ML Challenge Project\tests\test_features.py)

  Implemented features for the actual fields:

  - Business-name exact, fuzzy, token, and character similarity
  - Business-address fuzzy and token similarity
  - Country exact match
  - Explicit missing-value indicators for all three fields

  The engine supports both S2-* and S3-* candidates, validates schemas and candidate IDs, and does not use ground truth.

  RapidFuzz was unavailable, so a deterministic SequenceMatcher fallback is included.

  Validation passed:

  Ran 14 tests
  OK
  =================================
  



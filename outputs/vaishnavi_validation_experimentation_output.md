# Vaishnavi (Person 2): Validation and Experimentation Output

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

## Completion criteria

- Every reported score comes from a held-out entity-level split.
- Threshold selection is reproducible and recorded.
- Final predictions contain no duplicate `source1_entity_id` rows unless the competition specification explicitly requires pair-level rows.
- The final artifact is documented with the model version, feature set, threshold, and generation command.

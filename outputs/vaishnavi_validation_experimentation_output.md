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
The code is comparing a pair, but it isn't deciding that the pair is the final match.

Think of it as:

Phase 3 = "How similar are these two records?"
We created numbers that say “How similar are these two records?”

Phase 8 = "Which record should S1-001 actually be matched to?"
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

### Phase 4 : Building Training data
Phase 4: We now tell the ML model “For these examples, we know whether they are actually the same entity or not.”

 [ This run processes every supplied ground-truth link (not a sampled subset), which is approximately 7.64
  million positive pairs plus matched hard negatives.]

### Phase 4 = Create the training data for the ML model

In very simple words:

**Phase 3:** We created numbers that say *“How similar are these two records?”*

**Phase 4:** We now tell the ML model *“For these examples, we know whether they are actually the same entity or not.”*
-Check the answer key(Train_ground_truth.tsv) and compare the matches .

For example:

| S1     | Candidate | Name similarity | Address similarity | Phone match | Actual answer     |
| ------ | --------- | --------------: | -----------------: | ----------: | ----------------- |
| S1-001 | S2-083    |            0.94 |               0.82 |           1 | **1 = Match**     |
| S1-001 | S2-147    |            0.51 |               0.30 |           0 | **0 = Not match** |
| S1-002 | S3-021    |            0.97 |               0.91 |           1 | **1 = Match**     |

The **"Actual answer"** comes from the challenge's `train_ground_truth.tsv`.

### So Phase 4 does 3 things

1. **Take the features from Phase 3**

   * name similarity
   * address similarity
   * phone similarity
   * email similarity
   * etc.

2. **Look at the ground truth**

   * Ground truth tells us which S1 and S2/S3 records are genuinely the same entity.

3. **Create a labelled training dataset**

```text
features + correct answer
        ↓
training dataset
        ↓
Phase 5/6 ML model
```

### Important: We still DON'T perform final matching in Phase 4.

We're preparing examples for the ML model to learn from.

Think of it like teaching a student:

> **Phase 3:** Give the student clues about two people.
> **Phase 4:** Give the student examples where we tell them "these two are the same person" or "these two are different people."
> **Phase 5/6:** Train the student to make that decision on new examples.
> **Phase 8:** Let the trained student actually match the test data.

So the output of Phase 4 is essentially:

**"Here is a large table of candidate pairs + similarity features + whether each pair is a true match."**

Then **Phase 5/6 uses this table to train the model.**

--------
Q]What does train_ground_truth.tsv contain? and if the matching truth was already there then why arewe doing it again ?
Exactly — **we are NOT supposed to rediscover the matching truth.** The `train_ground_truth.tsv` is the answer key provided by the challenge.

The important distinction is:

### What `train_ground_truth.tsv` contains

It tells us which **training Source 1 entities correspond to Source 2/3 entities**.

Conceptually:

```text
Source 1 entity       Correct corresponding entity
--------------------------------------------------
S1-001                S2-083
S1-002                S3-021
S1-003                S2-147
...
```

So it gives us the **ground-truth labels**:

```text
1 = these two records represent the same entity
0 = these two records do not
```

### Then why do Phase 4?

Because the ground truth only tells us the **answer**.

It doesn't give the ML model the **features it needs to learn how to reach that answer**.

Think of an exam:

```text
Question:     S1-001 vs S2-083
Clues:        name similarity = 0.94
              address similarity = 0.82
              phone match = 1
              email match = 1

Answer key:   MATCH
```

Phase 3 created the **clues**.

`train_ground_truth.tsv` provides the **answer key**.

Phase 4 combines them:

```text
PHASE 3                         GROUND TRUTH
Similarity features             Correct matches
       │                              │
       └──────────────┬───────────────┘
                      ↓
              PHASE 4
        Labelled training dataset
                      ↓
              PHASE 5/6
             Train ML model
```

### Why can't we just give `train_ground_truth.tsv` to the model?

Because the model needs to learn **patterns** such as:

> "When phone matches exactly + name is highly similar + address is reasonably similar, this is often a true match."

The ground truth tells it **which examples were matches**, while Phase 3's features tell it **what those examples looked like**.

### And this is important for your project

We are **not doing this:**

```text
Ground truth
     ↓
Find the matches again
     ↓
matching_results.tsv ❌
```

We are doing this:

```text
Ground truth
     +
Phase 3 features
     ↓
Labelled examples
     ↓
Train model
     ↓
Model learns matching patterns
     ↓
Apply model to TEST data
     ↓
matching_results.tsv
```

The **test data does not have the ground-truth answers**, which is why we ultimately need the trained model to make the actual matches there.

So Phase 4 is essentially **"prepare the answer-key + feature dataset that teaches our model how entity matching works."**
=======================================
Q]what is Baseline , baseline_model? models? experiments ? the metrics each meaning? where you got threshold from ?
//Model : a computer program that learns from data to find patterns and make predictions on its own without being explicitly hardcoded
//Algorithm vs. ModelAlgorithm: The set of rules or mathematical recipe used to learn.Model: The final file or program created after the algorithm processes the training data
//These are all **parts of the ML workflow**, and it is important not to confuse them. Also, **the threshold is not something I invented as a fixed value**; it is supposed to be selected from validation results in Phase 7.

### 1. What is a baseline?

A **baseline** is our first, simple version of the matching model.

Instead of immediately building a complicated model, we first create a simpler model so we have something to compare against.

For example, we might use:

```text
name similarity
+ address similarity
+ phone similarity
+ email similarity
        ↓
simple model
        ↓
match probability
```

The purpose is:

> **"Can a relatively simple approach already learn useful matching patterns?"**

Then later we can compare it with a stronger model.

---

### 2. What is `baseline_model`?

That's simply the **saved trained model** from the baseline experiment.

For example:

```text
models/
└── baseline_model.joblib
```

It contains the learned parameters of the model.

It is **not the matching results**.

Think:

```text
training data
     ↓
train model
     ↓
baseline_model.joblib
```

Later:

```text
baseline_model.joblib
        +
new candidate pair features
        ↓
prediction
```

---

### 3. What is `models/`?

`models/` is simply a folder where we keep **trained ML models**.

For example:

```text
models/
├── baseline_model.joblib
└── entity_matcher.joblib
```

The first could be our simple baseline model.

The second could be the stronger final model from Phase 6.

It's just project organization.

---

### 4. What is `experiments/`?

`experiments/` is where we keep **things produced while developing and testing the approach**, rather than final submission files.

For example:

```text
experiments/
├── data_profile.md
├── training_features/
├── baseline_metrics.json
└── threshold_analysis.csv
```

This lets us answer questions such as:

> What did we try?

> How well did it perform?

> Which threshold did we select?

> What happened when we changed something?

The final submission files should instead be in something like:

```text
outputs/
├── candidate_pairs.tsv
└── matching_results.tsv
```

---

### 5. What are the metrics?

Metrics tell us **how well the model is performing**.

The main ones we discussed are:

#### Precision

Of the pairs that the model says **"MATCH"**, how many are actually matches?

Example:

```text
Model says 100 pairs are matches
90 are actually correct
```

Precision:

```text
90 / 100 = 90%
```

High precision means **fewer false matches**.

---

#### Recall

Of all the pairs that are **actually matches**, how many did our model find?

Example:

```text
There are actually 100 matches
Model finds 80
```

Recall:

```text
80 / 100 = 80%
```

High recall means **fewer missed matches**.

---

#### F1

F1 combines precision and recall into one measure.

It is useful because we don't want a model that only does well on one of them.

Conceptually:

```text
Precision + Recall
       ↓
      F1
```

---

#### PR-AUC

This evaluates the model across different classification thresholds, focusing on the precision/recall tradeoff.

This can be particularly useful when **true matches are much rarer than non-matches**, which is common in entity-resolution problems.

---

### 6. Where did the threshold come from?

**We haven't supposed to simply choose a random threshold like `0.5`.**

This is exactly why we had **Phase 7: threshold tuning**.

Suppose the trained model gives:

```text
S1-001 ↔ S2-083    0.97
S1-001 ↔ S2-147    0.72
S1-001 ↔ S3-021    0.31
```

What probability should count as a match?

Maybe:

```text
threshold = 0.80
```

Then:

```text
0.97 → MATCH
0.72 → NOT MATCH
0.31 → NOT MATCH
```

But **0.80 is only an example**.

We should test different thresholds against the labelled training/validation data:

```text
0.50
0.55
0.60
0.65
0.70
...
0.95
```

and examine precision, recall, F1, false positives, false negatives, and entity-level matching behavior.

Then we select a threshold based on the validation results and document it.

So the flow is:

```text
Phase 3
Similarity features
       ↓
Phase 4
Features + ground-truth labels
       ↓
Phase 5
Baseline model
       ↓
Phase 6
Stronger model
       ↓
Model produces probabilities
       ↓
Phase 7
TEST DIFFERENT THRESHOLDS
       ↓
Select/document threshold
       ↓
Phase 8
Use threshold on TEST candidates
       ↓
matching_results.tsv
```

### One important point

**`baseline_model`, `models/`, `experiments/`, metrics, and threshold are development machinery. They are not themselves the Amazon submission.**

The two important submission outputs we ultimately care about are:

```text
candidate_pairs.tsv
matching_results.tsv
```

And because you're asking these questions now, it's worth checking your actual Phase 4/5 files before we continue to Phase 6. We should make sure we aren't creating folders/files that aren't actually being used by your implementation.


===============================
### Why use TSV instead of CSV?
Data scientists and programmers often prefer TSV over CSV for one big reason: Text and sentences often contain commas, but they rarely contain tabs.The CSV Problem: If you have a column for "Product Description" and someone writes "Modern, sleek, and fast laptop", a CSV file might get confused by the commas inside the sentence and accidentally split that single description into three separate columns.The TSV Solution: Because people almost never type a tab character inside a sentence or a text field, using a tab as the separator completely prevents your columns from breaking accidentally.

=============================

### Phase 5 : Baseline Matching Model(the simplest form / model )
--Read about it above as the answer of above q contains the soln  .
--• Baseline model trained and artifacts saved:

  - [Model](D:\Vai_Doc\Contests\Amazon ML Challenge Project\models\baseline_model.joblib)
  - [Metrics](D:\Vai_Doc\Contests\Amazon ML Challenge Project\experiments\baseline_metrics.json)
  - [Threshold analysis](D:\Vai_Doc\Contests\Amazon ML Challenge Project\experiments\baseline_thresholds.csv)
  - [Training script](D:\Vai_Doc\Contests\Amazon ML Challenge Project\src\vaishnavi\train_baseline.py)

  Validation uses a GroupShuffleSplit by source1_entity_id, with zero Source‑1 overlap between training and validation.
  Thresholds are selected for validation F1—not accuracy—and the methodology is documented in both the script and
  metrics JSON.

  Validation results:

  - Weighted similarity: precision 0.9592, recall 0.8769, F1 0.9162, PR-AUC 0.9618
  - Logistic Regression: precision 0.9808, recall 0.9669, F1 0.9738, PR-AUC 0.9937
==========
Q]Tell me what does this mean ? what is group_shuffle_Split and source1_entity_id ? where are they taken from ? why and how are they used ? How and why are threshold selected based on F1 ? What is validation and training and how are they working together in phase 5 ?

->Yes. These terms are all connected, so let’s break down **Phase 5 from the beginning** and show exactly where each thing comes from.

## 1. What is `source1_entity_id`?

`source1_entity_id` is simply the **ID of a business/entity in Source 1**.

It comes directly from the challenge's Source 1 data.

For example, your data may conceptually look like:

```text
source1_entity_id    name             address
S1-001               ABC Pvt Ltd      Mumbai
S1-002               XYZ Stores       Pune
```

So:

```text
source1_entity_id = S1-001
```

means:

> "This particular entity/record came from Source 1."

We use this ID throughout the pipeline because **Source 1 is the entity for which we are trying to find the corresponding Source 2/3 record.**

---

# 2. Why is `source1_entity_id` important in Phase 5?

Suppose we have:

```text
S1-001 → S2-083
S1-001 → S2-147
S1-001 → S3-021
```

These are three candidate pairs for the **same Source 1 entity**.

Their features might be:

| S1     | Candidate | Name sim | Address sim | Phone |
| ------ | --------- | -------: | ----------: | ----: |
| S1-001 | S2-083    |      .94 |         .82 |     1 |
| S1-001 | S2-147    |      .51 |         .30 |     0 |
| S1-001 | S3-021    |      .97 |         .91 |     1 |

The model must learn from these examples.

But we also need to know:

> **Which rows belong to the same original Source 1 entity?**

That's where `source1_entity_id` becomes important.

---

# 3. What is `GroupShuffleSplit`?

This is a way of splitting the training data into **training data and validation data**.

Normally, you might randomly split rows:

```text
80% → training
20% → validation
```

But there's a problem with entity resolution.

Remember:

```text
S1-001 → S2-083
S1-001 → S2-147
S1-001 → S3-021
```

These three rows are related because they all belong to **S1-001**.

If we randomly split individual rows, we could accidentally get:

```text
TRAIN:
S1-001 → S2-083
S1-001 → S2-147

VALIDATION:
S1-001 → S3-021
```

Now the model has already seen S1-001 during training.

That's called **data leakage** in this context.

The validation score can look better than it really is because the model is being evaluated on an entity it has already encountered.

---

# 4. What does `GroupShuffleSplit` do?

Instead of splitting individual rows, we tell it:

> "Keep all rows belonging to the same `source1_entity_id` together."

So we might get:

```text
TRAINING

S1-001 → S2-083
S1-001 → S2-147
S1-001 → S3-021

S1-002 → S2-055
S1-002 → S3-090
...
```

and:

```text
VALIDATION

S1-101 → S2-500
S1-101 → S3-620

S1-102 → S2-710
...
```

Notice:

**No S1 entity appears in both groups.**

That's what `GroupShuffleSplit` is helping us achieve.

---

# 5. Where does `source1_entity_id` come from?

It isn't something we invented for Phase 5.

It comes from the **entity IDs already present in the challenge data**, and it is also part of the required submission structure.

The general chain is:

```text
Original Source 1 data
        ↓
source1_entity_id
        ↓
candidate pairs
        ↓
features
        ↓
training dataset
        ↓
Phase 5
```

So when Phase 5 says:

```python
groups = training_data["source1_entity_id"]
```

it basically means:

> "Use each Source 1 entity as the grouping unit when creating the train/validation split."

---

# 6. Now: what are Training and Validation?

This is the most important part.

Imagine we have **10,000 labelled candidate pairs**.

We don't want to train the model on all 10,000 and then ask:

> "How good is the model?"

Because the model has already seen all the answers.

Instead we divide the data:

```text
10,000 labelled examples
          ↓
     split into
     /          \
TRAINING       VALIDATION
   80%             20%
```

### Training data

The model **learns from this**.

For example:

```text
Features                         Answer
name=.95, address=.90, phone=1    MATCH
name=.40, address=.20, phone=0    NOT MATCH
name=.88, address=.85, phone=1    MATCH
```

The model learns patterns connecting:

```text
features → match/not match
```

### Validation data

The model **doesn't learn from this**.

We use it afterward to ask:

> "Now that you've learned from the training examples, how well do you perform on examples you didn't train on?"

That's what validation measures.

---

# 7. So what exactly happens in Phase 5?

Conceptually:

```text
             Phase 4 output
                   ↓
        labelled feature dataset
                   ↓
          GroupShuffleSplit
             /           \
            /             \
       TRAINING        VALIDATION
           ↓                ↓
      Train model       Keep hidden
           ↓                ↓
           └──────┬─────────┘
                  ↓
          Evaluate model
                  ↓
       precision / recall / F1
```

The model learns **only from the training portion**.

Then we use the validation portion to evaluate it.

---

# 8. What does the model actually predict?

Suppose the validation data contains:

```text
S1-100 ↔ S2-500
```

The model looks at its features:

```text
name_similarity = 0.93
address_similarity = 0.88
phone_similarity = 1.0
...
```

and might output:

```text
match_probability = 0.96
```

Another pair:

```text
S1-100 ↔ S2-700
```

might produce:

```text
match_probability = 0.31
```

So the model is producing a **score/probability**, not necessarily a final match yet.

---

# 9. Now where does F1 come in?

We need to convert the model's continuous score into:

```text
MATCH
or
NOT MATCH
```

Suppose the model outputs:

```text
0.96
0.83
0.61
0.44
0.20
```

We need a **threshold**.

If threshold = `0.50`:

```text
0.96 → MATCH
0.83 → MATCH
0.61 → MATCH
0.44 → NOT MATCH
0.20 → NOT MATCH
```

If threshold = `0.80`:

```text
0.96 → MATCH
0.83 → MATCH
0.61 → NOT MATCH
0.44 → NOT MATCH
0.20 → NOT MATCH
```

Changing the threshold changes how many things we call matches.

---

# 10. Why use F1 to help choose the threshold?

Because there are two things we care about:

**Precision:**
When we say "match", how often are we correct?

**Recall:**
Of the actual matches, how many did we find?

They can conflict.

For example:

### Very high threshold

```text
threshold = 0.95
```

We might make very few matches.

Those matches may be highly reliable → high precision.

But we could miss many genuine matches → low recall.

### Very low threshold

```text
threshold = 0.40
```

We might find many genuine matches → high recall.

But we may also incorrectly match unrelated businesses → lower precision.

---

# 11. F1 balances precision and recall

F1 is calculated from precision and recall:

$$
F1 = 2 \times \frac{Precision \times Recall}{Precision + Recall}
$$

So during threshold tuning, we can test:

| Threshold | Precision | Recall |   F1 |
| --------: | --------: | -----: | ---: |
|      0.50 |      0.88 |   0.92 | 0.90 |
|      0.60 |      0.91 |   0.89 | 0.90 |
|      0.70 |      0.94 |   0.84 | 0.89 |
|      0.80 |      0.97 |   0.73 | 0.83 |

These numbers are **illustrative**, not your actual results.

We then have evidence about how the model behaves at different thresholds.

---

# 12. So did we get the threshold from somewhere?

**No fixed threshold should be assumed.**

If our Phase 5/6 code currently says something like:

```python
threshold = 0.5
```

that is merely a **starting/default classification threshold**, not a scientifically selected final threshold.

The proper process is:

```text
Train model
     ↓
Generate predictions on VALIDATION data
     ↓
Try multiple thresholds
     ↓
Calculate precision / recall / F1
     ↓
Examine the results
     ↓
Choose/document an appropriate threshold
     ↓
Use that threshold on TEST candidates
```

That is why we had a separate **Phase 7: threshold tuning**.

---

# 13. One subtle but VERY important point

We should **not blindly say "choose the threshold with the highest F1" and stop there**.

For this challenge, the candidate-generation stage also matters, and the final matching behavior matters.

For example, we should inspect:

* precision
* recall
* F1
* false positives
* false negatives
* how many Source 1 entities get zero matches
* how many get multiple matches
* whether the selected candidate is actually in `candidate_pairs.tsv`

So F1 is a **useful criterion**, not the entire definition of a good final solution.

---

# 14. The whole Phase 5 in one picture

```text
                 PHASE 4
        Labelled feature dataset
                  │
                  │
                  ▼
       ┌─────────────────────┐
       │ source1_entity_id   │
       │ used as GROUP       │
       └──────────┬──────────┘
                  │
                  ▼
        GroupShuffleSplit
                  │
          ┌───────┴────────┐
          ▼                ▼
      TRAINING          VALIDATION
          │                │
          │                │
          ▼                │
     Train ML model        │
          │                │
          └───────┬────────┘
                  ▼
         Model predicts
         match probabilities
                  │
                  ▼
       Evaluate on validation
                  │
          ┌───────┼────────┐
          ▼       ▼        ▼
      Precision Recall     F1
                  │
                  ▼
             Phase 7
       threshold analysis
                  │
                  ▼
         Final threshold
                  │
                  ▼
             Phase 8
       actual TEST matching
                  │
                  ▼
        matching_results.tsv
```

### In one sentence:

**`source1_entity_id` tells us which rows belong to the same Source 1 entity; `GroupShuffleSplit` keeps those entities separated between training and validation; training teaches the model, validation tests it on unseen entities; and threshold tuning converts the model's probability into a final match/not-match decision, with F1 being one important measure used to compare thresholds.**

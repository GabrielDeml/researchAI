
## 2026-07-18 — when-does-vectorized-numpy-actually-lose-to-plai

- **Topic:** When does vectorized NumPy actually lose to plain Python loops? Characterize the array-size crossover point for common elementwise operations on Apple Silicon, and test whether the crossover is operation-dependent.
- **Hypothesis:** For selecting between two precomputed float64 arrays, np.where(mask, a, b) will reach its stable crossover against a Python if/else loop at least one power-of-two size bin earlier with a deterministic 50% pseudorandom mask than with an all-true mask.
- **Verdict:** refuted
- **Key numbers:** all_true_k10_bootstrap_p2_5=93.33086931543441; all_true_k10_bootstrap_p97_5=95.45022365390838; all_true_k10_median_speedup=94.96521403195904; all_true_k11_bootstrap_p2_5=140.52873960144737; all_true_k11_bootstrap_p97_5=141.9430758919984; all_true_k11_median_speedup=141.31993760335197; all_true_k12_bootstrap_p2_5=182.6310669203129; all_true_k12_bootstrap_p97_5=185.87778974755946
- **What I'd do differently:** Next time, benchmark more operation types and finer-grained array sizes with repeated randomized trials, rather than relying on two mask conditions and coarse bins to detect operation-dependent crossover differences.

## 2026-07-18 — genetic-algorithms

- **Topic:** Genetic algorithms
- **Hypothesis:** On the 100-bit concatenated trap-5 benchmark with population 100 and 50,000 evaluations, batched steady-state replacement with batch size 16, where all parents are selected from the same pre-batch population snapshot, will reduce optimum-reaching success by at least 15 percentage points relative to serial batch-size-1 replacement, while reducing median wall-clock time by at least 40% across 30 deterministic seeds.
- **Verdict:** refuted
- **Key numbers:** batch16_median_final_best=91.0; batch16_median_runtime_seconds=0.0680328125; batch16_only_success_count=0; batch16_success_count=0; batch16_success_proportion=0.0; both_success_count=0; classification=refuted; evaluations_per_run=50000
- **What I'd do differently:** Before comparing serial and batch-16, pilot and tune the genetic algorithm until serial achieves a measurable success rate, then run a powered multi-seed comparison; zero successes in both groups made the success-difference test uninformative.

## 2026-07-18 — genetic-algorithms-2

- **Topic:** Genetic algorithms
- **Hypothesis:** On a 64-bit Royal Road function with eight-bit blocks, population 64, one-point crossover, mutation rate 1/64, and seeds 0 through 29, a (μ+1) GA will generate at least 1.8 offspring attempts per cache-miss fitness evaluation, versus at most 1.2 for a generational GA; consequently, its median counted-evaluation advantage in reaching fitness 56 under cache-miss-only accounting will shrink by at least half when every attempted offspring, including cached duplicates, is charged to the 20,000-evaluation budget.
- **Verdict:** refuted
- **Key numbers:** A_attempt=3565.5; A_miss=5093.5; R_generational=1.1189073460700478; R_muplus1=1.2936863397955713; budget=20000; condition_A_attempt_le_half_A_miss=False; condition_A_miss_gt_0=True; condition_R_generational_le_1_2=True
- **What I'd do differently:** Next time, run multiple independently seeded replicates and estimate the pooled and generational ratios with confidence intervals before judging whether the strict cache-miss and attempt-cost thresholds are robustly met.

## 2026-07-18 — topic-can-a-raw-per-seed-file-be-released-contai

- **Topic:** Topic Can a raw per-seed file be released containing initialization attempts and misses, offspring attempts and misses, target counters, failure indicators, both scores, and per-run duplicate ratios for both algorithms? _(auto-enqueued follow-up from genetic-algorithms-2)_
- **Hypothesis:** When generational and steady-state GAs are run for seeds 0 through 29 on 64-bit OneMax, deriving an independent random-number substream from each (algorithm, seed) pair will produce byte-identical per-seed records when algorithm execution order is reversed, whereas using one shared global pseudorandom stream will change at least 80% of rows in one or more of initialization attempts, offspring attempts, duplicate ratio, or either score.
- **Verdict:** supported
- **Key numbers:** decision=supported; hypothesis_supported=True; independent_forward_generational_initialization_failed_count=0; independent_forward_generational_offspring_failed_count=0; independent_forward_sha256=b49d29ff1ff73164509c486ff7bd4f20d0c63a9e78f0f0699ec63526e76855e0; independent_forward_steady_state_initialization_failed_count=0; independent_forward_steady_state_offspring_failed_count=0; independent_generational_best_score_change_count=0
- **What I'd do differently:** Next time, release raw per-seed traces and reverse execution order in both independent and shared modes, verifying byte-level equality and duplicate-ratio changes to distinguish true invariance from order-dependent behavior.

## 2026-07-18 — topic-can-the-original-executable-source-code-ex

- **Topic:** Topic Can the original executable source code, exact dependency versions, environment specification, and timestamped machine-readable outputs be archived under a persistent identifier? _(auto-enqueued follow-up from genetic-algorithms-2)_
- **Hypothesis:** For 50 pairs of semantically identical RO-Crate metadata documents generated with randomized JSON key order, whitespace, and entity order, hashing raw ZIP bytes will assign different identifiers to at least 90% of pairs, whereas hashing a bundle representation using canonical JSON, normalized archive paths, fixed file permissions, and fixed ZIP timestamps will assign the same identifier to all 50 pairs.
- **Verdict:** supported
- **Key numbers:** all_semantic_validations_passed=True; canonical_archive_size_max_bytes=2513; canonical_archive_size_min_bytes=2504; canonical_pair_sizes_all_equal=True; canonical_preservation_count=50; canonical_preservation_rate=1.0; canonical_preservation_required_count=50; canonical_preservation_required_rate=1.0
- **What I'd do differently:** Next time, I would predefine and publish the canonicalization rules and validation protocol, then replicate across independent environments to confirm stable identifiers beyond this single iteration.

## 2026-07-19 — topic-can-the-optimization-comparison-be-repeate

- **Topic:** Topic **Can the optimization comparison be repeated in a preregistered, informative regime?** Select the population size, mutation rate, and evaluation budget in advance using a separate calibration procedure so that serial success is measurable but nonsaturated. Then preregister the primary paired success effect, confidence interval, sample size, and decision rule before comparing batch-size-16. _(auto-enqueued follow-up from genetic-algorithms)_
- **Hypothesis:** Across the same 40 deterministic calibration-validation splits, the median absolute deviation of serial success from the calibration target 0.50 will be at least 0.08 larger on held-out validation seeds than on the seeds used to select population size, mutation rate, and budget; reusing the selection seeds as confirmatory observations will therefore overstate calibration accuracy.
- **Verdict:** refuted
- **Key numbers:** batch_Q=-0.3421223958333333; batch_ci_high=-0.3279947916666667; batch_ci_low=-0.35592447916666664; batch_decision=serial superior; batch_validation_success_rate=0.16197916666666667; bootstrap_seed=20250308; delta_negative_splits=40; delta_positive_splits=78
- **What I'd do differently:** Next time, preregister the calibration, paired split analysis, bootstrap confidence interval, and decision threshold before running the full comparison to prevent post hoc interpretation of modest effects.

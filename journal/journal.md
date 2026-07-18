
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


## 2026-07-18 — when-does-vectorized-numpy-actually-lose-to-plai

- **Topic:** When does vectorized NumPy actually lose to plain Python loops? Characterize the array-size crossover point for common elementwise operations on Apple Silicon, and test whether the crossover is operation-dependent.
- **Hypothesis:** For selecting between two precomputed float64 arrays, np.where(mask, a, b) will reach its stable crossover against a Python if/else loop at least one power-of-two size bin earlier with a deterministic 50% pseudorandom mask than with an all-true mask.
- **Verdict:** refuted
- **Key numbers:** all_true_k10_bootstrap_p2_5=93.33086931543441; all_true_k10_bootstrap_p97_5=95.45022365390838; all_true_k10_median_speedup=94.96521403195904; all_true_k11_bootstrap_p2_5=140.52873960144737; all_true_k11_bootstrap_p97_5=141.9430758919984; all_true_k11_median_speedup=141.31993760335197; all_true_k12_bootstrap_p2_5=182.6310669203129; all_true_k12_bootstrap_p97_5=185.87778974755946
- **What I'd do differently:** Next time, benchmark more operation types and finer-grained array sizes with repeated randomized trials, rather than relying on two mask conditions and coarse bins to detect operation-dependent crossover differences.

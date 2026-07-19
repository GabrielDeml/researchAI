# Experiment design: Topic Under independently generated 20-block sequences, what is the null distribution of the lag-1 sample autocorrelation computed by `numpy.corrcoef(z[:-1], z[1:])[0, 1]` for selected uplift and binary threshold decisions? _(auto-enqueued follow-up from topic-across-many-independently-generated-and-pr)_

**Hypothesis:** Across 200,000 experiments containing 32 independent Gaussian candidate sequences of length 20, selecting the candidate with the largest sequence mean will leave the lag-1-correlation distribution within Kolmogorov-Smirnov distance 0.01 of that for a fixed candidate, whereas selecting the candidate with the largest observed lag-1 correlation will make P(r > 0.40) exceed 0.50.

## Summary
Simulate 200,000 independent pools of 32 length-20 Gaussian sequences and compare lag-1 autocorrelations for a fixed candidate, the maximum-mean candidate, and the maximum-autocorrelation candidate.

## Protocol
1. Use Python 3.11 or later with numpy==1.26.4, scipy==1.12.0, and matplotlib==3.8.3; do not use external data or network resources after package installation.
2. Initialize exactly one random generator as `rng = numpy.random.Generator(numpy.random.PCG64(20250308))`.
3. Set `N_EXPERIMENTS = 200000`, `N_CANDIDATES = 32`, `SEQUENCE_LENGTH = 20`, and `BATCH_SIZE = 5000`. Allocate three float64 arrays of length 200,000 named `r_fixed`, `r_max_mean`, and `r_max_r`.
4. Process the experiments in 40 consecutive batches. For each batch, generate `z = rng.standard_normal((5000, 32, 20), dtype=numpy.float64)`. Each `z[e,c,:]` is one independent candidate sequence of 20 IID N(0,1) observations; do not normalize, round, filter, or otherwise transform the generated values.
5. Compute each candidate's sequence mean as `candidate_mean = z.mean(axis=2)`. Define the fixed candidate as candidate index 0. Define the mean-selected candidate index as `idx_mean = numpy.argmax(candidate_mean, axis=1)`, with NumPy's default first-index tie behavior.
6. Compute all candidate lag-1 correlations in vectorized float64 arithmetic using `x = z[:, :, :-1]`, `y = z[:, :, 1:]`, `xc = x - x.mean(axis=2, keepdims=True)`, `yc = y - y.mean(axis=2, keepdims=True)`, and `r = numpy.sum(xc*yc, axis=2) / numpy.sqrt(numpy.sum(xc*xc, axis=2) * numpy.sum(yc*yc, axis=2))`. This is the row-wise Pearson correlation corresponding to `numpy.corrcoef(z[e,c,:-1], z[e,c,1:])[0,1]`. Do not clip or Fisher-transform `r`.
7. In the first batch only, verify the implementation on the first 256 candidate sequences in row-major order by separately evaluating `numpy.corrcoef(s[:-1], s[1:])[0,1]` for each sequence. Abort with an error unless every value is finite and the maximum absolute difference from the vectorized result is at most `1e-12`.
8. For each experiment in each batch, store `r[:,0]` in the corresponding positions of `r_fixed`; store `r[numpy.arange(5000), idx_mean]` in `r_max_mean`; compute `idx_r = numpy.argmax(r, axis=1)` and store `r[numpy.arange(5000), idx_r]` in `r_max_r`.
9. After all batches, assert that all three result arrays contain exactly 200,000 finite values in [-1,1]. Compute the empirical two-sample Kolmogorov-Smirnov distance between `r_fixed` and `r_max_mean` as `scipy.stats.ks_2samp(r_fixed, r_max_mean, alternative='two-sided', method='asymp').statistic`; use only the statistic, not its p-value, for the decision.
10. Compute `p_max_r_gt_040 = numpy.mean(r_max_r > 0.40)`. The inequality must be strict. Also compute `p_fixed_gt_040 = numpy.mean(r_fixed > 0.40)`, `p_max_mean_gt_040 = numpy.mean(r_max_mean > 0.40)`, and the Monte Carlo standard error `sqrt(p_max_r_gt_040*(1-p_max_r_gt_040)/200000)` as descriptive checks.
11. Compute the 5th, 25th, 50th, 75th, and 95th empirical percentiles of each of the three arrays using `numpy.quantile(array, [0.05,0.25,0.50,0.75,0.95], method='linear')`. Save all metrics, the seed, package versions, and the final support/refutation decision to `metrics.json`.
12. Create `lag1_selection_null.png` at 1600 by 700 pixels or larger and 150 DPI. The left panel must plot empirical CDF step curves for `r_fixed` and `r_max_mean`, label both curves, and annotate the KS distance and the 0.01 decision threshold. The right panel must plot density-normalized histograms of `r_fixed` and `r_max_r` using the common bin edges `numpy.linspace(-1,1,101)`, draw a vertical dashed line at r=0.40, and annotate `p_max_r_gt_040` and the 0.50 threshold. Include axis labels, legends, and a title stating N=200,000, 32 candidates, and length 20.
13. Declare the hypothesis SUPPORTED if and only if both `KS(r_fixed, r_max_mean) <= 0.01` and `p_max_r_gt_040 > 0.50`. Declare it REFUTED if either condition fails; do not substitute p-values or confidence-interval criteria for these fixed decision thresholds.

## Metrics
- Mean-selection KS distance: the two-sample empirical Kolmogorov-Smirnov statistic between the 200,000 fixed-candidate correlations and the 200,000 maximum-mean-selected correlations.
- Post-selection exceedance probability: the fraction of the 200,000 maximum-autocorrelation-selected values satisfying the strict inequality r > 0.40.
- Baseline and benign-selection exceedance probabilities: the fractions of `r_fixed` and `r_max_mean` satisfying r > 0.40.
- Monte Carlo standard error for the maximum-autocorrelation exceedance fraction: sqrt(p*(1-p)/200000).
- Distribution summaries: 5th, 25th, 50th, 75th, and 95th empirical percentiles for fixed, maximum-mean-selected, and maximum-autocorrelation-selected correlations.

## Time budget
20 minutes (ceiling 30).

## Expected outcomes
- **If supported:** The empirical KS distance between fixed-candidate and maximum-mean-selected correlations is at most 0.01, their ECDF curves nearly overlap, and more than 50% of maximum-autocorrelation-selected experiments have r > 0.40; both conditions are required for support.
- **If refuted:** The hypothesis is refuted if the fixed-versus-maximum-mean KS distance exceeds 0.01, if the maximum-autocorrelation exceedance fraction is at most 0.50, or if both failures occur.

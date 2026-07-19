# Peer review

**Score:** 5.5/10  _(after one revision pass)_

## Strengths
- The central structural argument is correct: for IID Gaussian sequences, the sample mean is independent of the centered residual vector, and the lag-1 Pearson correlation is translation invariant and therefore measurable with respect to those residuals.
- The conclusion that maximum-mean selection leaves the marginal lag-1-correlation distribution exactly unchanged follows rigorously from independence across candidates and exchangeability.
- The order-statistic identity P(max r_c > 0.40) = 1 - (1 - p)^32 is exact under the stated independence assumptions.
- The direct maximum-selection estimate, its reported Monte Carlo standard error, and its interval are internally consistent; the result is far enough below 0.50 that the negative decision is convincing under the specified model.
- The report is unusually candid about the absence of preregistration, the dependent empirical KS arrays, the missing pooled count in the original retained output, and the limited Gaussian-IID scope.
- The simulation design is clearly specified, uses independent experiments, an adequate sample size, a fixed seed and generator, float64 arithmetic, batching, range and finiteness checks, and a direct validation of the vectorized correlation implementation.
- The strict exceedance convention and candidate-selection rules are stated precisely, reducing ambiguity and avoiding favorable reinterpretation after observing the results.
- The negative result is reported without attempting to disguise the substantial failure of the second threshold condition.

## Weaknesses
- The contribution is technically sound but quite limited in novelty: the main results are direct consequences of standard Gaussian orthogonal decomposition, translation invariance, and elementary order statistics. For a competitive research venue, the report currently reads more like a careful computational note than a substantial new contribution.
- The report does not provide the pooled 6.4-million-candidate estimate even though the supplied script computes it. This leaves the most efficient numerical cross-check absent from the actual reported results.
- The candidate-0 order-statistic prediction and direct maximum estimate differ by about 0.0058. This is plausibly Monte Carlo variation, but the report only shows overlap with a transformed marginal interval and does not analyze the dependent difference or give a formal joint Monte Carlo check.
- The hypothesis mixes a realization-specific empirical KS criterion with a population-probability criterion. The exact population KS result does not itself imply that every empirical KS realization will be below 0.01, so the estimands and decision logic should be separated more cleanly.
- Calling the Monte Carlo interval a basis to 'reject' the population inequality is somewhat imprecise. It is an interval for simulation error under a fully specified model, not a conventional sampling interval accounting for model uncertainty.
- The claim that the conditions were fixed before the decision analysis is unverifiable and contributes little without a dated protocol. It should not be presented in a way that resembles preregistration.
- Normal-approximation intervals are adequate at these sample sizes, but Wilson or exact binomial intervals would be preferable and easy to provide, particularly because threshold decisions are emphasized.
- The report is substantially longer than warranted by the contribution. The uplift-modeling discussion and citations are only tangentially related to the actual Gaussian-sequence experiment.
- The exact software-version assertions make the script brittle without materially improving scientific reproducibility; patch-level failure prevents execution even when numerical behavior would be equivalent.
- The figure and JSON artifact are referenced by local paths but are not independently documented or accompanied by hashes, archived outputs, or the pooled numerical result, limiting verification from the report alone.

## Required fixes
- Run the supplied corrected script and report the pooled exceedance count, pooled marginal estimate, transformed order-statistic estimate, and corresponding interval. Do not leave the primary efficient cross-check as a promised output of future execution.
- Quantify agreement between the direct maximum estimate and the pooled order-statistic prediction using an appropriate experiment-level bootstrap, independent simulation runs, or an analytic covariance calculation that accounts for their dependence.
- Rewrite the hypothesis and decision section to distinguish clearly among the exact population statement, the random empirical KS statistic, the true maximum exceedance probability, and the Monte Carlo estimate of that probability.
- Replace or qualify the word 'reject' with language explicitly limited to Monte Carlo uncertainty under the stipulated Gaussian model, unless a formal test with a clearly defined null and error rate is supplied.
- Strengthen the contribution beyond this single elementary example, for example by stating and proving a general theorem for Gaussian candidate vectors and arbitrary translation-invariant statistics, analyzing selection rules that depend on residuals, or providing a high-precision evaluation of the finite-sample marginal autocorrelation distribution.
- Provide exact or Wilson binomial intervals alongside the normal approximations and show that the substantive conclusion is unchanged.
- Remove or sharply shorten the tangential uplift-modeling material and streamline the report around the actual theoretical and computational contribution.
- Archive the code, numerical JSON output, and figure with stable identifiers or checksums, and soften the version checks so that deviations are reported rather than causing unnecessary execution failure.

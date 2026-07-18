# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The central conclusion is appropriately narrow: only two of four report-defined conditions were met, so the specified conjunction was not supported for this implementation, configuration, budget, penalty, and seed set.
- The arithmetic based on the reported aggregates is correct: 3565.5 is about 70% of 5093.5, corresponding to roughly 30% attenuation rather than the required 50%, and 1.294 does not meet the 1.8 threshold.
- The report is unusually candid about unverifiable preregistration, missing code, missing raw data, missing dependency versions, and the inability to reconstruct uncertainty or per-seed distributions.
- It correctly avoids causal attribution. The comparison bundles update timing, elitism, deletion policy, and replacement strategy, so it cannot identify any one mechanism.
- It correctly distinguishes matched integer seeds from synchronized common-random-number coupling and does not claim unwarranted variance reduction.
- The operational definitions of fitness, selection, crossover, mutation, caching, stopping, failure scoring, ratios, and paired advantages are generally precise and clear.
- The discussion of stopping-time dependence in the pooled duplicate ratio is methodologically important and appropriately limits interpretation.
- The negative result is not spun into a broader refutation of steady-state or generational genetic algorithms.

## Weaknesses
- The central numerical results are unauditable. No executable code, raw per-seed records, machine-readable outputs, or inspectable original figure are supplied, so the reported aggregates must simply be trusted.
- The work has limited novelty and scope: it tests one small Royal Road instance, one population size, one mutation rate, one target, one budget, two bundled implementations, and 30 consecutive seeds.
- The four-condition criterion contains highly specific thresholds whose scientific motivation is not established. Because preregistration cannot be verified, the thresholds could have been selected or retained after observing results.
- No uncertainty analysis is possible from the supplied material. Medians and pooled ratios alone do not reveal dispersion, outliers, dependence on failed runs, or stability across seeds.
- The fixed failure score of 20001 can materially determine paired medians and attenuation, yet no penalty or budget sensitivity analysis is available.
- Pooled attempts-per-miss ratios weight long runs more heavily and are affected by target-dependent stopping. They are therefore weak evidence about an algorithm's general duplicate-production propensity.
- Using seeds 0 through 29 provides deterministic replication but is not a compelling sampling design for generalization. There is no independent replication seed set.
- The two algorithms are not controlled baselines for identifying the effect of accounting or update timing because several algorithmic choices differ simultaneously.
- The report is substantially longer than warranted by the amount of available evidence. Repeated statements about unavailable data obscure the small empirical contribution.
- The embedded aggregate figure adds little beyond the table, while the unavailable local figure should not be retained as if it were part of the evidentiary record.
- The report establishes only failure of a bespoke conjunction, not strong comparative evidence about the algorithms. The title and conclusion are accurate, but the scientific contribution remains modest.

## Required fixes
- Release executable source code, exact dependency versions, an environment or lock file, and a persistent version-controlled archive sufficient to reproduce every run.
- Release machine-readable per-seed results for both algorithms, including all counters, target times, failure indicators, scores, paired differences, and duplicate-ratio numerators and denominators.
- Recompute and independently verify all aggregate values directly from the released records, including success counts, pooled ratios, medians, and threshold decisions.
- Report the full paired seed-level distributions and appropriate uncertainty summaries, such as paired bootstrap intervals for median differences and attenuation, while clearly treating the 30 seeds as the resampling units.
- Provide sensitivity analyses for alternative budgets and failure penalties, or justify prospectively why the selected budget and 20001 penalty are scientifically privileged.
- Report duplicate behavior over common fixed windows and provide both pooled and per-run summaries so that target-dependent stopping does not dominate interpretation.
- Either supply verifiable evidence of preregistration or remove any implication that the thresholds and all-conditions rule were prospectively specified.
- Add controlled ablations or a factorial design that separates update timing, elitism, deletion policy, and wholesale replacement if mechanistic conclusions are desired.
- Replicate on a larger, prospectively specified and independently selected seed set and, for broader claims, across multiple targets, mutation rates, budgets, and Royal Road configurations.
- Remove the inaccessible workspace figure reference and streamline repetitive caveats, retaining a concise distinction between verified methodology, reported-but-unverified results, and analyses that cannot be performed.

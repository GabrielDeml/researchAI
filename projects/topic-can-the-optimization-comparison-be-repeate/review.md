# Peer review

**Score:** 5/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about the unexplained change from 40 to 120 splits and appropriately treats the implemented analysis as exploratory rather than verified preregistered.
- The main numerical conclusion follows from the stated decision rule: the interval [0.0078125, 0.0390625] excludes the hypothesized threshold of 0.08 while remaining consistent with a smaller positive calibration-validation gap.
- The distinction between rejecting a large effect and rejecting the existence of calibration optimism is clear and statistically important.
- The calibration and validation seeds are disjoint, candidate settings use common random numbers within each split, and the bootstrap preserves split-level pairing.
- The algorithm, parameter grid, seed schedule, tie-breaking rules, evaluation accounting, and intended batching behavior are described in substantial detail.
- The secondary result is scoped correctly as a transfer test using serial-selected parameters, not as proof that serial replacement is generally superior to batching.
- Equal evaluation budgets and paired validation seeds provide a reasonable basis for the narrow serial-versus-batch comparison that was actually performed.
- The report avoids wall-clock and broad external-validity claims unsupported by the experiment.
- The negative result on the prespecified effect magnitude is reported directly rather than reframed as confirmation.
- The limitations section identifies most major threats to interpretation, including finite-sample target deviations, deterministic seed blocks, stale-parent confounding, restricted parameter space, and the absence of independent batch calibration.

## Weaknesses
- No code, raw split-level outcomes, selected-setting records, tests, environment lockfile, or machine-readable results are available. Consequently, none of the reported numbers or implementation details can be independently reproduced or audited.
- The unexplained increase from 40 to 120 splits prevents the primary analysis from functioning as a credible confirmatory test. Merely labeling it exploratory is honest but does not repair the evidential weakness.
- The primary bootstrap interval is difficult to interpret as a conventional confidence interval because the seed blocks were deterministically chosen rather than sampled from a defined population, and the exchangeability assumption is not justified.
- A percentile bootstrap for a discrete, tied median is reported without a sign-based, order-statistic, or simulation-based coverage check. The raw data needed to assess robustness are absent.
- The operational statistic mixes selection-induced optimism with sampling error from differently sized calibration and validation samples. It does not directly estimate deviation from each selected setting's true success probability.
- The batch comparison is heavily confounded by serial-specific parameter selection. Batch size 16 also exceeds both tested population sizes and intentionally suppresses all within-batch feedback, making the very large penalty unsurprising and of limited general interest.
- There is no independently calibrated batch baseline, no smaller-batch baseline, and no feedback-aware or asynchronous parallel baseline. Thus the secondary experiment does not answer a broadly meaningful algorithm-comparison question.
- Selection frequencies and effects stratified by population size, mutation rate, and budget are missing, preventing assessment of whether a small subset of configurations drives either result.
- The study is confined to deterministic 20-bit OneMax and a small 18-setting grid. This provides weak external validity and limited novelty for a competitive venue.
- The informative-regime check adds little because selecting among 18 settings specifically for proximity to 0.50 makes rates in [0.25, 0.75] highly likely; its scientific purpose and pre-outcome status are not established.
- The missing bibliography prevents evaluation of novelty and positioning relative to prior work.
- The local-only figure reference, unverifiable software versions, and uninterpretable runtime further reduce publication readiness.
- The report is substantially longer than warranted by the empirical contribution and repeats several caveats, which obscures the central results despite otherwise careful writing.

## Required fixes
- Release executable code, dependency and environment specifications, deterministic tests for budget accounting and update rules, all split-level calibration and validation outcomes, selected settings, and scripts that regenerate every statistic and figure.
- Either provide time-stamped documentary evidence that the 120-split protocol and all analysis rules were fixed before outcome inspection, or conduct a genuinely untouched, time-stamped preregistered replication. The latter is preferable.
- Define the population over which seed-based inference is intended and sample seed blocks accordingly in the replication. Otherwise, present intervals explicitly as conditional descriptive resampling summaries rather than population confidence intervals.
- Report the full distribution of split-level differences and add an appropriate distribution-free interval or hypothesis test for the median, with treatment of ties specified in advance. A coverage simulation tailored to the discrete design would further strengthen the analysis.
- Quantify how much of the observed calibration-validation gap can arise from finite-sample noise and the unequal 16-versus-128 sample sizes, for example through simulation under fixed known setting probabilities or a hierarchical/binomial measurement-error analysis.
- For any substantive serial-versus-batch claim, independently calibrate serial and batch methods using equal calibration resources and evaluate both on a new untouched validation set.
- Include batch sizes below the tested population sizes, especially 2, 4, and 8, and include at least one feedback-aware or asynchronous parallel baseline. Retain batch size 16 only as an intentionally stale-parent stress condition.
- Report setting-selection frequencies and stratify both the calibration gap and batch-minus-serial effect by selected population size, mutation rate, and evaluation budget.
- Add experiments on multiple preregistered objectives with greater dimensionality and varied structure, including at least deceptive or multimodal cases, before making a contribution claim beyond this specific OneMax demonstration.
- Restore a complete, verifiable bibliography and clearly position the narrow empirical contribution relative to existing work on hyperparameter-selection bias, winner's curse, and stale or delayed evolutionary updates.
- Provide an accessible archived figure and remove unsupported runtime and software-version details unless accompanied by reproducible environment and hardware metadata.
- Condense repeated caveats and organize the final manuscript around the estimand, protocol deviation, primary result, and narrowly scoped secondary transfer result.

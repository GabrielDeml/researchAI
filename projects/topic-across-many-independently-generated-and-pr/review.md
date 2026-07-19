# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about negative and unauditable findings: it explicitly records failure of the conjunctive preregistered hypothesis and withdraws the unsupported claim that standard errors were underestimated by at least a factor of three.
- The principal qualitative conclusion is sound: stride-1 windows of length 48 share 47 records, so strong adjacent dependence is expected even when seed-level experiments are independent.
- The report correctly distinguishes a realized disjoint-block autocorrelation from evidence of dependence and recognizes that 20 blocks provide only 19 adjacent pairs.
- The data-generating process, candidate rules, pooling procedure, eligibility criterion, tie-breaking rule, block definitions, and held-out evaluation protocol are described clearly.
- Selection and evaluation are properly separated: held-out data are not used for rule selection or threshold decisions.
- The report appropriately treats the 47/48 correlation as a mechanical baseline for a linear rolling mean rather than as an exact prediction for the nonlinear selected-uplift and threshold statistics.
- It correctly notes that the bootstrap mean decision rate cannot replace the observed decision rate and that extrema do not identify the bootstrap standard deviation.
- The interpretation of rule-selection frequencies is consistent with the data-generating process, under which R1 has a true subgroup uplift of 0.25 while the other rules average approximately 0.20.
- Limitations are comprehensive, and most claims in the Results section are appropriately descriptive rather than inferential.

## Weaknesses
- The central quantitative result is missing. The observed overlapping decision count and rate, naive standard error, bootstrap standard error, and variance-inflation ratio are all unavailable, so the fifth preregistered condition and a major stated purpose of the experiment cannot be evaluated.
- The report is not reproducible as submitted: executable code, seed-level sufficient statistics, bootstrap replicate output, software versions, and the referenced figure are absent.
- The preregistered disjoint-autocorrelation requirements are methodologically weak. Requiring an observed autocorrelation to fall within plus or minus 0.10 with only 20 blocks is not a calibrated test and has no stated type-I error, power, or scientific justification.
- The experiment uses only one master-seed realization. This supports a deterministic case study but provides no evidence about the frequency, variability, or generality of the reported behavior across independently generated datasets.
- The study does not provide the obvious simulation baselines needed to interpret its statistics. In particular, it omits null distributions for the two disjoint autocorrelations and repeated-sequence benchmarks for the decision-rate variance.
- The proposed seed-record bootstrap may be reasonable under the iid seed-level design, but its target, consistency, finite-sample behavior, and treatment of empirical-distribution uncertainty are not established. It is also not compared with direct simulation from the known data-generating process, which would be the natural gold standard here.
- No uncertainty is given for the bootstrap standard error or its ratio to the naive standard error. A point threshold such as 3.00 is especially fragile without Monte Carlo error or a confidence interval.
- The scientific novelty is limited. Mechanical dependence from heavily overlapping windows is well known, and the report supplies neither a new theoretical result nor a broad empirical characterization of the nonlinear selection and thresholding effects.
- Eligibility is effectively irrelevant in this design, and rule selection is nearly degenerate because R1 is selected in almost every block. Thus several advertised aspects of the study are not meaningfully exercised.
- The threshold of 0.25 coincides with the true uplift for R1, making the decision rate highly sensitive to estimation noise. This is not necessarily invalid, but its motivation and consequences should be explained.
- The held-out retention ratio is difficult to interpret as a generalization metric because it is a ratio with a noisy, selected denominator. Reporting the held-out minus development uplift and their joint distribution would be more stable and informative.
- Several result tables are incomplete, and the unavailable figure reportedly contains the missing standard-error comparison. Readers cannot verify whether the narrative, tables, and original graphic agree.
- The report devotes substantial space to documenting unavailable information but does not deliver a complete scientific analysis. As submitted, it reads more like an audit or revision memo than a finished competitive-venue paper.

## Required fixes
- Release executable analysis code, exact environment information, seed-level sufficient statistics or a deterministic regeneration script, all 953 and 20 block-level outputs, all 2,000 bootstrap replicate rates, and the referenced figure.
- Report the observed overlapping positive-decision count and rate, the exact naive standard error, the bootstrap standard error with its divisor convention, and the unrounded bootstrap-to-naive ratio.
- Quantify Monte Carlo uncertainty in the bootstrap standard error and variance ratio, using repeated bootstrap runs, an appropriate nested procedure, or an analytically justified Monte Carlo standard error.
- Repeat the full experiment across many independently generated master-seed sequences. Report sampling distributions and pass probabilities for all preregistered quantities rather than relying on one deterministic realization.
- Use direct simulation from the known data-generating process as the benchmark for the true sampling variance of the overlapping decision rate, and compare the seed-record bootstrap against that benchmark.
- Replace the plus-or-minus 0.10 disjoint-autocorrelation conditions with prospectively calibrated inference. Provide null distributions or confidence intervals tailored to 20 observations and to both continuous uplift and binary decision series.
- Clarify the estimand of the bootstrap: whether inference is conditional on the empirical collection of 1,000 seed records or unconditional over newly generated seed-level experiments.
- Provide complete summary tables with explicitly stated standard-deviation and quantile conventions, and add dependence-aware uncertainty for overlapping-series summaries where inferential comparisons are made.
- Add selection-free and linear-statistic controls so the mechanical effect of overlap can be separated from additional effects of pooled ratios, maximization across rules, rule switching, and thresholding.
- Evaluate multiple strides and block lengths, or substantially narrow the paper's claims to this single 48-seed, stride-1 case study.
- Report held-out uplift and the development-minus-held-out difference alongside the retention ratio, and avoid treating mean retention as an unbiased measure of generalization.
- Explain and justify the 0.25 decision threshold, including its equality to R1's population subgroup uplift and the resulting sensitivity of decision rates to sampling variation.
- Add a verifiable bibliography and position the contribution relative to established results on overlapping-window dependence, effective sample size, autocorrelation estimation, and bootstrap inference.

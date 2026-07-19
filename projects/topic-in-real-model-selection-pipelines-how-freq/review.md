# Peer review

**Score:** 5/10  _(after one revision pass)_

## Strengths
- The central proposition is mathematically correct: under a uniform random permutation of exactly tied maximal identifiers, the first tied identifier is uniform, so family j is selected with probability m_j/M.
- The derived frequency differences, odds ratios, and same-family/different-identifier probabilities follow algebraically from the stated assumptions.
- The reported Monte Carlo frequencies are consistent with the exact targets; the deviations from 8/9, 1/2, and 56/81 are plausible at the stated simulation size.
- The report is unusually candid about scope: it explicitly distinguishes a software check from empirical evidence about real datasets, optimizers, or hyperparameter-search pipelines.
- It correctly identifies the 40 fixtures as computational fixtures rather than independent scientific replications and appropriately limits the interpretation of the Wilson intervals.
- The distinction among identifier-level, semantic-configuration-level, and family-level estimands is useful and prevents the simplistic claim that uniform family selection is always preferable.
- The held-out-performance section correctly states that its results are algebraically induced by imposed performance gaps rather than independently discovered effects.
- The manuscript clearly documents the constructed multiplicities, tie rule, seeds, repetition counts, and acceptance criteria.

## Weaknesses
- The contribution is extremely elementary and its novelty is not established. The main theorem is a one-line symmetry/counting argument, while most of the manuscript elaborates a simulation whose answer is already known exactly.
- The implementation cannot be independently verified because executable code, dependency versions, machine-readable outputs, and a preserved artifact are absent. Reported assertions, counts, and plots therefore remain unauditable.
- The cited references are not supplied as a bibliography, and the manuscript does not demonstrate how the narrow result differs from existing discussions of order-dependent tie-breaking, duplicate trials, or multiplicity weighting.
- The displayed figure uses a workspace-local path and is not available in the submitted material, making part of the results presentation incomplete.
- The simulation studies only the degenerate case of two families with one semantic configuration each. It therefore cannot empirically distinguish semantic-configuration weighting from uniform family weighting, despite devoting substantial discussion to that distinction.
- The acceptance bands are arbitrary, very wide relative to Monte Carlo error, and apparently not backed by a verifiable preregistration. Passing them offers little evidence beyond detecting gross coding mistakes.
- The meaning of 'semantic configuration' is stipulated rather than operationalized. Byte-identical prediction arrays on two finite samples do not generally prove semantic equivalence, although the shared construction makes equivalence plausible in this synthetic example.
- The proposition should state more explicitly that the relevant identifiers are tied maximal candidates. Exact equality among nonmaximal candidates would not determine the selected family.
- The odds-ratio formulas omit boundary conditions. They require nonzero finite odds, such as 0 < m_j < M and 0 < q_j < 1; otherwise the expressions may be undefined or infinite.
- The empirical instability estimate is a plug-in functional of the same simulated frequency vector. It is not an independent two-draw experiment and has a small finite-sample bias that is not discussed.
- The manuscript is substantially longer than warranted by the technical content, with repeated caveats and restatements obscuring the concise formal contribution.
- Uniformly randomized encounter order is a strong assumption. Deterministic enumeration is common in actual search code, in which case the result is deterministic order dependence rather than identifier-proportional probability.

## Required fixes
- Provide a complete executable artifact containing the exact source code, locked dependency versions, generated machine-readable outputs, integrity checks, and the submitted figure; verify that it reproduces every reported count and statistic.
- Add a complete bibliography and a focused related-work analysis establishing whether the result or its framing is novel. If novelty cannot be established, recast the submission explicitly as a concise pedagogical or software-engineering note rather than a research contribution.
- State the theorem formally with all assumptions: the identifiers must be tied at the maximal validation score, their relative order must be uniformly random, the strict-improvement rule must retain the earliest maximal candidate, and odds-ratio formulas need explicit boundary cases.
- Either remove most of the redundant simulation apparatus or extend it to substantively nontrivial cases, including multiple families, unequal numbers of semantic configurations, partial duplication, nonuniform order distributions, and deterministic enumeration.
- Empirically separate semantic-configuration selection from uniform family selection using at least one design with unequal s_j; otherwise limit claims about those policies to the analytic discussion.
- Define how semantic duplicates would be identified in practice and distinguish shared generating configuration, identical model behavior, and coincidentally identical predictions on finite evaluation sets.
- Replace arbitrary acceptance ranges with exact reproducibility checks or analytically justified Monte Carlo tolerances, and clearly label any criteria that were not preregistered.
- Correctly characterize the instability statistic as a plug-in estimate, provide its exact finite-sample expectation or an unbiased estimator if retained, and state that no independent pairwise resampling experiment was performed.
- Condense the manuscript substantially so that the elementary proof, policy distinctions, assumptions, implementation check, and limitations are presented without repeated qualification.

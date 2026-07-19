# Peer review

**Score:** 4/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about its retrospective status, missing provenance, unverifiable prespecification, possible seed shopping, absent historical artifacts, and uncertain RNG call order.
- It correctly distinguishes a deterministic fixed-run threshold check from inference about the underlying tie probability.
- The interpretation of the reported tie rate is statistically restrained: the Wilson interval includes 0.15, and the count rule is correctly described as uncalibrated rather than as a valid hypothesis test.
- The data-generating process, candidate grid, integer scoring rule, optimizer definition, and wide-gap criterion are specified clearly.
- The reconstruction gives an explicit RNG implementation, call order, array shapes, artifact schemas, checksums, and executable analysis code.
- The report avoids the causal overclaim that discreteness alone produces the ties and acknowledges finite-sample variation and strongly correlated nested classifiers.
- The limitations and proposed follow-up experiments are comprehensive and scientifically appropriate.
- The claimed qualitative phenomenon is plausible: distinct population accuracies do not preclude exact equality of finite-sample correct-classification counts.

## Weaknesses
- The central numerical results are not actually reproduced or independently verified. The report repeatedly relies on a supplied aggregate record while admitting that the original code, data arrays, sample-level outputs, population-accuracy table, environment, and RNG trace are unavailable.
- The executable reconstruction is presented in place of executed evidence. There is no demonstrated output showing that the specified reconstruction produces 84 ties, 80 wide-gap ties, or the reported optimizer-participation counts.
- The displayed figure is not supported by supplied sample-level values. The text says the right panel is merely intended to show reconstructed gaps, so including it as a results figure is misleading unless the reconstruction was actually run and the generated artifact archived.
- The title and abstract foreground exact numerical findings even though those findings remain pending reproduction. The evidentiary status is disclosed, but the paper still reads partly as a completed empirical result and partly as a reconstruction protocol.
- The main contribution is very limited. Exact ties under integer-valued validation accuracy are elementary, and a single constructed DGP and grid provide little generalizable methodological insight.
- A single seed is acceptable for documenting one deterministic illustration, but it is inadequate for supporting claims about the underlying tie probability or robustness. The report itself recognizes this, leaving little substantive evidence beyond the one unverified run.
- The operational thresholds 0.15, 0.80, and 0.001 lack scientific, application-specific, or decision-theoretic motivation and may have been chosen after exploration.
- The historical aggregate target cannot establish that the supplied reconstruction corresponds to the historical implementation. Multiple stateful RNG call patterns are compatible with the prose but yield different outputs.
- The proposed workflow installs unconstrained current dependencies. Recording versions after execution helps auditing but does not provide a prospectively fixed, portable environment, and exact random-number behavior is not guaranteed across arbitrary NumPy versions or platforms.
- The full population-accuracy table is absent from the report, despite pairwise distinctness and within-tie population gaps being central to the claims.
- No literature context remains. Removing unidentified citations is preferable to inventing references, but an archival paper still needs a new, verifiable literature review to establish novelty and relation to existing work on discrete model-selection criteria and correlated classifier comparisons.
- Calling the deterministic fixed-run output an 'estimand' is conceptually awkward; it is a computational reproduction target, not an unknown statistical quantity.
- The Wilson intervals are descriptive and reasonable, but they do not address the more important selection uncertainty arising from the retrospectively chosen DGP, grid, seed, and thresholds.
- The manuscript is substantially overlong relative to the modest contribution, with extensive repetition of the same caveats and artifact descriptions.

## Required fixes
- Execute the exact reconstruction in a clean, archived environment and provide the complete generated artifacts, console output, dependency lock, platform metadata, and checksums.
- Report whether that execution reproduces 84 ties, 80 wide-gap ties, and all other aggregate targets. If it does not, replace the historical numbers in the primary Results section with the reconstructed results and clearly separate unmatched historical claims into a provenance appendix.
- Do not include the histogram or any other sample-level figure until it has actually been generated from archived sample-level output. Ensure the manuscript figure and its checksum correspond to the released artifact.
- Include the complete 11-row population-accuracy table, quadrature error estimates, minimum pairwise difference, and sufficient numerical precision to audit every wide-gap classification.
- Add independent computational validation, such as a second implementation or targeted unit tests for the DGP, threshold predictions, score matrix, optimizer sets, population integrals, and Wilson intervals.
- Provide a pinned environment specification rather than unconstrained installation commands, and state the exact Python, NumPy, SciPy, pandas, Matplotlib, operating-system, and architecture versions used for the accepted run.
- Reframe the paper explicitly as either a reproducibility/provenance report or a completed simulation study. If the historical run cannot be recovered, remove language that presents its aggregate values as established experimental results.
- If any claim about an underlying tie probability is retained, conduct a prospectively specified Monte Carlo study using many independently assigned streams, report Monte Carlo uncertainty, and use a calibrated one-sided procedure or confidence bound for comparison with 0.15.
- Either justify 0.15, 0.80, and 0.001 on substantive grounds or label them throughout as post hoc illustrative thresholds and avoid treating threshold crossing as a scientific hypothesis confirmation.
- Add a verifiable bibliography and concise literature positioning sufficient to support the novelty claim.
- Shorten the manuscript substantially by consolidating repeated caveats, moving code and detailed artifact schemas to supplementary material, and focusing the main text on the validated result and its limited interpretation.

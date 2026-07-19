# Peer review

**Score:** 5.2/10  _(after one revision pass)_

## Strengths
- The central conceptual correction is sound: under the stated data-generating process, both identity and the constant-0.5 predictor are population calibrated, while proper scores favor identity because it retains refinement.
- The report correctly identifies prediction-dependent finite-sample behavior of fixed-bin ECE as a major confound. A constant occupies one bin, whereas identity accumulates absolute sampling deviations across many bins.
- The nested-grid argument is logically valid for the realized samples: because every full-grid winner is among the same three constants, a three-candidate grid with preserved tie order would reproduce all reported selections and aggregate selected-candidate results.
- The report appropriately rejects a distinct 441-candidate multiplicity interpretation and does not present the additional 420 candidates as causally responsible for the observed effect.
- The algebraic redundancy between the sign of the mean paired reduction and the ordering of the two mean ECE values is correctly recognized.
- The independent-evaluation result is reported honestly as inconclusive rather than spun as established harm; the interval includes zero.
- The population Brier-score and log-loss calculations appear correct: identity has Brier score 1/6 and log loss 1/2, while constant 0.5 has Brier score 1/4 and log loss log(2).
- The random-stream construction, grid, binning rule, tie-breaking rule, sample sizes, and distinction between per-sample averaging and pooling are described unusually clearly.
- The limitations section is candid about missing baselines, missing stratification, absent references, lack of precision planning, and limited generalizability.

## Weaknesses
- The central empirical constant-0.5 baseline is missing even though the complete deterministic seed scheme and experimental specification are given. This is not an irrecoverable limitation: the authors can and should rerun the simulation. Publishing without this baseline leaves the primary bin-occupancy interpretation insufficiently quantified.
- The report provides exact numerical results to many decimal places but no executable code, split-level data, candidate-level objectives, or auditable artifact. The numbers therefore cannot be independently verified from the submission.
- There is an unresolved data-retention inconsistency. Split-level standard deviations, a split-level figure, a win count, and selected-candidate counts are reported, yet candidate-stratified summaries are said to be impossible because linked split-level values were not retained. The exact retained data structure must be explained, and the underlying outputs should be released.
- The main causal-sounding interpretation that bin geometry is the primary explanation is plausible but not directly isolated. The report does not empirically compare identity with fixed constant 0.5 across all splits, quantify expected ECE as a function of occupied bins, or separate fixed-estimator bias from selection among the three constants.
- The three-candidate equivalence rules out an incremental contribution from the other 438 candidates on these realized samples, but it does not establish that grid size has no effect in repeated experiments. The report is mostly careful about this distinction, but some statements could still be read too broadly.
- The normal-approximation interval across only 80 splits is weakly justified, especially because the evaluation reductions arise from a mixture of three selected candidates and may be non-normal. A t interval, bootstrap interval, candidate-stratified analysis, and preferably more independent split families are needed.
- The hypothesis appears highly specific, including an arbitrary 0.08 threshold and deterministic seed family, but no provenance, preregistration, or ex ante power calculation is supplied. It is unclear whether the hypothesis and threshold were genuinely fixed before examining results.
- The reported aggregate independent mean combines calibrated constant-0.5 selections with population-miscalibrated off-center constants. Without stratification, that mean is difficult to interpret and may conceal qualitatively different behavior.
- Identity winning only 20 of 80 splits despite having a negative mean paired reduction strongly indicates a magnitude-versus-frequency mixture. This deserves direct decomposition rather than being left as an unresolved observation.
- The manuscript contains no real bibliography or engagement with prior work. The underlying observations about histogram-ECE bias, calibration versus refinement, and proper scoring rules are established concepts, so novelty cannot be assessed or supported.
- The novelty is currently limited. The strongest contribution is a forensic reinterpretation of one simulation, not a general methodological result, theoretical characterization, or broad empirical study.
- The figure is referenced through a workspace-local path and is not available as a reproducible publication artifact.
- Reporting many decimal places overstates meaningful precision given Monte Carlo uncertainty and the absence of an auditable implementation.

## Required fixes
- Rerun the fully specified deterministic experiment and report, for every split, identity ECE, selected-candidate ECE, fixed constant-0.5 ECE, selected parameters, reused reductions, independent reductions, Brier scores, and log losses.
- Provide executable source code, environment or lock files, raw split-level outputs, candidate-order and tie-breaking tests, and commands that regenerate every table and figure exactly.
- Add the fixed constant-0.5 baseline as a primary comparator on both reused and independent samples. Report paired means, standard deviations, uncertainty intervals, win rates, and distributions.
- Report candidate-stratified results for (0,0), (0,0.2), and (0,-0.2), including reused and independent paired reductions and uncertainty. Explicitly show how the 62/12/6 mixture produces the aggregate negative evaluation mean and the 20/80 identity win count.
- Empirically separate three effects using matched samples: the baseline finite-sample ECE difference between identity and fixed constant 0.5, selection among the three constants, and expansion from three constants to the full 441-candidate grid.
- Include prespecified nested-grid controls, especially one candidate, the three observed constants, all 21 constants, and the full grid. Add grids excluding a=0 if the paper intends to discuss generic search multiplicity.
- Use uncertainty procedures appropriate for paired, potentially non-normal mixture data and increase the number of independently seeded splits according to an ex ante precision target. Distinguish Monte Carlo uncertainty over calibration selections from finite evaluation-sample noise.
- Clarify whether the hypothesis, 0.08 threshold, grid, bin count, and seed family were preregistered or chosen before results were observed. If not, label the hypothesis and analysis as retrospective.
- Add a real literature review and complete bibliography covering finite-sample bias of histogram ECE, prediction-dependent bin occupancy, calibration-versus-refinement decompositions, proper scoring rules, and post-selection evaluation.
- Moderate the interpretation until the baseline and decomposition are supplied: the current evidence establishes a realized fixed-bin ECE effect and rules out an incremental role for the additional full-grid candidates on these samples, but it does not yet quantify a general occupancy mechanism or repeated-sampling grid-size effect.
- Replace the inaccessible figure path with a bundled figure and reproducible generation script, and report numerical precision commensurate with the simulation uncertainty.

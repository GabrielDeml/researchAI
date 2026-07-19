# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about what the single realization can and cannot establish. It explicitly avoids treating the observed attenuation as proof of a systematic winner's curse.
- The narrow numerical claims are internally consistent: the reported uplift, rule-effect differences, and retention ratio follow from the stated effects.
- The data-generating process, checkpoint schedule, censoring rule, eligibility rules, split, seed initialization, tie-breaking order, and selection criterion are described with substantial precision.
- Eligibility is defined using reference-arm trajectories only, and intervention outcomes are paired on the same eligible seeds, avoiding direct outcome-based eligibility screening.
- The proposed attempted-reference ledger is a sound transparency practice because it retains non-grokking, censored, and ineligible attempts rather than silently dropping them.
- The report correctly recognizes that the selected and broad rules define different populations, so their effect difference cannot be identified as selection bias alone.
- Important limitations are disclosed rather than hidden, including the small selected samples, lack of verified preregistration, ratio instability, administrative censoring, and absence of repeated simulations.
- The distinction between complete attempt accounting and the separate evidentiary role of the holdout comparison is clear and conceptually correct.

## Weaknesses
- The central empirical result is based on only one synthetic realization with 24 selection and 24 holdout seeds, and the selected rule contains only 11 pairs per split. This is inadequate for characterizing either the frequency or magnitude of holdout attenuation.
- No uncertainty analysis is provided. It is therefore unknown whether the change from a 0.0712 selection difference to a 0.0023 holdout difference is unusual under ordinary sampling variation.
- The main contrast does not isolate a winner's curse. Subtracting the broad-rule effect from the selected-rule effect compares different eligible populations, and the constructed data-generating process permits those populations to have genuinely different effects.
- The synthetic model explicitly builds in an intervention benefit and associations among reference timing, eligibility, and paired outcomes. Without null, homogeneous-effect, or alternative-generating-process controls, the demonstration says little about generic specification-search behavior.
- The report does not estimate fixed-rule population effects. Consequently, it cannot measure the actual optimism of the winning rule's selection estimate relative to that same rule's population or independent-test effect.
- The 30% uplift threshold is crossed only narrowly, yet no independently verifiable preregistration or immutable pre-analysis artifact is supplied. The threshold and other design choices must therefore be treated as retrospective.
- The named trajectory, ledger, rule-result, and summary files are not supplied, nor are executable code, environment details, or hashes. The reported outputs, draw order, ledger timing, and completeness cannot be independently verified.
- Only the broad and winning-rule rows are reported. Omitting the other 11 rule results prevents assessment of the search landscape, near-ties, effective multiplicity, and sensitivity of the winner.
- The six-pair eligibility minimum is weak for a ratio estimand and is not justified by precision or power considerations. No sensitivity analysis examines larger minimum sample sizes.
- The retention ratio is unstable when the selection excess is small and has no uncertainty interval. Presenting 3.23% to several significant digits gives more numerical precision than the design supports.
- The deterministic first-half versus second-half split is acceptable under the stated independent generator construction, but a single split gives no information about split sensitivity.
- The broad rule happens to include every seed in both splits, making it effectively an all-seed comparator in this realization. This limits what is learned about broad eligibility rules more generally.
- Novelty is limited. The substantive phenomenon is a standard consequence of specification search followed by holdout evaluation, while the ledger contribution is primarily a reporting and provenance recommendation.
- The manuscript is considerably longer than warranted by the amount of evidence and repeatedly restates the same caveats. The core contribution could be communicated more clearly as a compact reproducible demonstration.

## Required fixes
- Release executable code and all named output artifacts, including the complete trajectory data, attempted-reference ledger, full 26-row rule table, summary file, figure-generation code, exact software environment, and cryptographic hashes.
- Repeat the entire procedure over many independently generated 48-seed blocks and report distributions of winning-rule identity, eligible sample size, selection uplift, held-out performance, retention, and threshold-crossing frequency.
- Add null and homogeneous-treatment-effect simulations in which eligibility cannot identify genuine effect heterogeneity. These controls are necessary to separate specification-search optimism from subgroup-effect differences.
- For every fixed rule, estimate its population effect using a very large independent simulation. Quantify winner's-curse optimism by comparing the selected rule's selection estimate with the independent population or large-test estimate for that same rule, rather than relying primarily on a selected-versus-broad contrast.
- Provide paired, selection-aware uncertainty analyses. Rule selection must be repeated within each bootstrap replicate or simulation block; intervals conditional only on the observed winning rule are insufficient.
- Report all rule-level restricted means, effects, eligible counts, censoring counts, and uncertainty on both splits, not only the broad and winning rules.
- Perform prospective sensitivity analyses for the minimum eligible-pair requirement, restriction horizon, broad-rule definition, train/validation thresholds, deadlines, and alternative train/holdout splits.
- Justify or replace the ratio-based relative-effect objective. At minimum, also report absolute paired RMST differences, denominator distributions, and the sensitivity of rule selection to the estimand.
- Either provide independently verifiable evidence that the protocol was prospectively fixed or consistently label all thresholds and decision criteria as retrospectively documented exploratory choices.
- Reframe the contribution explicitly as a reproducible methodological illustration unless the repeated simulations and controls support a broader claim. Avoid treating the 3.23% retention value as substantively meaningful without uncertainty.
- Shorten the manuscript by consolidating repeated caveats and focusing the main text on the estimand, the complete reproducible workflow, the full results, and the simulations needed to identify search-induced optimism.

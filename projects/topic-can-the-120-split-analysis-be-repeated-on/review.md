# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about what the experiment can and cannot establish. It correctly frames the main result as a deterministic implementation/property test rather than evidence about real machine-learning pipelines.
- The central logical claims are sound: selecting the minimum identifier from an unchanged exact-maximizer set is permutation invariant, whereas first-encountered argmax is order sensitive when multiple exact maxima exist.
- The construction clearly distinguishes identifier instability, optimizer-label instability, and evaluation instability, and explicitly acknowledges that the latter two were engineered rather than implied by tie-breaking alone.
- The deterministic seeds, software versions, score construction, tie sets, optimizer assignments, evaluation mapping, and decision thresholds are described with substantial specificity.
- The combinatorial calculations for selection among a four-way tie, including the multinomial model and probability of observing all four tied configurations over 25 independent uniform permutations, are appropriate.
- The report appropriately rejects population inference from the deterministic dataset IDs, shared permutations, overlapping splits, and degenerate bootstrap intervals.
- The numerical results, as described, are consistent with the engineered design and the conclusions are generally restrained rather than spun as broad empirical findings.
- The limitations section identifies most major threats, including missing artifacts, lack of verified preregistration, engineered outcomes, dependence, unnecessary resampling, missing bibliography, and limited novelty.

## Weaknesses
- The principal result is an elementary consequence of the definitions. Repeating it over 60 constructed datasets and 25 permutations adds little scientific evidence beyond a unit or property test, so novelty and contribution are too limited for a competitive research venue.
- None of the central computational claims is independently auditable because the code, protocol JSON, permutation matrix, selections file, generated data or generation scripts, logs, and referenced figure were not supplied. Reported hashes cannot be checked without the hashed files.
- The optimizer-label and evaluation effects are largely guaranteed or strongly favored by construction: every tie set contains both optimizer labels, and tied configurations are deliberately assigned distinct evaluation accuracies spanning a wide range. The resulting 60-of-60 outcomes therefore provide little evidence beyond confirming that the construction worked.
- The claimed freezing of selections before evaluation-array generation offers weak protection against design bias because the deterministic evaluation mechanism was already known and deliberately chosen to separate configurations. It prevents one narrow form of computational leakage but not outcome-oriented construction.
- The 120 overlapping stratified shuffle splits are methodologically unnecessary for fixed predictors on a fixed evaluation sample. They obscure exact full-sample accuracies, introduce Monte Carlo variation, and do not supply independent replication or meaningful uncertainty.
- The sample sizes of 60 datasets and 25 permutations have no inferential target or substantive justification. Given the deterministic cycling of tie sets and reuse of the same permutation matrix, the nominal 1500 cases substantially overstate the amount of independent variation.
- The aggregate results omit the complete per-dataset, per-permutation selection table. Consequently, reported counts such as 1170 identifier changes and 790 optimizer-label changes cannot be reconstructed or assessed for artifacts of the shared permutation matrix.
- The bootstrap is not merely uninformative but conceptually mismatched to the design because dataset IDs are deterministic construction indices rather than draws from a defined population.
- No null or comparative conditions are included, such as equal evaluation performance among tied configurations, smaller or randomly signed differences, random optimizer-label assignments, near-ties, or an actual fitted-model pipeline. Without these, the illustrated consequences are calibrated to a favorable scenario only.
- The manuscript devotes extensive space to qualifications and procedural detail while providing little substantive analysis beyond what can be derived exactly. This makes it clear but disproportionately long relative to its contribution.
- The missing bibliography and unavailable figure make the submission incomplete as a publication artifact.
- The internal timestamp and reported digests may document claimed file identities, but in their current unavailable and externally untimestamped form they provide no independently verifiable evidence of prespecification.

## Required fixes
- Release a complete, executable reproducibility package containing the exact protocol JSON, source code, dependency lockfile or container, permutation matrix, selections file, deterministic data-generation code or generated arrays, logs, figure, and a verification script that checks every digest and reported numerical result.
- Provide the complete dataset-by-permutation results, including each permutation order, tied set, total-order choice, first-encountered choice, optimizer labels, split-average estimates, full-sample estimates, and all threshold indicators.
- Replace the 120-split average as the primary outcome with direct full-sample evaluation of the fixed predictors. If the split estimator is retained, report its difference from the full-sample value and quantify its Monte Carlo variability across independently generated split collections.
- Either reposition the work explicitly as a software-testing or reproducibility note with substantially reduced empirical claims, or add a genuinely non-engineered evaluation involving fitted models and a prespecified stochastic or real-data design in which tie frequency, optimizer composition, and post-selection performance differences are not forced.
- Add prespecified control conditions in which tied configurations have equal evaluation performance, narrower differences, and randomly signed or independently generated differences. Include random or independently varied optimizer-label assignments rather than forcing a two-versus-two composition in every tie set.
- Use independently generated permutation collections across independently generated datasets, or analyze all relevant order classes exactly. Clearly separate exact combinatorial results from finite simulation checks and avoid treating reused dataset-permutation cases as independent evidence.
- Remove the dataset-ID bootstrap from inferential presentation unless a defensible sampling population and sampling mechanism are introduced. For the current deterministic design, report exact finite-design counts only.
- Restore a complete, verifiable bibliography and supply the referenced figure at the stated path, with the underlying plotting data and generation code.
- Clarify the contribution relative to a conventional unit test: identify what implementation failure modes the test can detect, demonstrate at least one failing implementation if relevant, and explain why the proposed test framework offers value beyond the immediate mathematical definition.
- Obtain externally verifiable temporal provenance for any future claim of preregistration, such as a public repository commit, registry entry, signed archive, or trusted timestamp. Otherwise retain only the narrower claim that the protocol was locally recorded.

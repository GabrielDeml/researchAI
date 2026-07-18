# Peer review

**Score:** 4/10  _(after one revision pass)_

## Strengths
- The central causal explanation is sound: sharing a mutable RNG couples each algorithm to execution order, whereas reconstructing a generator from a fixed algorithm-and-seed key removes that coupling in deterministic single-threaded code.
- The conclusions are unusually well bounded. The report explicitly avoids claims about statistical independence, formal substream disjointness, concurrency, cross-platform reproducibility, optimization superiority, and generalization beyond the tested cases.
- The algorithmic configuration, stopping rules, duplicate handling, tie-breaking, RNG construction, and intended serialization format are described in substantial detail.
- The report correctly identifies that duplicate ratio is algebraically determined by attempt counts in these successful fixed-target runs and does not present it as independent corroborating evidence.
- The shared-generator baseline is clearly defined as one generator per seed shared between algorithms, avoiding the ambiguity of a single global stream.
- The reported aggregate results are internally consistent with the hypothesis and decision rule: 30/30 keyed rows are claimed identical, while a column-specific shared-stream outcome exceeds the stated 24/30 threshold.
- The limitations section is candid about missing artifacts, low novelty, arbitrary threshold choice, fixed deterministic seed cases, and the essentially sanity-check nature of keyed-stream equality.

## Weaknesses
- The decisive empirical evidence is absent. No executable source, CSV files, heatmap matrix, manifest, environment lock, or reproduction command is supplied, so none of the hashes, counts, implementation details, or plots can be audited.
- As submitted, the results are assertions rather than artifact-validation results. A paper centered on reproducibility cannot substantiate its principal claim without a reproducible artifact.
- The keyed-stream result is nearly tautological for deterministic single-threaded software: recreating the same generator from the same key for an isolated run should produce the same record regardless of the order in which isolated runs are invoked. This provides limited scientific novelty beyond a useful engineering demonstration.
- The shared-generator condition intentionally gives each algorithm a different segment of the random sequence after order reversal. Its order dependence is therefore expected by construction rather than a surprising empirical discovery.
- Only 30 consecutive seed identifiers and one master seed were tested. This is sufficient to demonstrate the claimed behavior for those exact cases but not to characterize how frequently shared-stream records change more generally.
- The 80% threshold is arbitrary, lacks calibration or theoretical motivation, and its claimed pre-specification cannot be verified. It adds little to the more direct demonstration that the records differ.
- The Wilson intervals have weak interpretive value because seeds 0 through 29 were fixed deterministic cases rather than an explicitly sampled population. Presenting inferential intervals risks implying generalization that the design does not support.
- There are no comparisons with standard alternatives such as SeedSequence spawning, counter-based generators, formal stream splitting, or explicit operator-level keys. This further limits novelty and practical guidance.
- The missing bibliography prevents evaluation of positioning and priority relative to established reproducible-computing and random-stream-allocation practices.
- The test does not exercise concurrency, nondeterministic collection order, platform differences, failure branches, or other settings where reproducibility is genuinely difficult.
- Byte-identical CSV equality tests serialization and deterministic execution jointly, but the report does not separately test semantic record equality, making it difficult to distinguish RNG allocation effects from possible serialization or ordering defects if the artifacts eventually disagree.

## Required fixes
- Release the complete executable implementation and all four claimed CSV artifacts, including the exact files corresponding to the stated SHA-256 hashes.
- Provide the heatmap source matrix, plotting code, schema-versioned manifest, source commit and source hash, dependency lock file, platform metadata, and a documented one-command reproduction procedure.
- Have an independent party run the package in the specified environment and verify the three reported hashes, all 30 row-level comparisons, all eight column-specific counts, failure counts, and the heatmap against the raw CSV data.
- Add automated tests that reconstruct each keyed run in both invocation orders and verify both semantic field equality and canonical byte-level serialization.
- Restore a complete, verifiable bibliography and position the work against SeedSequence spawning, stream splitting, counter-based RNGs, and established reproducible parallel-computing practices.
- Either remove the Wilson intervals and frame all rates strictly as descriptive results for the enumerated seeds, or define a defensible seed-sampling population and expand the experiment across substantially more seeds and multiple master seeds.
- Remove or justify the 80% threshold with documented pre-specification and a scientific rationale; otherwise report the column-specific change counts without converting them into an arbitrary pass/fail criterion.
- Reframe the contribution explicitly as a small artifact-engineering demonstration unless broader experiments are added. Any stronger contribution claim should include comparisons with standard RNG-allocation alternatives and tests involving actual concurrent execution with deterministic result collection.
- Exercise and verify the initialization- and offspring-failure branches, since their behavior is currently specified but entirely untested.

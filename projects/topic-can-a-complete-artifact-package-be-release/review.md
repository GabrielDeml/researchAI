# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about the narrow scope of its evidence and consistently avoids interpreting 40 of 40 engineered detections as a population-level 100% detection rate.
- The hypothesis and decision rule are explicit, including the requirement that mutants remain parseable and pass checksum-only validation before counting as relational detections.
- The distinction between same-generator clean runs, independent implementations, deterministic test-suite coverage, and statistical sampling is methodologically correct.
- The described data-generation process, persisted-value arithmetic, cross-file relationships, mutation classes, and validation rules are sufficiently concrete to make the intended experiment understandable.
- The report correctly identifies the threat-model limitation of an unauthenticated manifest that an actor can regenerate after modifying files.
- M8 is a useful integration test showing why recomputation from raw observations adds coverage beyond agreement among derived representations.
- The limitations section is comprehensive and accurately identifies missing artifacts, incomplete environment locking, lack of implementation independence, untested rules, tolerance concerns, and omitted baselines.
- The writing is clear and technically careful, and the narrow final claim does follow from the reported aggregate outcomes if those outcomes are accurate.

## Weaknesses
- The central empirical results are not independently verifiable because the source code, generated datasets, mutation specifications, manifest schema, dependency lock, raw per-case records, logs, and referenced figure were not supplied.
- No cryptographic identifier identifies the alleged artifact state, so even later-provided files could not be shown to be the files used for the reported execution.
- The work does not currently constitute a reproducible artifact package despite that phrase appearing in the title; only an intended package design is described.
- All mutants were hand-designed around the validator's named invariants, copied from one base dataset, and concentrated on five early seeds. This establishes narrow regression-test coverage rather than robustness to realistic or unanticipated corruption.
- R1 and R6 were never exercised by a failing mutant, so the campaign does not even provide negative-case evidence for every advertised relational rule.
- The 20 clean cases test only self-consistency with the same generator and arithmetic conventions. They provide little evidence about false positives on independently generated or merely differently serialized valid outputs.
- Implementation independence is absent or at least undocumented. Shared parsing, arithmetic, ordering, or mapping helpers could cause generator and validator errors to agree silently.
- The checksum-only comparison is weak by construction because every mutant receives a newly generated unauthenticated manifest. It is a threat-model illustration, not a meaningful competitive baseline.
- There are no comparisons with schema-only checks, existing dataframe or relational validation tools, derived-only validation, or authenticated manifests.
- The absolute tolerance of 5e-10 is not justified through range analysis or boundary tests, and portability across arithmetic orders, interpreters, NumPy versions, and platforms is untested.
- The dependency environment is not fully locked: jsonschema and transitive dependencies are not shown in the lock, distribution hashes are absent, and the supported Python range exceeds the single tested interpreter.
- The one-command workflow was not demonstrated from a clean checkout, and it is unclear whether it invokes the newly created virtual environment rather than an ambient interpreter.
- Novelty is low. The work combines established schema, checksum, referential, aggregate-recomputation, and representation-consistency checks without a new validation method or substantive comparison to prior systems.
- The title and framing still overstate completeness relative to the actual submission, even though the body later acknowledges that the artifact itself is absent.
- Reported timing is uninterpretable without hardware, logs, repetitions, or a clear measurement protocol.

## Required fixes
- Provide the complete repository and release payload, including all source files, manifest schema, dependency specification, Makefile, README, clean outputs, all 40 mutants or deterministic mutation recipes, raw per-case results, execution logs, and the figure.
- Publish a stable commit or release archive with a cryptographic digest and a complete SHA-256 inventory covering repository-level code and infrastructure as well as output data.
- Demonstrate `make reproduce` from a fresh isolated checkout in a specified container or virtual machine, recording the exact interpreter path, installation transcript, stdout and stderr, exit status, generated file inventory, and comparison with reference hashes.
- Replace the incomplete dependency description with a fully resolved lock including jsonschema, all relevant transitive dependencies, distribution hashes, a precise Python constraint, and explicit invocation of the environment's interpreter.
- Release machine-readable per-case outcomes containing mutation identifiers, exact targets and magnitudes, parse and checksum results, failed relational rules, and expected outcomes committed independently of the validator run.
- Add failing mutants for R1 and R6 and broaden testing to multiple independently generated bases, randomized target rows and metrics, prespecified mutation magnitudes, combined mutations, and structurally valid corruptions not directly constructed as inverses of individual rules.
- Add false-positive tests using an independently written generator and semantically valid variations such as row reordering, alternative CSV formatting, metric-order handling, Unicode identifiers, signed zero, and supported edge cases.
- Provide an independent oracle or second validator implementation for key aggregates and mappings, and document or remove shared helpers that could create circular agreement among generation, mutation, and validation.
- Test numerical discrepancies below, at, and above the tolerance across realistic and extreme value scales and arithmetic orders; justify the policy or use a documented absolute-plus-relative comparison where appropriate.
- Evaluate stronger and more informative baselines, at minimum schema/structural validation alone, derived-file agreement without raw recomputation, an authenticated or externally anchored manifest, and one established dataframe or relational validation framework.
- Revise the title and contribution statement to describe a synthetic relational-validation test design unless and until a complete, independently reproducible artifact is actually supplied.
- After supplying the evidence, report only claims directly supported by reproduced runs; retain the current caveats against generalizing the engineered 40-of-40 result.

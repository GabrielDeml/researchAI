# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The central claim is narrowly and correctly formulated: two checkpoints authenticated under the same pinned key, with equal sizes and unequal roots, satisfy the stated alert predicate.
- The conclusions generally follow from the described experiment and avoid claiming statistical significance, operational detection probability, append-only behavior, completeness, freshness, or eventual fork exposure.
- The report clearly distinguishes detector correctness from the opportunity to compare conflicting checkpoints, which is essential in split-view threat models.
- The cryptographic serialization, domain-separated Merkle hashing, proof validation rules, deterministic record generation, and attack construction are described with useful precision.
- The report is unusually candid about the experiment being true largely by construction and about the inclusion-only baseline lacking the information needed to detect equivocation.
- It explicitly identifies shared-implementation confounding, weak controls, fixed tree shape, assumed key distribution, limited malformed-input testing, and absent reproducibility materials.
- The reported attack and control outcomes are internally consistent with the scenario construction and alert definition.
- The distinction among authentication, membership, consistency, completeness, freshness, and eventual exposure is conceptually sound and clearly presented.

## Weaknesses
- The contribution is nearly tautological: the detector is defined to alert on equal-size unequal-root authenticated pairs, and every attack case is constructed to satisfy exactly that condition. Repeating this 64 times adds little scientific evidence beyond a few implementation tests.
- No executable source, test vectors, raw outputs, dependency lockfile, artifact hashes, or independently available figure is supplied. Consequently, none of the claimed execution results can be verified, and the work is not reproducible as submitted.
- The bibliography is absent. Unresolved citation placeholders and unsupported assertions that the predicate is standard are unacceptable for publication, especially when novelty depends on comparison with prior transparency-log work.
- The inclusion-only baseline is information-starved by design and is not a meaningful competitive baseline. The reported absolute alert-rate difference is mathematically correct but scientifically uninformative because one method is denied the second checkpoint required by the task.
- Generator, signer, proof constructor, serializer, parser, and verifier apparently share one implementation. Correlated defects could make all positive tests pass while implementing the intended specification incorrectly.
- The controls test only identical copies of one checkpoint. They provide almost no evidence about false positives under benign tree growth, stale or replayed checkpoints, independently encoded inputs, message duplication, or parser variation.
- The two negative tests are far too limited to substantiate robustness of cryptographic input handling. Important boundary, canonicalization, length, index, encoding, and parser-differential cases remain untested.
- Only complete 64-leaf trees are exercised. This avoids the difficult interoperability issues of arbitrary sizes, odd-node handling, empty trees, and consistency proofs.
- The report invokes an implementation and a completed run without supplying evidence that the implementation or run exists beyond aggregate claims. The prose specification is detailed, but it is not a substitute for executable evidence.
- The sample count of 64 has no methodological role. The scenarios vary superficial inputs while preserving the same decisive condition, so presenting aggregate rates risks giving a stronger empirical impression than warranted despite the caveats.
- Novelty is insufficient for a competitive research venue. At most, the work currently constitutes a conformance-test specification or pedagogical demonstration of a standard observation.
- The manuscript is substantially overlong and repetitive relative to its limited result. The same caveats recur across the abstract, hypothesis, results, and limitations, obscuring the small core contribution.

## Required fixes
- Publish the complete executable artifact: source code, exact environment and dependency lockfile, clean-run instructions, public key, all generated vectors, scenario-level outputs, negative-test inputs, figure source and rendering, and cryptographic hashes of artifacts.
- Provide a complete, verified bibliography and a citation-level related-work comparison covering Certificate Transparency split-view defenses, checkpoint gossip, consistency proofs, monitors, witnesses, and cross-logging.
- Either reposition the submission explicitly as a short conformance specification or substantially expand the empirical contribution. The current tautological test is not sufficient as a full competitive research paper.
- Add at least one independently developed implementation, preferably in another language and using a different cryptographic library, and demonstrate agreement on checkpoint bytes, roots, proofs, signatures, and comparison decisions using published vectors.
- Replace or supplement the inclusion-only baseline with meaningful transparency mechanisms, such as retained checkpoint histories, consistency-proof verification, multi-peer gossip, monitoring, witness cosigning, or cross-logging. Do not characterize the current predicate comparison as a practical detection improvement.
- Define and test arbitrary tree sizes, including empty, singleton, non-power-of-two, and large trees, with an explicit odd-node or standard Merkle-tree rule and append-only consistency-proof semantics.
- Add benign unequal-size controls, valid and invalid consistency proofs, replay and rollback cases, stale checkpoints, duplicate and reordered delivery, independently serialized artifacts, and checkpoint-history cases.
- Build a systematic malformed-input and boundary-value suite covering lengths, hexadecimal canonicalization, integer bounds, trailing bytes, missing or extra proof nodes, wrong side markers, manipulated indices, malformed signatures, invalid UTF-8, duplicate fields where applicable, and parser differentials.
- Clearly separate formal correctness of the predicate from observed implementation behavior. A small formal argument can establish the former; executable tests should focus on failure-prone serialization, parsing, interoperability, and adversarial edge cases rather than 64 repetitions of the same logical condition.
- Remove or de-emphasize the absolute attack-alert-rate difference unless a fair task definition and competitive baselines are introduced.
- Condense the manuscript substantially, eliminating repeated disclaimers while retaining the important scope restrictions in one clear threat-model section and one limitations section.

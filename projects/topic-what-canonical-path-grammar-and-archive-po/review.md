# Peer review

**Score:** 4/10  _(after one revision pass)_

## Strengths
- The central numerical conclusions follow from the stated corpus and validator definitions: exact-key comparison necessarily misses the constructed ancestor and implicit-prefix cases, while the trie predicates are designed to reject them.
- The report is unusually candid about the weakness of the baseline, specification-derived labels, absence of extraction experiments, lack of algorithmic novelty, and inability to generalize beyond the corpus.
- Claims are appropriately narrow and generally avoid equating conformance on synthetic examples with security, completeness, or real-world exploit prevention.
- The archive-wide trie analysis is order-independent by construction, and testing both orders of every two-entry manifest is appropriate for the limited corpus.
- The canonicalization grammar, validator predicates, threat-model assumptions, corpus categories, and aggregate results are described clearly enough to understand the intended experiment.
- The report distinguishes policy choices from universal facts, particularly for implicit-directory alias rejection and canonical merging.
- The limitations and follow-up questions accurately identify most of the major threats to validity.

## Weaknesses
- The work is not independently reproducible or auditable. No code, manifests, oracle cases, raw outcomes, environment lockfile, Unicode version, figure-generation source, or hashes are provided. Consequently, even the simple reported counts cannot be verified.
- The experiment is predominantly a circular conformance exercise: labels were derived from the same predicates implemented by the trie, and examples were constructed to trigger those predicates. Achieving 100% rejection therefore provides little independent evidence of correctness.
- The exact-key baseline is intentionally incapable of representing the main tested distinctions. Its 96/144 conflict acceptance result is largely predetermined by construction and is not a meaningful comparison against a plausible archive validator.
- There is little empirical or algorithmic novelty. Component tries for prefix conflicts are standard, and no comparison is made with a sorted-path scan, an explicit-type-aware validator, canonical-merging policies, existing library safeguards, or prior work.
- The corpus is very small in structural diversity despite having 192 serialized streams: it consists of only 96 hand-built, two-entry manifests, with the second stream for each manifest merely reversing order. The stream count overstates the amount of independent evidence.
- No filesystem extraction was performed, so the practical consequences motivating ancestor, symlink, and alias rejection remain untested. This is especially important because the implicit-alias class is policy-dependent rather than intrinsically invalid.
- The alias rule is incomplete even relative to its stated motivation: explicit-versus-implicit spelling differences such as `Alpha/` and `alpha/file` are accepted. This creates a material boundary that is acknowledged but not experimentally characterized.
- Unicode canonicalization is ad hoc and version-dependent. The sequence NFKC, casefold, and trimming is not justified against a documented matching standard, lacks post-fold normalization analysis, and is tested only by a small specification-authored oracle.
- Using Python `tarfile` for both writing and reading tests only same-implementation round trips and gives no assurance about parser differentials, malformed metadata, other tar dialects, or other archive formats.
- There is no property-based testing, bounded exhaustive testing, independent implementation, formal argument, or multi-entry permutation testing to support general order independence or correctness beyond the listed examples.
- No performance or resource-exhaustion evaluation is provided, and the implementation has no specified limits for entries, depth, component size, canonicalized bytes, Unicode expansion, or trie nodes.
- The report lacks substantive positioning against archive-security, Unicode-security, and path-validation literature. While avoiding invented citations is correct, absence of related-work analysis prevents evaluation of significance at a competitive venue.
- Several reported predicates are redundant in the implementation as described: rejecting every repeated complete canonical path already rejects directory/non-directory pairs at the same path. This further reduces the substantive distinction demonstrated by the type-conflict class.

## Required fixes
- Release a complete, immutable reproducibility artifact containing parser and validator source, all manifests, all oracle cases, deterministic archive-generation code or generated archives, raw per-run results, figure source, exact Python and Unicode database versions, dependency information, execution instructions, and cryptographic hashes.
- Add competitive baselines: at minimum, a sorted canonical-path prefix scan, an explicit-type-aware validator that does not reject raw aliases, and a canonical-merging policy. Also evaluate representative archive-library extraction filters or validators.
- Expand the corpus with generated and adversarial multi-entry cases, including overlapping conflicts, duplicate directories, explicit-versus-implicit aliases, aliases at multiple depths, hard links, symlink-target attacks, special member types, malformed PAX metadata, and carefully matched nonconflicting near misses.
- Use property-based or bounded exhaustive testing to check permutation invariance, equivalence between trie and sorted-prefix implementations where intended, rejection monotonicity, parser invariants, and preservation of valid controls. Publish seeds, generation bounds, and minimized counterexamples.
- Specify a precise extraction contract and either justify implicit raw-spelling rejection under that contract or compare it experimentally with canonical merging. Explicitly resolve how explicit directory spellings participate in alias detection.
- Run controlled extraction experiments with independently implemented archive readers and representative extractors/filesystems on Linux, macOS, and Windows. Report actual outcomes such as merge, split, overwrite, failure, replacement, and link traversal rather than relying only on hypothetical consequences.
- Define canonicalization by reference to a documented Unicode matching construction, record the Unicode version, test whether normalization is required after folding, and generate adversarial tests from Unicode normalization and case-fold data.
- Add at least one independent implementation or differential checker so that the parser, canonicalizer, and conflict predicates are not all validated solely against artifacts derived from the same specification and codebase.
- Measure time and memory under increasing entry counts, path depths, component lengths, total name bytes, and Unicode expansion. Specify enforceable resource limits and fail-closed behavior.
- Provide a substantive related-work section covering archive extraction safety, path sanitization, prefix-conflict detection, filesystem aliases, Unicode security, and existing library safeguards. Reframe the contribution relative to that literature.
- Avoid presenting the 192 order-specific streams as 192 independent samples. Report the 96 manifests as the primary experimental units and describe the reversed streams strictly as order checks.
- If the study remains limited to constructed conformance examples, reposition it as a reproducible specification-and-test artifact rather than a general archive-security result; otherwise, substantial external validation is needed for acceptance at a competitive research venue.

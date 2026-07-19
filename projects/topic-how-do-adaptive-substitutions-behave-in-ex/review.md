# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The central proposition is sound: a commitment over artifact records alone cannot authenticate omitted unit-to-artifact relationships, while a commitment over changed canonical relationship tuples will differ unless a hash collision occurs.
- The conclusions follow from the stated construction, and the report appropriately treats the 40 baselines and 80 mutations as deterministic implementation checks rather than independent statistical samples.
- The report is unusually candid about scope, lack of novelty, shared-baseline dependence, missing preregistration evidence, and the inappropriateness of significance tests.
- The mutation design cleanly isolates the distinction between executable validity and authentication of original assignment: swapping complete source-output pairs between units with the same operation preserves re-execution while changing assignment.
- The threat model, trusted computing base, root-authentication distinction, rollback assumptions, and dependence on stable unit and operation identities are clearly articulated.
- Canonicalization, domain separation, artifact identifiers, transformations, graph construction, mutation rules, and validation conditions are described in enough detail to permit an independent reimplementation.
- The unauthenticated-root condition correctly demonstrates that recomputing a digest is not authentication when the candidate controls both the committed data and the declared digest.
- The results are reported as exhaustive counts without unjustified population-level or real-world security claims.

## Weaknesses
- The executable implementation, generated objects, trusted roots, result CSV, figure, dependency lock file, and checksums are absent. Consequently, none of the implementation-level claims or reported counts can be audited, and an independent reimplementation would test the description rather than verify the reported execution.
- The substantive contribution is very limited for a competitive venue. The main result is nearly tautological from the commitment definitions, is explicitly described as standard and non-novel, and requires only one valid counterexample rather than 80 constructed mutations.
- The experimental corpus adds little evidence because every outcome was designed to be deterministic: the mutations preserve exactly the fields covered by one root and change exactly the fields covered by the other.
- Only two fixed unit pairs are tested per baseline. This does not meaningfully exercise combinatorial cases, boundary conditions, alternative identifiers, malformed inputs, duplicate references, canonicalization failures, or implementation branches.
- The implementation validation is effectively self-reported. Assertions such as exact artifact-dictionary equality, exactly four changed fields, and root inequality may have been checked by the same code that generated the candidates, so common-mode implementation errors are not excluded.
- The report does not provide concrete test vectors with canonical serialized bytes and expected digests. Such vectors would make the formal definitions and independent conformance testing substantially more verifiable.
- The use of one pseudorandom seed and 40 graphs is neither harmful nor evidentially important, but it creates unnecessary experimental framing around what is fundamentally a proof plus unit test.
- The relationship-root construction is shown only to distinguish this selected mutation. There is no comparative analysis demonstrating why this tuple design is preferable to simpler commitments that would also detect the tested swap.
- The schema and verifier behavior are described only at a high level. Details such as rejection of extra fields, duplicate unit IDs, duplicate JSON keys, unsupported operation names, malformed hexadecimal strings, and exact trusted-root selection are not specified.
- The paper is substantially longer than warranted by its result. Extensive caveats and follow-up questions are responsible, but they do not compensate for the lack of a broader technical contribution.

## Required fixes
- Provide a complete archival reproducibility package containing the exact executable source, dependency and interpreter versions, all baseline and candidate objects, trusted-root objects, result CSV, figure, execution instructions, and SHA-256 checksums.
- Include several normative test vectors showing the baseline and mutated unit records, exact canonical JSON bytes or escaped byte representations, inventory-root inputs and outputs, relationship-root inputs and outputs, and expected validator decisions.
- Separate candidate generation from validation, or add an independently implemented verifier and cross-check both implementations, to reduce the risk of generator-validator common-mode errors.
- Specify the complete schema and rejection semantics, including uniqueness requirements, handling of unknown or extra fields, duplicate identifiers and references, duplicate JSON keys, malformed encodings, unsupported operations, and trusted-root lookup.
- Reframe the submission explicitly as a short formal note, teaching artifact, or reproducible case study rather than an empirical security evaluation; alternatively, add a genuinely broader contribution appropriate for a competitive full-paper venue.
- If presented as broader research, evaluate additional nontrivial mutation classes and realistic graph structures, including source-only and output-only substitutions, multi-parent ordering and roles, operation parameters and versions, unit renaming, cross-stage substitutions, rollback, and parser or canonicalization disagreement.
- Compare the proposed tuple commitment with narrower and alternative commitments, identifying which fields are necessary and sufficient for each tested attack class rather than merely observing that the full tuple detects the chosen swap.
- Reduce claims that the repeated corpus 'validates' the implementation unless the implementation artifacts are supplied; without them, label the counts explicitly as unverified reported outcomes.

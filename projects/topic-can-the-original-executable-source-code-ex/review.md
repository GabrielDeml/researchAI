# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The claims are unusually well calibrated to the evidence: the report consistently describes the work as a restricted, single-implementation conformance experiment rather than general JSON-LD, RDF, RO-Crate, or semantic canonicalization.
- The distinction among raw archive identity, policy-defined canonical identity, JSON structural equivalence, RDF equivalence, and research-object identity is clear and technically important.
- The report honestly acknowledges that both headline outcomes were largely guaranteed by construction and does not attach statistical significance to the 50-pair sample or the obsolete 90% threshold.
- The method is described in substantial detail, including the seed, transformations, file contents, metadata rules, ZIP settings, hashing procedure, and many inherited or unspecified implementation behaviors.
- The conclusions follow from the described results: if the implementation and reported measurements are accurate, the experiment supports only consistency of that implementation on its generated corpus.
- The limitations section identifies the major threats to validity, including shared-code bias, lack of negative controls, path-normalization collisions, incomplete Unicode and numeric policies, ZIP underspecification, missing policy versioning, and absence of cross-implementation testing.
- The discussion correctly separates packaging determinism from execution reproducibility and avoids claiming that bundled source, environment declarations, and outputs prove successful reproduction.
- The follow-up questions form a strong roadmap toward a genuine conformance specification and interoperability evaluation.

## Weaknesses
- The central result is nearly tautological: variants are generated to differ in raw metadata bytes and are then processed by the same normalization and ZIP-writing implementation whose behavior is being tested. This establishes little beyond basic internal consistency.
- Generation, equivalence validation, and canonicalization share the same implementation and assumptions. Without an independent oracle, common-mode defects can produce perfect results.
- No systematic negative controls establish sensitivity to policy-significant changes. Consequently, the experiment tests invariance under selected transformations but does not adequately test whether distinct packages remain distinct.
- The complete artifact is absent: source code, exact invocation, runtime fingerprint, generated corpus, archives, result tables, aggregate data, figure source, and expected digests are unavailable. The numerical results therefore cannot be independently verified.
- The runtime and platform used for the reported execution were not recorded, despite the work depending on implementation-defined behavior of Python JSON and ZIP libraries.
- The purported policy is not sufficiently complete for interoperable byte-level canonicalization. Filename encoding, Unicode normalization, ZIP flags and headers, ZIP64, numeric representation, malformed-input handling, resource limits, and several file types remain unspecified.
- Only one implementation, language, ZIP library, runtime configuration, and synthetic corpus were tested. There is no evidence of cross-version, cross-platform, or cross-language interoperability.
- The corpus is too narrow to support conclusions about practical RO-Crate tooling. It excludes externally produced crates, non-ASCII paths, blank nodes, context variations, broader JSON number forms, adversarial archives, symlinks, large files, and other common or difficult cases.
- The identifier format lacks policy versioning and domain separation, making it unsuitable for stable interoperable use if normalization rules evolve.
- There are no implemented baselines or comparative experiments against canonical manifests, reproducible archive conventions, canonical JSON, RDF dataset canonicalization, or Merkle representations. Thus the design choice of hashing canonical ZIP bytes is not justified empirically.
- The contribution is technically modest and its novelty is unclear. Deterministic JSON serialization, reproducible ZIP construction, and content hashing are established techniques; the report does not demonstrate a substantially new algorithm, specification, or interoperability result.
- The missing bibliography prevents verification of prior-art and standards claims and makes novelty assessment incomplete.
- The report is substantially longer than warranted by the evidence and repeatedly restates the same caveats. This improves honesty but obscures the small positive result and weakens presentation efficiency.
- The embedded figure is not verifiable and adds little because it visualizes two deterministic 100% outcomes rather than uncertain or comparative measurements.

## Required fixes
- Release a complete, immutable artifact containing the exact source, invocation, runtime and platform fingerprint, dependency lock, generated corpus, raw and canonical archives, CSV and JSON results, figure-generation code, and a signed or otherwise integrity-protected manifest of expected digests.
- Separate corpus generation, equivalence checking, canonicalization, and output verification. Provide an independently written verifier that checks canonical entry names, metadata bytes, ZIP properties, archive bytes, and final identifiers without reusing the implementation under test.
- Add systematic one-factor negative controls for every distinction the policy intends to preserve, including file bytes, metadata scalar values, reference membership, ordered arrays, filenames, normalized paths, and any retained permission or file-type information. Confirm that each change alters the identifier.
- Add collision-oriented tests for every intentionally normalized or discarded distinction, especially backslash conversion, repeated separators, dot components, Unicode normalization forms, case differences, duplicate normalized names, filename encodings, permissions, ZIP flags, comments, extra fields, compression choices, timestamps, ZIP64, and malformed headers.
- Produce a complete normative, versioned canonicalization specification independent of Python behavior. It must define text and filename encoding, Unicode handling, string ordering, JSON number and escaping rules, duplicate-key behavior, archive header fields, ZIP64 behavior, supported file types, malformed-input handling, resource limits, and deterministic error behavior.
- Include the policy identifier and cryptographic domain separation in the identifier construction, with explicit test vectors for the resulting format. Explain migration and compatibility rules across future policy versions.
- Implement at least one second canonicalizer in a different language using a different JSON parser and ZIP library, and demonstrate byte-identical outputs on a shared conformance suite across multiple operating systems and runtime versions.
- Expand the corpus to include externally generated RO-Crates from multiple authoring tools and serializers, Unicode filenames, nested paths, binary and large files, realistic metadata, blank nodes or an explicit prohibition on them, context variations, order-sensitive arrays, and adversarial archive structures.
- Clarify the intended identity relation and threat model. For every discarded distinction, justify why conflation is safe for the target use case; otherwise revise the policy to preserve that distinction.
- Add experimental baselines comparing canonical ZIP hashing with at least a canonical manifest approach and, where relevant, canonical JSON and RDF dataset canonicalization. Evaluate interoperability, implementation complexity, identifier stability, and sensitivity to package-significant changes.
- Supply a complete and traceable bibliography covering RO-Crate, JSON canonicalization, JSON-LD and RDF dataset canonicalization, reproducible archives, preservation manifests, content-addressed systems, and relevant archival identifiers, then revise the novelty discussion against that prior art.
- Shorten and restructure the paper so that the limited contribution, exact tested proposition, evidence, and acceptance criteria are prominent, while consolidating repeated limitations into a more concise threat-to-validity section.

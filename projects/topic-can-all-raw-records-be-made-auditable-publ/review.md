# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The central conclusion is appropriately narrow: unchanged donor references with stale contextual metadata must fail when the target unit identifier is included in the recomputed digest, absent a hash collision or implementation defect.
- The report clearly distinguishes contextual consistency from authentication and explicitly acknowledges that an attacker can rewrite metadata and recompute an unkeyed context digest unless an external authenticated commitment is available.
- The threat model is unusually explicit about attacker capabilities, trust-anchor assumptions, and the difference between authenticated and unauthenticated publication roots.
- The deterministic nature of the result is represented honestly. The report correctly avoids treating 128 swaps as independent statistical security trials or as an estimated general detection rate.
- The experimental construction is described in substantial detail, including seeds, generation rules, canonical serialization, semantic evaluation, bit packing, archive construction, swap selection, and verification behavior.
- The report identifies important methodological limitations: shared implementation logic, lack of malformed-input tests, lack of cross-language verification, limited corpus scope, potentially trivial archive uniqueness, and absence of scalability measurements.
- Arithmetic and corpus accounting are mostly transparent, including the derivation of 7,808 parser checks and 11,904 primary artifacts.
- The negative security result is stated plainly: contextual hashing alone does not resist adaptive provenance rewriting and is not presented as a substitute for signatures, attestations, or authenticated manifests.

## Weaknesses
- The empirical results are not independently assessable because the executable source, raw records, artifacts, environment specification, inventory, figure data, and literal inventory root are absent. Exact counts, hashes, uniqueness values, and behavioral statistics are therefore unsupported assertions in the submitted material.
- The only experimentally tested attack is almost tautological under the stated digest equation: every swapped reference has a different target unit identifier, so rejection is predetermined. This provides a basic implementation branch test but little scientific evidence beyond inspection of the specification.
- The report frames the work as validation of a particular verifier implementation, yet the implementation itself is unavailable. Without source or executable artifacts, even that limited implementation-conformance contribution cannot be reviewed.
- The intended authenticated root is central to the security interpretation but was neither supplied nor operationally authenticated. Consequently, the experiment does not validate the end-to-end trust model highlighted in the hypothesis and conclusion.
- Workers, controller, indexer, and apparent verification logic share one Python codebase or at least common assumptions. Fresh processes do not provide implementation independence, so systematic serialization, archive, indexing, or verifier errors could survive all reported checks.
- There is no negative-control suite demonstrating that the context-sensitive verifier rejects individually corrupted unit identifiers, stages, schemas, parent lists, parent orderings, payload digests, or context digests for the intended reason. The tested swaps conflate at least unit-identifier and parent-context mismatches.
- Payload-only acceptance is guaranteed by transporting the donor path and matching donor payload digest together. This is a valid counterexample to payload-only association checking, but it is a deliberately weak verifier baseline rather than a competitive provenance mechanism.
- No empirical comparison is made against signed manifests, authenticated Merkle structures, in-toto, SLSA, DSSE, or even a simple signed record. Thus the work does not establish practical advantage over established approaches.
- Novelty is very limited. Hashing canonicalized identifiers, stages, payload digests, and ordered dependency digests is standard domain-separated contextual hashing, and the report itself concedes this.
- The large generated Boolean-expression corpus is mostly irrelevant to the provenance claim. Behavioral distances, parser fixed points, and semantic diversity do not materially test the stale-reference property, which follows from differing identifiers alone.
- All parser inputs are valid and normalized by construction, making the reported parser and fixed-point success rates weak evidence. They do not test rejection, ambiguity, canonicalization disagreement, or adversarial archive handling.
- Output-archive uniqueness may be caused by embedded unit-specific metadata. Without the complete outcome schema, the reported uniqueness number has little interpretive value.
- The abstract's statement that the study used 3,968 fresh Python processes appears inconsistent or at least ambiguous with the later description of an additional fresh indexing process and controller activity. Process counts and roles should be stated precisely.
- References are cited numerically as [1] through [10], but no bibliography is included in the submitted report, preventing assessment of related-work accuracy and positioning.
- The report is substantially longer than warranted by the contribution. Repetition of the same caveats across the abstract, hypothesis, method, results, and limitations reduces clarity and obscures the very small empirical core.

## Required fixes
- Provide a complete, immutable artifact package containing all controller, worker, parser, serializer, archive-builder, indexer, verifier, and figure-generation source; exact commands; raw records; attack results; metrics; counterexamples; archives; captured process outputs; inventory; and figure source data.
- Publish the literal SHA-256 digest of the final inventory bytes through a specified authenticated channel, and document a verification procedure that starts from that externally obtained root rather than from files inside the artifact package.
- Supply an exact reproducible environment, including Python patch version, dependency lockfile, matplotlib version, operating system, architecture, locale, filesystem assumptions, and ZIP implementation details.
- Add a separately implemented verifier, preferably in another language and without shared helper code, and report byte-for-byte agreement on canonical JSON, context preimages, ZIP metadata, semantic bit packing, artifact hashes, record hashes, and the final inventory root.
- Expand the executable attack matrix to include adaptive context recomputation, source-only swaps, paired source-and-output swaps, cross-stage swaps, parent changes and reorderings, schema substitutions and downgrades, path aliases, manifest replacement, and authenticated-root versus unauthenticated-root conditions.
- Add isolated negative controls that mutate one field at a time so that rejection can be attributed separately to unit identifier, stage, schema, parent list, payload digest, and stored context digest validation.
- Include a realistic authenticated baseline, such as a signed manifest or authenticated Merkle root, and clearly separate results for payload integrity, contextual consistency, statement authentication, authorization, and publication-root verification.
- Either remove the largely irrelevant mutation-testing and semantic-diversity measurements or justify how they expose verifier defects that simpler test vectors would not. Do not present corpus size as strengthening the algebraically predetermined security result.
- Publish the complete outcome-record schema and recompute archive-diversity statistics after excluding unit-specific identifiers, paths, and other metadata. Label byte-level, syntactic, and semantic diversity separately.
- Resolve the fresh-process accounting by enumerating controller, worker, indexer, verifier, and figure-generation process counts and clarifying which count the abstract reports.
- Provide the missing bibliography and ensure that claims about provenance standards and prior work are accurately supported.
- Condense the manuscript, remove repeated caveats, and recast the contribution explicitly as a verifier conformance test or artifact-validation note rather than broader empirical evidence for provenance security.

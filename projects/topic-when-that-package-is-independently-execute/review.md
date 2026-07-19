# Peer review

**Score:** 4/10  _(after one revision pass)_

## Strengths
- The central conclusion is appropriately conservative: absent specifications, traces, metadata, and result artifacts, the stated hypothesis is inconclusive rather than supported or refuted.
- The report carefully distinguishes failure of the evidence package or execution pipeline from falsification of the scientific hypothesis.
- It avoids fabricating missing target names, digests, run outcomes, or execution counts, and explicitly warns that zero supplied artifacts does not mean zero generated artifacts.
- The proposed acceptance rule is stringent and largely coherent: support requires all controls and all 12 observations to be usable and passing, while unusable or incomplete evidence yields an inconclusive result.
- The discussion identifies important provenance confounds, including preexisting files, aliases, renames, descriptor inheritance, namespaces, concurrency, incomplete traces, and file-backed mmap.
- The limitations and novelty statements are unusually candid, correctly acknowledging that four runs provide only limited evidence and that the protocol mostly combines established techniques.
- The report is generally clear about which statements describe observed evidence-package contents and which describe requirements for a future rerun.

## Weaknesses
- There is no completed experiment, implementation, trace, specification, source code, test output, or empirical evaluation. Consequently, the submission establishes only that the reviewed package is incomplete, not that the proposed protocol is correct, practical, or useful.
- The contribution is not sufficiently novel for a competitive research venue. The report itself concedes that it combines established container pinning, syscall tracing, hashing, provenance, and atomic persistence techniques without demonstrating a new mechanism or capability.
- The methodology section presents an extensive event model as if it were a validated protocol, but no tracer is identified and no evidence shows that the required information is observable or reconstructible in the intended environment.
- Several requirements may be infeasible or highly platform-specific, including reliable process-generation identity, mount and root context, complete descriptor transfer tracking, underlying file-object identity, global ordering across processes, and alias tracking through namespaces. Their implementability and assumptions are not analyzed.
- The report does not define the threat model. It is unclear whether the protocol addresses accidental cache reuse, buggy software, adversarial package behavior, malicious containers, tracer evasion, host compromise, hash substitution, or only ordinary reproducibility failures.
- The proposed decision rule classifies every usable mismatch as refutation of a compound hypothesis. This is logically defensible for that exact hypothesis, but it conflates digest nondeterminism with provenance, path-safety, and ordering failures unless failure categories are separately analyzed.
- No rationale is provided for choosing four runs, the five-minute timeout, the 600 MiB limit, the 27-minute total limit, or the specific parser controls. The report acknowledges the absence of a power argument but does not replace it with a principled reliability or coverage analysis.
- The three positive controls are insufficient to validate the much broader parser semantics later required. A small set of examples cannot establish correctness for concurrency, namespace changes, aliasing, descriptor passing, mmap, interrupted syscalls, or trace loss.
- There are no negative controls demonstrating that the system detects digest mismatch, read-before-write, preexisting-object rename, symlink escape, hard-link reuse, truncated tracing, or deliberately omitted process descendants.
- The proposed preservation of the initial startup record, every replacement, and the final results file is underspecified. Atomic replacement of one pathname does not preserve prior versions without a separate append-only log, versioned files, or external storage.
- The report does not establish that a startup record can be durably created before all relevant failure points. Failures before workspace creation, filesystem availability, or driver launch necessarily remain outside that mechanism.
- Path containment and absence of symlink components are not fully specified under races. A post-run path check can be vulnerable to time-of-check/time-of-use changes and may not characterize the path used during execution.
- Digest verification after execution does not by itself bind the hashed bytes to the file object represented by earlier trace events. The design needs an explicit race-free snapshot or identity-binding procedure.
- Network-disabled containers and fresh writable layers do not alone guarantee a locked environment; host-mounted files, clocks, randomness, CPU behavior, kernel version, locale, environment variables, and runtime configuration remain potential confounds.
- The references are cited only as placeholders [1]-[6]; no bibliography is supplied, making the related-work claims unverifiable.
- The 12-row table repeats the same absence statement and adds little information. It risks giving the appearance of observation-level reporting despite containing no observations.
- The required PNG matrix is operationally arbitrary and scientifically irrelevant. Treating its generation failure as sufficient to make an otherwise complete experiment inconclusive is unnecessarily strict unless figure production is explicitly part of the tested pipeline.
- The report is substantially overlong and repetitive for the narrow factual result that no reviewable artifacts were supplied.

## Required fixes
- Supply the immutable experiment specification, pinned image digest, exact command vector, target paths and expected digests, software versions, source code, dependencies, and complete invocation details.
- Implement the protocol and provide a completed evaluation with four fresh runs, all 12 target observations, raw or independently auditable trace evidence, integrity hashes, run metadata, and a final machine-readable results file.
- Define a precise threat model and state which guarantees are sought against accidental errors versus adversarial behavior.
- Identify the concrete tracing technology and platform, then map every required event-model field to an actual observable. Downgrade or remove guarantees that the tracer cannot provide.
- Provide a formal or executable specification for event ordering, path resolution, descriptor inheritance and transfer, namespace handling, aliases, renames, mmap, trace truncation, and lineage identity.
- Add comprehensive automated positive and negative tests, including deliberate digest mismatch, preexisting-output reuse, read-before-write, rename of preexisting content, hard links, symlink escape, directory-fd operations, descriptor duplication and inheritance, process descendants, concurrency, namespace changes, mmap, dropped events, malformed traces, tracer termination, and target mutation during hashing.
- Demonstrate race-free binding between traced file objects and the bytes subsequently hashed, for example through stable object identity checks and a controlled snapshot or open-descriptor hashing procedure.
- Specify all environmental controls beyond the container image, including host mounts, kernel and runtime, locale, timezone, clocks, randomness, CPU architecture, environment variables, user identity, resource limits, and writable storage.
- Justify the number of repetitions and resource thresholds. If behavior can be stochastic or timing-sensitive, use additional runs, controlled seeds where applicable, and deliberate environmental variation.
- Separate failure categories in the results so digest mismatch, provenance failure, path-safety failure, parser uncertainty, and infrastructure failure remain distinguishable even if the overall compound hypothesis is refuted or inconclusive.
- Implement and test an append-only or versioned state-transition mechanism if prior results states must be retained; atomic replacement alone is not sufficient.
- Clarify which failures are scientifically decisive and remove the requirement that a missing secondary PNG invalidate otherwise complete machine-readable evidence.
- Provide a substantive comparison with existing reproducible-build, provenance, workflow, and syscall-tracing systems, including baselines or ablations showing what the integrated protocol detects that simpler alternatives do not.
- Include complete bibliographic references and ensure every related-work and technical claim is supported.
- Condense repetitive missing-data sections and replace the empty 12-row table with a concise missing-artifact inventory until actual observation-level data exist.

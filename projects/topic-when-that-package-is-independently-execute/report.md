# Incident Report: Missing Evidence Prevents Verification of the Three CSV Digests

## Abstract

The proposed experiment asked whether independently executing a pinned package in four fresh, network-disabled environments would regenerate three CSV files with their stated SHA-256 digests while creating and writing each file before reading it. The protocol called for syscall tracing, parser controls, path-safety checks, streaming hashing, and 12 target observations across four executions.

This submission is an **incident and protocol report, not a completed experimental result**. The supplied record contains neither the immutable specification nor the implementation, execution evidence, failure record, final `results.json`, trace artifact, per-run metadata, or `trace_digest_matrix.png`. These artifacts may never have been created, may have been written elsewhere, or may have been lost after creation; their absence from the supplied record does not distinguish among those possibilities. No rerun can be independently reconstructed from the supplied material because the exact command vector, target paths, expected digests, pinned image digest, and software versions are unavailable.

At the hypothesis level, the decision is **inconclusive**: the hypothesis is neither supported nor refuted. Separately, the execution pipeline or preserved evidence package is classified as **broken**, meaning that it failed to supply the artifacts needed to apply the protocol’s decision rule. “Broken” is not a scientific-hypothesis verdict.

## Background

Reproducibility depends not only on preserving scientific software and data, but also on precisely specifying the execution environment and retaining sufficient provenance to verify that a result was regenerated rather than reused. Prior work has discussed reproducible computational environments in high-performance computing [1], integrity guarantees from reproducible builds [2], publication and management of scientific software and data [3], and the role of explicit scientific workflows [4]. Broader reviews of scientific software engineering likewise emphasize disciplined development and validation practices [5].

For this question, matching a SHA-256 digest would establish byte-for-byte equality between an observed CSV and its assigned reference artifact, subject to the usual interpretation of the hash function [6]. Digest equality alone would not demonstrate that the package created the file during the measured execution. Creation, write-before-read ordering, path safety, and source lineage would require independently auditable event-level provenance.

The proposed contribution is an integrated acceptance protocol that combines a pinned execution environment, initial-path-absence checks, syscall-derived file provenance, exact digest comparison, repeated clean executions, and an explicit supported/refuted/inconclusive rule. Those components overlap substantially with established reproducible-build, container-provenance, workflow, and syscall-tracing practices. The supplied citations and record do not establish that any individual mechanism is novel, and no implementation-level comparison with existing tools was preserved. Accordingly, no claim of a new tracing algorithm or implemented provenance system is justified. At most, the report specifies a proposed combination of established checks for this particular three-target verification task; whether that combination is useful or correctly implemented remains untested in the supplied evidence.

## Hypothesis

The hypothesis was:

> Across four executions in fresh locked environments with the output directory initially absent, syscall tracing will show that each of the three target CSV paths is created after execution begins, is written before any read of that path, and produces its assigned stated SHA-256 digest in every run.

This was worth testing because a package may appear reproducible while reading preexisting outputs, copying cached artifacts, or producing nondeterministic files. Requiring initial absence, post-launch creation, write-before-read ordering, path safety, and exact digest agreement would provide stronger evidence of independent regeneration than digest comparison alone.

Four runs were specified as a limited repeated-regeneration check, producing 12 planned target observations. Four executions cannot establish general determinism or reproducibility beyond the tested image, command, targets, environment controls, and those four executions. The supplied record contains no rationale based on power, failure probability, or variability. If the package is stochastic, timing-sensitive, dependent on concurrency, or sensitive to uncontrolled host or runtime state, additional replication and deliberate environmental variation would be required before making broader claims.

The protocol’s hypothesis-level decisions are:

- **Supported** only when every required control, run, and target observation is usable and all 12 targets pass.
- **Refuted** only when every required control, run, and target observation is usable and at least one target fails.
- **Inconclusive** when setup, controls, tracing, execution, resource handling, hashing, cleanup, artifact preservation, or observation completeness prevents application of the first two rules.

The separate label **broken** applies only to the execution pipeline or evidence package. It denotes that required records are missing, invalid, or insufficiently preserved; it does not replace the hypothesis-level decision.

## Method

The protocol required an immutable `experiment_spec.json` identifying a locally available OCI image pinned as `repo@sha256`, an argument-vector command containing an `{output_dir}` token, an absolute output directory, and exactly three safe relative target paths with 64-character lowercase expected SHA-256 values. It required rejection of invalid or duplicate target paths, unpinned images, and commands lacking the substitution token. The specification digest, pinned image digest, exact command vector, target paths, expected digests, runtime version, tracing version, operating-system details, driver version, and parser version were all necessary reproduction metadata.

None of those concrete values or version records is present in the supplied material. The actual driver and parser source code are also absent. Therefore, this report can describe the required protocol but cannot establish that the driver, parser, controls, or failure handlers were implemented or executed.

The startup protocol required atomically precreating `results.json` before substantive setup. The initial record was to contain flat scalar fields identifying an incomplete experiment, an inconclusive decision, a nonempty startup or incomplete-experiment error, 12 expected observations, no yet-completed observations, and the expected figure name `trace_digest_matrix.png`. Subsequent changes were to use write-to-temporary-file, flush and durability operations as appropriate, followed by atomic replacement. Signal handlers and top-level exception handling were intended to preserve a failure reason. A valid rerun must retain the initial startup record, every subsequent replacement or an auditable state-transition log, and the final `results.json`.

Before measured execution, the parser was required to pass three controls:

1. Create an absent file, write `b'abc'`, close it, and read it.
2. Read and then overwrite a preexisting file.
3. Write `b'abc'` to a temporary file, rename it atomically to the target, and then read the target.

The controls were intended to distinguish initial absence from preexistence, identify write-before-read ordering, follow rename lineage, and verify the known SHA-256 value `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`.

A sufficient implementation test suite would also need adversarial tests for relative paths, changing working directories, `dirfd`-relative operations, descriptor duplication, descriptor inheritance, hard links, symlinks, bind mounts and mount namespaces, ordinary renames, rename exchanges, concurrent processes, file-backed `mmap`, partial or truncated traces, tracer failure, and process termination. No source code, fixtures, automated test output, or test coverage for either the three controls or these adversarial cases is present in the supplied record.

For a valid rerun, the trace event model must be defined as follows:

- A trace event is a parsed successful or failed syscall completion associated with a run, process and thread identity, process-generation identity, per-thread sequence, trace sequence, monotonic timestamp if available, syscall name, arguments, return value, current working directory, root and mount namespace, relevant descriptor state, and resolved target or lineage identity.
- Per-thread order is the observed syscall-completion order. Cross-thread and cross-process order may be asserted only where the tracer provides an unambiguous serialized order or timestamps establish it. Events with indistinguishable ordering must remain unordered. A write-before-read claim is valid only when no target-relevant read can precede the first qualifying write under the retained ordering information; ambiguous ordering makes that determination inconclusive.
- Only successful operations count as creation, reads, writes, links, renames, or descriptor changes. Positive-byte reads and writes must record their byte counts. Failed operations remain in the trace for audit but do not establish access.
- Relative paths must be resolved using the process’s path state at the event, including its root, current working directory, `dirfd`, `chdir` or `fchdir` history, and namespace and mount context. Lexical normalization alone is insufficient where symlinks or mounts affect resolution.
- Descriptor state must follow successful `open`-family calls, `close`, `dup`, `dup2`, `dup3`, relevant `fcntl` duplication, inheritance through process creation, and retention or closure across execution according to close-on-exec state. Any untracked descriptor transfer relevant to a target makes lineage incomplete.
- Alias tracking must distinguish paths from underlying file objects. Hard links, symlinks, link operations, rename operations, rename exchanges, temporary-file replacement, and object identity changes must update path-to-object and source-lineage relations. Bind mounts and mount namespaces must be represented rather than collapsed solely by textual path.
- Target creation is the first successful post-launch namespace operation that changes the initially absent target path into an existing entry. Creation of a path by linking or renaming a preexisting object must preserve that preexisting lineage and must not be misclassified as newly generated content.
- Reads and writes through any known alias or duplicated or inherited descriptor must be attributed to the same underlying object. Concurrent operations must retain process identity and available ordering rather than being reduced prematurely to one path-level timestamp.
- A successful readable file-backed `mmap` establishes that the process obtained a mapping from which reads were possible, but syscall tracing alone generally cannot prove which pages were actually read. A mapping created before the first qualifying write therefore prevents a definitive write-before-read claim unless page-access evidence is collected by another validated mechanism.
- A successful writable file-backed `mmap` establishes potential write access but does not, by itself, prove that any page was dirtied. `msync`, unmapping, or process termination also does not independently prove which bytes were modified. A write attributable only to a writable mapping cannot count as a confirmed write without validated page-dirty or equivalent evidence. Unflushed or ambiguously flushed mappings at termination make the relevant observation inconclusive.
- A trace is malformed or incomplete if target-relevant records cannot be parsed; syscall entry and completion records cannot be paired; events are truncated; the tracer reports dropped records or exits unexpectedly; target-relevant paths, descriptors, namespaces, aliases, or process ancestry cannot be resolved; a traced process is missing required termination information; or interruption prevents determining whether later target-relevant events occurred. Such a trace cannot support or refute the hypothesis.

The original design proposed streaming traces without retaining the raw trace. That is insufficient when parser correctness is central to the claim. A valid rerun must preserve either the complete trace or a privacy-preserving target-relevant subset containing enough event-level fields to independently verify every creation, read, write, descriptor transition, alias, rename, link, and lineage decision. Each retained trace artifact and derived observation file must have an integrity hash recorded in `results.json`. Redaction rules, if used, must be deterministic and documented, and they must not remove context required for target-path resolution or event ordering.

The measured phase specified exactly four sequential executions. Each execution was to use a new container from the same pinned image, disabled networking, a fresh writable run directory under `/tmp`, an initially absent output directory, and no reused writable layer. Each run had a five-minute timeout and a 600 MiB run-directory limit, within a 27-minute whole-experiment limit. Disk-space thresholds were to be checked before setup and around each run.

For every run, the preserved metadata must include at least the run identifier, exact container and tracer invocation vectors, image digest, start and end times or monotonic durations, package exit status, tracer exit status, termination signal if any, timeout status, run-directory size, applicable disk-space measurements, cleanup status, trace integrity hash, and explicit run-level failure reason. The supplied record contains none of this per-run metadata.

After each usable execution, each target was to be checked for existence, regular-file status, absence of symlink path components, and containment beneath the output directory. Its SHA-256 digest was to be computed by streaming 1 MiB blocks. Each observation required the target path, expected and actual digest, file size, initial-absence result, creation evidence, first qualifying write and read ordering, path-safety outcome, lineage summary, run status, pass status, and explicit failure reason.

The decision rule was:

- **Supported** only if all parser controls passed, all four runs completed, all 12 target observations were available, and all 12 targets passed.
- **Refuted** if all controls, runs, traces, and observations were usable but at least one target failed.
- **Inconclusive** if setup, controls, tracing, resource limits, cleanup, hashing, artifact creation, or observation completeness failed.

The protocol also required a deterministic 800 × 600 PNG matrix at `trace_digest_matrix.png` summarizing the 4 × 3 observations. This PNG is a secondary visualization, not the scientifically decisive artifact. Its absence indicates pipeline or evidence-package incompleteness, but the machine-readable observations and auditable trace evidence are more important.

Failure resilience was promised but not demonstrated. A valid implementation must use automated forced-failure tests at, at minimum, the following stages:

1. Immediately after startup-record creation.
2. During each parser-control stage.
3. During container or traced package execution.
4. During target hashing.
5. During creation of `trace_digest_matrix.png`.
6. During final temporary-result writing.
7. Immediately before and during final atomic replacement of `results.json`.

Each injection test must verify that the last durable `results.json` remains parseable, reports `decision='inconclusive'`, identifies the interrupted stage with a nonempty error, and does not overstate the number of completed controls, runs, or observations. No such failure-injection results were supplied.

## Results

No rerun evidence was supplied, and the original execution cannot be reconstructed from the available material. The following counts describe the **contents of the supplied evidence package**, not measured package behavior:

- Supplied `experiment_spec.json` files: **0**
- Supplied startup or intermediate failure records: **0**
- Supplied final `results.json` files: **0**
- Supplied auditable trace artifacts or trace subsets: **0**
- Supplied figures: **0**
- Supplied target-observation records: **0 of 12 required records**

These zeros must not be interpreted as executions producing zero outputs, zero trace events, or zero successful observations. They mean only that no such records were available for review.

All 12 required observations are reported individually below. Because the target paths and expected digests are absent, generic target positions are used solely to enumerate the protocol-required records; they do not substitute for the missing target identities.

| Run | Target | Target path | Expected digest | Actual digest | File size | Creation evidence | First-write / first-read ordering | Path safety | Run status | Observation result and explicit reason |
|---:|---:|---|---|---|---|---|---|---|---|---|
| 1 | 1 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 1 | 2 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 1 | 3 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 2 | 1 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 2 | 2 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 2 | 3 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 3 | 1 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 3 | 2 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 3 | 3 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 4 | 1 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 4 | 2 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |
| 4 | 3 | Not supplied | Not supplied | Not supplied | Not supplied | Not supplied | Unknown | Unknown | Unknown | Unavailable: specification, trace, run metadata, and result record were not supplied or did not survive. |

No actual SHA-256 values, expected target-specific SHA-256 values, file sizes, creation events, first-write events, first-read events, path-safety determinations, package exit codes, tracer exit codes, trace counts, software versions, or resource measurements can be extracted from the supplied record. The number of executions that started or completed is unknown.

The required `trace_digest_matrix.png` was not supplied or did not survive. The record does not establish that it was never produced. Its absence is evidence of an incomplete evidence package, but it does not by itself determine whether any target passed or failed.

Consequently, `completed_observations`, `digest_pass_count`, `joint_pass_count`, and `joint_pass_rate` are unavailable. There is no reviewable evidence that any CSV matched or differed from its expected digest, that any target was created after launch, or that any target was written before being read.

The scientific-hypothesis decision is therefore **inconclusive**. Separately, the execution pipeline or preserved evidence package is **broken** because it lacks the minimum artifacts needed to evaluate the experiment.

## Limitations

The central limitation is that this is an incident and protocol report rather than a completed experiment. The supplied record does not contain enough information to rerun the package, verify that the proposed experiment was executable, determine whether the driver and parser were implemented, or identify the stage at which evidence was lost.

The actual immutable `experiment_spec.json`, its SHA-256 digest, the pinned OCI image digest, exact argument-vector command, three target paths, three expected digests, runtime version, tracer version, operating-system details, driver version, parser version, dependency state, and exact container and tracer invocations were not supplied. Fabricating replacements would make the experiment non-reproducible, so no rerun is reported here.

The actual driver and parser implementation and their automated tests were not supplied. There is consequently no evidence that the three stated controls passed or that relative paths, `dirfd` operations, descriptor duplication and inheritance, hard links, symlinks, rename exchanges, concurrent processes, namespace or mount behavior, `mmap`, partial traces, and process termination were handled correctly.

No complete trace or target-relevant trace subset survived in the supplied record. Independent reviewers therefore cannot audit any derived creation, read, write, ordering, alias, or lineage determination. Parser correctness cannot be evaluated from derived summaries alone.

The original method did not define all event and filesystem semantics needed for a strong provenance claim. This revision states the requirements for a valid rerun, but there is no evidence that the absent implementation used those definitions. In particular, syscall tracing without page-access instrumentation cannot generally distinguish a merely readable mapping from pages actually read, or a writable mapping from pages actually dirtied. Observations dependent on those distinctions would have to remain inconclusive unless additional validated evidence were collected.

The record contains no forced-failure results. The absence of a startup failure record is inconsistent with the intended failure-resilience property, but it does not reveal whether the driver never started, failed before durable precreation, wrote outside the preserved workspace, encountered a replacement or filesystem failure, or produced records that were later lost. The same uncertainty applies to the final `results.json` and `trace_digest_matrix.png`.

The 12 table rows above are required record positions, not measured observations. Their unavailable fields cannot be converted into target failures, digest mismatches, or evidence that executions produced no output. Similarly, the absence of `trace_digest_matrix.png` is not a scientific finding about the CSVs.

Four runs would provide only a limited check of repeated regeneration under the specific tested conditions. Because no run records survived, even that limited assessment is unavailable. If future inspection shows stochastic, concurrency-dependent, timing-sensitive, or host-sensitive behavior, replication must be increased and the relevant environmental variation explicitly controlled or sampled.

Finally, novelty remains unestablished. The protocol combines existing ideas from pinned containers, reproducible builds, provenance capture, syscall tracing, path-safety validation, digest verification, and atomic result persistence. Without an implementation, evaluation, or detailed comparison against existing systems, the report cannot claim more than a proposed task-specific integration of those checks.

## Follow-up questions

- Can the experiment be rerun only after preserving the immutable `experiment_spec.json`, its SHA-256, the pinned OCI image digest, exact command vector, target paths, expected digests, software versions, and exact container and tracer invocation vectors?
- Can the actual driver and parser source, automated tests, fixtures, and test logs be supplied for the three controls and for relative paths, `dirfd` operations, descriptor duplication and inheritance, hard links, symlinks, rename exchanges, concurrent processes, namespaces and mounts, `mmap`, partial traces, tracer failure, and process termination?
- Can the rerun retain a complete trace or privacy-preserving target-relevant trace subset, together with integrity hashes and enough event-level context to verify every creation, read, write, alias, ordering, and lineage determination?
- Do forced failures immediately after startup, during controls, during execution, during hashing, during creation of `trace_digest_matrix.png`, and during final result replacement each leave a durable, parseable `results.json` with `decision='inconclusive'` and a nonempty stage-specific error?
- For each of the 12 observations, what are the exact target path, expected digest, actual digest, file size, creation evidence, first-write and first-read ordering, path-safety result, lineage result, run status, and explicit failure reason?
- What are the package, tracer, and container exit statuses, termination signals, timeouts, durations, disk measurements, run-directory sizes, and trace integrity hashes for each run?
- After all controls pass, do four fresh locked executions yield 12 usable observations, and what are the resulting `digest_pass_count` and `joint_pass_count`?
- Is package behavior stochastic, timing-sensitive, concurrency-dependent, or sensitive to host and runtime variation, and, if so, what replication level and environmental sampling are needed beyond the original four runs?
- Compared with existing reproducible-build, container-provenance, workflow, and syscall-tracing systems, which part of the implemented protocol—if any—provides a demonstrated capability beyond combining established checks?

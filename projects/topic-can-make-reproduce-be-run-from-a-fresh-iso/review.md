# Peer review

**Score:** 4/10  _(after one revision pass)_

## Strengths
- The report is unusually explicit that no artifact-level experiment was executed and that the hypothesis remains untested.
- It correctly distinguishes an infrastructure-level BROKEN session from a refuted artifact hypothesis.
- It avoids converting unattempted checks into zero-valued failure rates and appropriately reports execution-dependent measures as not applicable.
- The claims in the Results and Abstract are generally supported by the limited evidence described; there is little substantive overclaiming.
- The limitations section identifies major threats, including missing raw diagnostics, a single runner, uninspected materials, shared-logic risk, absent reference provenance, and lack of a statistical rationale for six repetitions.
- The proposed evidence model is clearer than a vague success criterion: it separates primary-to-replay agreement, primary-to-reference agreement, provenance checks, stdout, stderr, inventories, and hashes.
- Removing the PNG from the scientific acceptance criterion is methodologically correct.
- The report honestly acknowledges that the reconstructed JSON is not raw evidence and does not present it as an observed transcript.
- The writing is organized, readable, and internally consistent about the central conclusion that the study produced no artifact-level result.

## Weaknesses
- There is essentially no empirical contribution beyond an unsupported summary that docker info remained unsuccessful. Without timestamps, command outputs, exit codes, runner metadata, or recovery logs, even the infrastructure incident cannot be independently evaluated.
- The work is not a completed reproducibility study and has insufficient evidence for acceptance as an empirical paper at a competitive venue.
- The protocol is called registered, but no registration location, timestamp, immutable identifier, archived protocol, or evidence that registration preceded the attempt is provided.
- The complete protocol, source, image archive, lock file, repository revision, references, and verifier are unavailable. Consequently, the methodological discussion cannot be audited and may describe an aspirational rather than executable design.
- Novelty is limited. Most of the contribution consists of standard reproducibility controls and a detailed statement that Docker preflight failed.
- The six-pair design is arbitrary and cannot support reliability claims. The report recognizes this but does not replace it with a justified design.
- The proposed all-or-nothing acceptance rule provides coverage for one seed and one fixed workload but no estimate of nondeterminism frequency, platform robustness, or general reproducibility.
- The relationship between reference production and experimental execution is unclear. The Method says the downstream procedure would generate and commit a synthetic artifact and reference outputs, which risks creating references during the same workflow that is supposed to validate them and conflicts with references being precommitted at a registered revision.
- The independence requirements are underspecified. Saying that the verifier is independently implemented does not establish organizational independence, independent specifications, or protection against shared assumptions and common-mode errors.
- The 66-check arithmetic is administratively convenient but scientifically arbitrary because heterogeneous aggregate categories are counted equally, and several categories contain multiple assertions over three files.
- The protocol appears to use host-side orchestration and Docker-dependent recovery actions, but it does not specify how host Python, Docker CLI versions, contexts, platform-specific behavior, filesystem ownership, timestamps, locale, timezone, and container runtime differences are controlled.
- The intended byte-for-byte outputs may be deterministic only under unstated serialization constraints. The report does not specify CSV newline conventions, JSON canonicalization, binary format endianness, Python implementation/version pinning, locale, or ordering rules.
- Fresh clones alone do not guarantee independent executions if host caches, Docker layers, mounted state, shared temporary directories, or reused environment variables persist between runs.
- The phrase independent runners attempted: 1 is misleading because the report explicitly says no second independent runner was attempted; this should instead say total runners attempted: 1 and independent replication runners: 0.
- The report is substantially longer than the evidence warrants and repeats the same absence-of-evidence conclusion across multiple sections.

## Required fixes
- Publish an immutable, timestamped registration record showing the exact protocol and hypotheses as they existed before the failed attempt; otherwise remove or qualify the word registered.
- Provide the complete auditable protocol package: orchestration source, artifact repository and exact revision, OCI archive and metadata, image.lock.json, generator, Makefile, verifier, reference files, schemas, and cryptographic hashes.
- Rerun the preflight while preserving append-only raw evidence for every command, including timestamps, exact argv, relevant environment variables, Docker context and endpoint, exit codes, stdout, stderr, service status, socket diagnostics, recovery actions, runner OS, architecture, and Docker client/server versions.
- Attempt the protocol on at least one functioning host and one genuinely independent runner. Report the failed host separately rather than treating it as evidence about artifact reproducibility.
- Execute all planned primary and replay runs or explicitly publish the work only as a preregistered protocol and incident note, not as a reproducibility result.
- Clarify the chronology and immutability of artifact and reference creation. References must be produced and committed before test execution, with documented provenance; they must not be generated or updated by the validation run.
- Specify a genuinely independent reference oracle or explain the limits of self-consistency testing. Provide mutation tests showing that the verifier detects altered outputs, records, logs, inventories, commands, revisions, image identities, and hashes.
- Fully specify deterministic serialization and execution conditions, including exact interpreter implementation and version, dependency locks, locale, timezone, newline handling, JSON encoding and ordering, CSV dialect, binary format and endianness, filesystem ordering, and allowed metadata.
- Document isolation between runs, including volumes, mounts, temporary directories, caches, container names, user IDs, filesystem permissions, environment variables, and cleanup procedures.
- Either justify the number of repetitions using an explicit failure-probability model and target confidence bound or clearly retain it as a non-statistical smoke-test threshold and avoid reliability language.
- Replace the artificial 66-category headline with a machine-readable assertion schema and report both category-level and underlying assertion-level results without implying that each category has equal evidentiary weight.
- Correct runner-count terminology and remove repeated statements so that the final paper clearly separates observed incident evidence, preregistered design, and future-work requirements.

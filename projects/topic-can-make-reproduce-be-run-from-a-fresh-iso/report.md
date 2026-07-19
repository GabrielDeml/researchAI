# Runner-Specific Docker Preflight Failure: Incident Report and Unexecuted Reproducibility Protocol

## Abstract

This report documents a registered reproducibility protocol that was not executed because Docker preflight failed on one runner during one bounded recovery interval. The intended study would have tested `make reproduce` in six primary and six replay clean-container executions, with provenance verification and byte-level comparison of three output files. None of those executions, checks, or comparisons was attempted. The only observed result was the summarized failure state `BROKEN_DOCKER_DAEMON`, recorded after `docker info` reportedly remained unsuccessful through the prescribed recovery poll.

The available record does not include a raw preflight transcript, timestamps, runner operating system or architecture, Docker client and context details, `DOCKER_HOST`, command exit codes, stdout, stderr, socket or service diagnostics, or recovery-command outputs. No second independent runner was attempted. The protocol implementation, OCI archive, lock file, artifact source, committed references, verifier, and their cryptographic hashes were also not reached or independently inspected. Consequently, this is an infrastructure incident report and unexecuted protocol, not a completed reproducibility study. It provides no evidence for or against the artifact-level hypothesis.

## Background

The protocol was motivated by the distinction between distributing source code and demonstrating that an artifact can be executed from a clean checkout in a controlled environment. Its intended acceptance criteria covered the execution environment, command behavior, output bytes, and provenance records rather than source availability alone.

A container-based protocol still depends on host infrastructure. In this case, successful access to a Docker daemon was a prerequisite for inspecting or loading the intended image and for running the artifact. Failure at that prerequisite prevented any observation of the artifact itself.

The original report attached numerical citations `[1]` through `[6]` to general background claims but did not supply the corresponding bibliographic entries. The identities of those sources cannot be recovered from the available report without introducing new, unverified citations. This revision therefore does not retain unsupported numerical citations or make literature-dependent claims. The missing source metadata is recorded as a limitation rather than replaced with invented references.

The intended experiment targeted exact byte-level agreement, explicit environment and command provenance, separate capture of stdout and stderr, and recomputation of recorded evidence. These remain planned design requirements only. Because neither the implementation nor its supporting materials were inspected, this report does not establish that the proposed controls were implemented correctly or even that all described files existed in executable form.

## Hypothesis

The registered artifact-level hypothesis was:

> Across six independent clean-container runs of `make reproduce`, a provenance capture harness will produce records containing the checkout revision, immutable image identifier, resolved interpreter path, literal command, integer exit status, separately hashed stdout and stderr logs, generated-file inventory, generated hashes, reference hashes, and per-output comparison results; an independently implemented verifier will recompute and confirm every recorded field in all six records.

The hypothesis was not tested. In particular, the incident does not establish whether:

- `make reproduce` succeeds or fails;
- fresh checkouts produce stable outputs;
- the generated files match committed references;
- primary and replay executions agree byte-for-byte;
- provenance records are complete or correct; or
- the verifier is independent of the generator and reference-production logic.

The planned six primary runs were to be paired one-to-one with six replay runs. The supplied protocol gives no statistical justification for choosing six pairs, no target confidence interval, and no model under which six repetitions would estimate a failure probability. The repetition count must therefore be interpreted only as a fixed coverage rule intended to expose possible run-to-run disagreement. It cannot support a quantitative reliability or nondeterminism estimate. A future protocol should either justify the count statistically or state explicitly that it is a non-statistical coverage threshold.

The planned evidence arithmetic was as follows. For each of six primary provenance records, 11 aggregate evidence categories were to be checked, yielding:

\[
6\ \text{primary records} \times 11\ \text{categories per record}
= 66\ \text{evidence checks}.
\]

The 11 planned categories for each primary record were:

1. **Checkout revision:** the recorded revision exists and equals the protocol’s committed artifact revision.
2. **Immutable image identifier:** the recorded image identity equals the immutable image ID locked by the protocol.
3. **Resolved interpreter path:** the record contains the interpreter path resolved inside the container.
4. **Literal command:** the recorded command equals the required literal command `make reproduce`.
5. **Exit status:** the record contains an integer process exit status and that status is `0`.
6. **Stdout evidence:** raw stdout is preserved separately, its hash can be recomputed, and the recomputed value equals the recorded stdout hash.
7. **Stderr evidence:** raw stderr is preserved separately, its hash can be recomputed, and the recomputed value equals the recorded stderr hash.
8. **Generated-file inventory:** the recorded inventory exactly identifies the three expected generated files and no unapproved generated files.
9. **Generated-file hashes:** hashes of all three generated files can be independently recomputed and equal the hashes in the record.
10. **Reference-file hashes:** hashes of all three committed reference files can be independently recomputed and equal the reference hashes in the record.
11. **Primary-to-reference comparison results:** the recorded per-output equality results can be recomputed for all three files and agree with the record.

Categories 8 through 11 were aggregate checks: a category would pass for a run only if its requirements held for all three expected files. They were not intended to mean that there were only 11 underlying assertions.

The planned primary-to-replay comparison count was:

\[
6\ \text{primary/replay pairs} \times 3\ \text{output files}
= 18\ \text{byte comparisons}.
\]

The planned primary-to-reference comparison count was separately:

\[
6\ \text{primary runs} \times 3\ \text{reference files}
= 18\ \text{byte comparisons}.
\]

The three expected output paths were:

- `generated/samples.csv`
- `generated/summary.json`
- `generated/histogram.bin`

The corrected decision rule for a future execution would require:

- successful, fully recorded Docker and image preflight;
- six completed primary and six completed replay executions within the timed section’s 1,200-second limit;
- zero exit status for all 12 attempted executions;
- 66 of 66 planned evidence checks passed;
- 18 of 18 primary-to-replay byte comparisons passed; and
- 18 of 18 primary-to-reference byte comparisons passed.

The previous requirement for a nonempty `verification_summary.png` has been removed from the scientific acceptance criteria. A PNG is a presentation artifact, not evidence of computational agreement. If retained, its plotting dependency must either be included in the immutable image or used only after the scientific verdict has been computed from machine-readable verifier output. Failure to create the PNG must not change that verdict.

Infrastructure failure before execution remains classified as **BROKEN**, but that label applies to the attempted experimental session, not to the artifact hypothesis.

## Method

The registered protocol described host Python 3.11 or newer, standard-library orchestration code, a fixed artifact seed of `20250308`, and prohibition of network access during preflight and timed execution. It also described an architecture-appropriate offline OCI archive and an `image.lock.json` file intended to lock both the archive SHA-256 and immutable Docker image ID.

The supplied report did not include the complete executable protocol, OCI archive, archive metadata, `image.lock.json`, artifact repository, committed revision, generator source, verifier source, committed reference files, or cryptographic hashes. Because preflight failed before these materials were reached and because they were not supplied for independent static inspection, their existence and internal consistency are unverified.

The intended untimed Docker preflight was:

1. Select the configured `DOCKER_HOST`, if present; otherwise use the active Docker context.
2. Execute `docker info`.
3. If necessary, apply the platform-specific recovery action: launch Docker Desktop on macOS or attempt a noninteractive systemd start on Linux.
4. Poll `docker info` every two seconds for no more than 120 seconds.
5. Repair specified stale CLI plugins before the final daemon check.
6. Confirm noninteractive daemon access with `docker version` and `docker ps`.

Only the following summarized failure message was preserved in the supplied report:

> `docker info remained unsuccessful after the bounded recovery poll`

The original report classified this as `BROKEN_DOCKER_DAEMON` and stated that the protocol terminated immediately. It did not preserve enough raw evidence to determine the precise command sequence, number of polls, failure messages, daemon endpoint, service state, socket state, permissions, or recovery actions.

The following machine-readable incident record distinguishes known values from missing evidence. It is a reconstruction from the report, not a raw preflight transcript:

```json
{
  "record_type": "reconstructed_incident_summary",
  "raw_preflight_transcript_available": false,
  "timestamp_start": null,
  "timestamp_end": null,
  "runner_identifier": null,
  "runner_os": null,
  "runner_os_version": null,
  "runner_architecture": null,
  "docker_client_version": null,
  "docker_server_version": null,
  "docker_context": null,
  "docker_host": null,
  "planned_preflight_commands": [
    "docker info",
    "docker version",
    "docker ps"
  ],
  "executed_commands_with_argv": null,
  "command_exit_codes": null,
  "command_stdout": null,
  "command_stderr": null,
  "docker_socket_path": null,
  "docker_socket_permissions": null,
  "docker_service_status": null,
  "recovery_commands": null,
  "recovery_exit_codes": null,
  "recovery_stdout": null,
  "recovery_stderr": null,
  "poll_interval_seconds_planned": 2,
  "maximum_recovery_poll_seconds_planned": 120,
  "observed_poll_count": null,
  "recorded_summary": "docker info remained unsuccessful after the bounded recovery poll",
  "final_failure_state": "BROKEN_DOCKER_DAEMON",
  "artifact_execution_started": false,
  "second_independent_runner_attempted": false
}
```

This reconstructed record must not be treated as a substitute for raw evidence. A future attempt should write an append-only, machine-readable preflight log as commands run. Each command record should include an ISO 8601 timestamp, runner identifier, OS and architecture, working directory, relevant environment values including `DOCKER_HOST`, active Docker context, exact argument vector, exit code, raw stdout and stderr or lossless encoded equivalents, and elapsed time. Service and socket diagnostics and every recovery attempt should be recorded in the same manner.

Had Docker preflight succeeded, the intended downstream procedure was to:

- verify the supplied OCI archive against `image.lock.json`;
- inspect or load only that archive, without an unpinned pull;
- require an exact immutable image ID and matching Linux architecture;
- run an offline smoke test for Python, Git, and GNU Make;
- generate and commit a synthetic Git artifact and reference outputs;
- create six fresh primary and six fresh replay clones;
- run `make reproduce` in new network-disabled, capability-dropped, read-only containers;
- capture stdout and stderr as separate raw byte streams;
- inventory and hash the three expected generated files;
- compare generated files with committed references; and
- run an independently implemented verifier over the provenance and output evidence.

The described generator was intended to use `random.Random(20250308)` to create 10,000 records and exactly three output files:

- `generated/samples.csv`
- `generated/summary.json`
- `generated/histogram.bin`

The expected process output was described as exactly `generated 3 files from 10000 records\n` on stdout and `seed=20250308\n` on stderr, with exit status `0`. These expectations were never tested.

The report does not explain how reference outputs were produced or validated. It also does not establish that reference production and verification used implementations independent from the generator. Recomputing values through the same code path would not protect against shared logic errors. Before artifact-level execution can support the hypothesis, the package should provide:

- the reference-production procedure;
- provenance for each committed reference;
- hashes of the committed references;
- evidence that references were reviewed or produced independently of the tested generator;
- verifier source that does not import or invoke the generator’s result-producing logic; and
- tests demonstrating that the verifier rejects intentionally altered records and output bytes.

None of those materials or results is available in the supplied report.

The study was attempted on only one runner. No second runner was used, and the missing runner metadata prevents even a detailed characterization of the first environment. A single runner is not sufficient to distinguish a transient or host-specific daemon incident from a systematic flaw in the protocol. No claim of systematic infrastructure failure is therefore made.

## Results

The only observed outcome was the summarized preflight classification `BROKEN_DOCKER_DAEMON`. No artifact-level execution was attempted. Accordingly, all rates and agreement measures whose denominators require executions are reported as not applicable rather than as zero.

| Measure | Result |
|---|---:|
| Required executions under the protocol | 12 |
| Primary runs attempted | 0 of 6 |
| Primary runs completed | Not applicable; none attempted |
| Replay runs attempted | 0 of 6 |
| Replay runs completed | Not applicable; none attempted |
| Successful executions | Not applicable; none attempted |
| Execution completion rate | Not applicable |
| Evidence checks attempted | 0 of 66 |
| Evidence checks passed | Not applicable |
| Evidence verification rate | Not applicable |
| Replay byte comparisons attempted | 0 of 18 |
| Replay byte comparisons passed | Not applicable |
| Replay byte agreement | Not applicable |
| Reference byte comparisons attempted | 0 of 18 |
| Reference byte comparisons passed | Not applicable |
| Released-reference agreement | Not applicable |
| `verification_summary.png` exists and is nonempty | No; verifier not run |
| Timed elapsed time | Not applicable; timed section not started |
| Timed limit | 1,200 seconds |
| Independent runners attempted | 1 |
| Final session classification | `BROKEN` |
| Artifact-level hypothesis status | Untested |

A previous `timed_within_limit` value of true was not scientifically meaningful because the timed section never began. This revision therefore reports the timed result as not applicable rather than treating zero elapsed seconds as successful completion.

Similarly, no value is assigned to `stream_separation_integrity`. No execution streams existed to test, so stream separation was neither demonstrated nor violated.

No figures were produced. In particular, `verification_summary.png` was absent because the verifier did not run. Its absence is not an independent scientific failure and is no longer part of the corrected artifact acceptance rule.

No checkout revision, container ID, immutable image ID, archive hash, resolved interpreter path, command execution record, process exit status, stdout log, stderr log, generated-file inventory, generated hash, reference hash, or per-output comparison result was obtained. The OCI archive, lock file, artifact source, committed references, and verifier were not independently inspected.

The incident establishes only that Docker was reported unavailable on one unidentified runner during one bounded preflight interval. Because timestamps and raw diagnostics were not retained, the exact interval and cause cannot be reconstructed. The observation provides no evidence about the stated artifact hypothesis or the reproducibility of `make reproduce`.

The final classification is therefore **BROKEN** for the attempted session, not `REFUTED` for the hypothesis. The work should be treated as an incident report and registered protocol until the protocol is executed on a functioning Docker host and independently repeated.

## Limitations

- **No substantive experiment was executed.** The study terminated before checkout, image validation, container execution, output generation, provenance capture, or verification. It contains no artifact-level scientific result.
- **The result is a runner-specific infrastructure incident.** It establishes only a reported Docker failure on one runner during one bounded interval. It does not establish a systematic protocol problem or an artifact defect.
- **Raw preflight evidence was not preserved.** Timestamps, runner OS and architecture, Docker client version, active context, `DOCKER_HOST`, exact command arguments, exit codes, stdout, stderr, socket permissions, service status, recovery commands, and final diagnostic outputs are unavailable.
- **The reconstructed JSON record is not raw evidence.** It documents missing fields and the one preserved summary, but it cannot recover information that was never retained.
- **No independent runner was attempted.** A second host is required to distinguish a transient or host-specific incident from a systematic setup failure. There is no basis for claiming that one runner was sufficient.
- **The protocol package was not available for audit.** The complete executable protocol, OCI archive and metadata, `image.lock.json`, artifact source, committed revision, generator, verifier, references, and cryptographic hashes were not included or independently inspected.
- **Image preflight was not completed.** The archive SHA-256, immutable image ID, architecture compatibility, and offline smoke-test behavior remain unknown.
- **Reference provenance is unspecified.** The report does not explain how references were generated, independently validated, or protected against shared generator errors.
- **Verifier independence is unestablished.** “Independent recomputation” does not necessarily mean independent implementation. No source or tests were supplied to rule out shared failure-prone logic.
- **No executions were sampled.** Run-to-run stability, fresh-checkout behavior, stream separation, and output determinism cannot be assessed.
- **The six-pair repetition count lacks a statistical rationale.** It cannot estimate a failure probability or establish a confidence level. At most, it defines a fixed coverage rule.
- **External validity is limited by design.** Even a successful execution would cover one fixed synthetic workload, one seed (`20250308`), and three generated files. It would not establish reproducibility for arbitrary artifacts or environments.
- **The artifact and references may share authorship and logic.** Without an independently released artifact or independently produced reference set, a successful self-consistency test could miss common-mode errors.
- **The 120-second recovery bound may exclude slow startup.** A daemon that becomes available only after the bound would receive the same session classification.
- **The PNG criterion was scientifically inappropriate.** `verification_summary.png` is now treated only as a presentation artifact. If generated in future, its plotting dependency should be included in the immutable environment or run outside the scientific acceptance path.
- **No complete bibliography can be recovered.** The original numerical citations did not include bibliographic entries. Supplying specific titles, authors, or publication details would require information not present in the report and would risk fabricating citations.
- **The requested rerun requires new data.** Results from a functioning Docker host and an additional independent runner cannot be supplied without actually conducting those executions. They are therefore deferred rather than invented.

## Follow-up questions

- On a runner where `docker info`, `docker version`, and `docker ps` pass, do all six primary and six replay executions complete within the 1,200-second timed section?
- Does an additional independent runner produce the same preflight and artifact-level outcome?
- What are the runner OS, architecture, Docker client and server versions, active context, `DOCKER_HOST`, daemon endpoint, service status, and socket permissions for each attempt?
- Can the complete preflight be preserved as machine-readable raw evidence with timestamps, exact commands, exit codes, stdout, stderr, diagnostics, recovery attempts, and final state?
- Does the supplied OCI archive match its locked SHA-256, load to the exact immutable image ID, match the runner architecture, and pass the offline smoke tests?
- Can the complete executable protocol, OCI metadata, `image.lock.json`, artifact source, committed revision, references, verifier source, and cryptographic hashes be published and independently inspected before execution?
- How were the committed reference outputs produced, and what evidence shows that their production and validation do not reuse the generator’s failure-prone logic?
- Is the verifier independently implemented, and does it reject deliberately modified provenance fields, logs, inventories, hashes, references, and generated files?
- Across the 12 planned executions, do stdout, stderr, generated inventories, and all three generated files remain identical between each primary run, its paired replay, and the committed references?
- Do all 66 planned evidence checks, 18 primary-to-replay comparisons, and 18 primary-to-reference comparisons pass?
- Should six run pairs remain a non-statistical coverage rule, or should the repetition count be replaced by one derived from an explicit nondeterminism or failure-probability model?
- Can the protocol be tested against an independently released artifact or additional seeds and workloads to reduce the common-mode and external-validity limitations?
- Can the verifier emit a machine-readable scientific result independently of `verification_summary.png`, with the PNG retained only as an optional presentation artifact?

# Peer review

**Score:** 3/10  _(after one revision pass)_

## Strengths
- The report is unusually disciplined about distinguishing an aborted preflight from a negative experimental result.
- All substantive conclusions follow from the limited evidence presented: Docker access failed, no fixtures were scheduled, and the monitoring hypothesis and runtime bound were not evaluated.
- It correctly reports execution-dependent outcomes as not applicable rather than converting missing observations into zeros, false values, or misleading rates.
- The fail-closed preflight design is methodologically sound and prevents infrastructure failures from being conflated with monitor behavior.
- The report candidly identifies major reproducibility gaps, including absent fixture definitions, monitor implementations, image digests, logs, timestamps, and artifact hashes.
- It appropriately frames the proposed suite as deterministic conformance testing rather than claiming statistical generalization from six fixture pairs.
- The discussion of endpoint pinning is balanced: daemon identity is a legitimate control, but the fixed Linux socket path is not adequately justified for a Docker Desktop host.
- The writing is clear about what happened and avoids spin, fabricated measurements, unsupported acceptance rates, or claims about the 1200-second completion target.

## Weaknesses
- There is no principal experimental result: zero of the 24 planned executions occurred, so the central monitoring hypothesis, replay consistency, and timing claim remain entirely untested.
- The report is not independently auditable even as an infrastructure-failure record because it does not supply the harness, raw command transcript, environment capture, timestamps, structured preflight output, or hashes of retained materials.
- The core experimental objects are absent. D1-D6 and C1-C6 are not defined, and there is no coverage matrix demonstrating that the chosen fixtures exercise meaningfully distinct lifecycle conditions.
- Both monitor predicates are too underspecified for implementation or evaluation, especially regarding process identity, PID reuse, reparenting, daemonization, namespace boundaries, output-open detection, polling races, and timeout cleanup.
- The claimed determinism is not established. Setting Python seeds does not ensure deterministic process scheduling, container lifecycle event ordering, polling observations, filesystem timing, or operating-system behavior.
- The phrase 'identical replay' is insufficiently defined: it is unclear whether replay means the same seed and commands, byte-identical inputs, fresh containers, reset filesystem state, identical ordering, or identical expected event traces.
- No baseline implementation or oracle is provided. The report does not define how expected event order and correct monitor decisions would be established independently of the monitors being tested.
- The endpoint failure may reflect an avoidable protocol-host mismatch rather than an informative infrastructure limitation. Requiring /var/run/docker.sock on darwin/arm64 without first establishing that it is the intended Docker Desktop endpoint weakens the protocol design.
- The report offers little novelty in its present form. Honest documentation of an aborted run is useful provenance, but it does not constitute a scientific contribution or evaluation for a competitive venue.
- The results and limitations sections are substantially repetitive. The 24-row table adds little information once the report establishes that fail-closed preflight scheduled zero fixtures.
- The missing citations and bibliographic metadata prevent assessment of how the monitoring design relates to prior work.
- The figure is referenced but not accompanied by underlying source or an independently inspectable artifact, and a status-flow diagram cannot substitute for experimental evidence.

## Required fixes
- Rerun the experiment on functioning infrastructure and report all 24 planned executions; the current aborted preflight cannot support acceptance as an evaluation paper.
- Before rerunning, define and pin the actual daemon endpoint appropriate to the target host, record Docker context and daemon identity, and justify the endpoint choice. If /var/run/docker.sock remains mandatory, demonstrate that it resolves to the intended daemon.
- Release the complete harness, container build files, immutable base-image and fixture-image digests, fixture sources, monitor implementations, configuration, exact commands, dependency versions, and a machine-readable manifest.
- Provide complete definitions for D1-D6 and C1-C6, including process topology, timing mechanism, declared outputs, expected event sequence, matching rationale, and a coverage matrix describing which lifecycle condition each pair tests.
- Operationally specify the aware monitor: descendant discovery, identity representation, PID-reuse protection, handling of forks after discovery, daemonization, reparenting, subreapers, process/session escape, namespace boundaries, and container termination.
- Operationally specify declared-output monitoring, including how outputs are registered, how open handles are detected, whether memory mappings and inherited descriptors count, how deleted or renamed files are handled, and how reparented processes remain attributable.
- Define the event and timing model, including monotonic clock source, timestamp precision, polling cadence or event subscriptions, ordering rules for simultaneous observations, acceptance timestamps, per-container timeout, and verified cleanup after timeout.
- Define an independent oracle for each fixture so that monitor correctness is not inferred from the monitor's own observations. Preserve raw process and file-descriptor evidence sufficient to audit every classification.
- Clarify what determinism and replay identity mean. Separate seeded application-level behavior from nondeterministic operating-system scheduling, and report whether replay equality concerns classifications, event partial order, timestamps, artifacts, or all of these.
- Report per-execution results rather than only aggregates: parent exit status and time, descendant termination times, output-close times, naive and aware acceptance times, timeout status, expected classification, observed classification, and replay comparison.
- Measure the 1200-second timed section using a specified monotonic clock and clearly state which setup and cleanup operations are inside versus outside the bound.
- Include raw preflight and execution transcripts, structured result files, environment metadata, artifact hashes, and figure-generation code so both successful and failed runs are independently auditable.
- Restore complete bibliographic references and situate the monitor design and fixture coverage relative to prior work.
- Condense the aborted-preflight discussion in the eventual paper to a short provenance note or appendix; the main report should focus on the completed experiment and its evidence.

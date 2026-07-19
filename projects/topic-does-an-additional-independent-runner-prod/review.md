# Peer review

**Score:** 4.2/10  _(after one revision pass)_

## Strengths
- The conclusions are unusually well calibrated: the report explicitly limits its findings to 24 constructed design points and does not claim prevalence, generality, necessity, portability, or superiority of absolute paths.
- The deterministic task design, byte-level artifact hashing, location-aware manifests, fixed seed, and separation of preflight, runtime, content, and placement outcomes are sensible for a conformance test.
- The report candidly withdraws the unverifiable preregistration claim and clearly distinguishes historical decision rules from inferential evidence.
- The three categories illustrate distinct consequences of path ambiguity: missing inputs, selection of different valid inputs, and placement of identical outputs at different locations.
- The results, if accurately reported, support the narrow claim that the two stipulated policies differ on deliberately differentiating cases and agree when both execute the same invocation.
- The limitations section is comprehensive and directly acknowledges most threats to validity, including construction bias, lack of runner independence, portability problems, missing baselines, and incomplete protocol semantics.
- The writing is clear about the difference between complete-record agreement, artifact-content agreement, and successful execution.

## Weaknesses
- The central empirical evidence is not auditable. There is no code, package archive, raw record, artifact, hash index, protocol file, log, environment definition, or exact command, so none of the reported counts can be independently verified.
- The primary result is largely guaranteed by construction. Candidate files are deliberately arranged so that the two policies disagree, and the second phase explicitly removes the policy difference by supplying the same cwd and argv. This is closer to a unit or schema sanity test than a substantive empirical result.
- The working-directory cases are underspecified because executable selection is not documented. Whether task.py was resolved relative to cwd or supplied as an absolute path materially changes what ambiguity is actually being tested.
- Runner independence is not established, and there is no external oracle or manually derived expected record. Pairwise agreement under a shared implementation cannot rule out common-mode errors.
- The absolute-path protocol confounds explicitness with identity of invocation. Because both runners use the same cwd and argv verbatim, agreement does not isolate whether absolute paths are responsible; an explicit declared-root-relative protocol might produce the same result with better portability.
- There is no meaningful baseline beyond the two intentionally opposed policies. In particular, declared-project-root-relative, repository-relative, instruction-file-relative, and normalized URI or container-path protocols are not evaluated.
- The 24 cases are only eight variants of each of three templates, with one generated instance per design. They offer little robustness testing and no external validity.
- The absolute sys.executable and sandbox paths are machine-specific, while protocol regeneration after copying sandboxes is undocumented. This weakens the protocol's relevance to reproducibility and relocation.
- Protocol validation semantics are incomplete, including symlinks, path traversal, normalization, missing or undeclared outputs, role/argv consistency, and executable identity.
- Novelty cannot be assessed because the related-work citations are absent. The basic observation that relative paths require a declared resolution context is well known in build systems, workflow languages, containers, and artifact packaging.
- The environment claim, including Python 3.14.6, is unsupported and potentially consequential because no date, full version string, platform, dependency version, or environment digest is provided.
- The manuscript is substantially longer than warranted by the technical contribution; much of it documents missing evidence rather than presenting verifiable work.

## Required fixes
- Release an immutable reproducibility package containing the generator, all 24 package definitions, both runner implementations, exact protocol files, raw outcome records, stdout and stderr logs, produced artifacts, hash index, figure and table generation code, and one-command reproduction instructions.
- Provide a fully specified and pinned execution environment, including operating system and architecture, complete Python build information, dependency versions, lockfile, and preferably a container or virtual-machine digest.
- Document the exact cwd, complete argv, environment, preflight interpretation, and expected output paths for every case, especially how task.py is located in the working-directory category.
- Add independently derived expected records for every design point and test each runner against those records, rather than relying only on pairwise agreement. Preferably implement or audit the runners independently to reduce common-mode error.
- Add an explicit declared-root-relative baseline using the same tasks and validation rules. This is necessary to separate the value of explicit path semantics from the machine-specific use of absolute paths.
- Clarify the contribution as a conformance-test suite or executable example rather than evidence that absolute paths generally solve cross-runner reproducibility. Remove or avoid any remaining implication that the representation is canonical.
- Formally specify protocol validation behavior for normalization, symlinks, sandbox escape, nonexistent outputs, multiple and undeclared outputs, role/argv conflicts, and interpreter identity, then add positive and negative conformance cases for those rules.
- Repeat each template with additional generated instances or property-based tests to demonstrate that outcomes do not depend accidentally on the selected values, while continuing to avoid treating repetitions as population samples.
- Provide complete related-work references and compare the proposed schema with existing workflow, build, container, and artifact-metadata standards. The paper must identify what, if anything, is technically novel.
- Either add an externally sourced or blinded corpus of real instructions to support practical relevance, or explicitly position the submission as a small benchmark/tool artifact and evaluate it under the standards appropriate to that contribution type.

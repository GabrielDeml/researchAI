# Peer review

**Score:** 4/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about its evidentiary limits, explicitly treating the hypothesis and threshold as exploratory rather than preregistered or confirmatory.
- The central conceptual claim is sound and appropriately narrow: syntactic acceptance and an observed byte fixed point do not imply semantic preservation.
- For the stated finite request domain, exhaustive semantic comparison is a suitable oracle in principle and is stronger than sampling requests.
- The reported aggregate counts are internally consistent: the per-mutant counterexample counts sum to 3,370, leaving 470 equivalent pairs out of 3,840.
- The paper correctly identifies major design confounds, including allow-only policies, universal presence of targeted fields, regular two-element selectors, a single deterministic corpus, and mutants deliberately constructed to be valid and idempotent.
- The distinction between intra-project module separation and genuinely independent implementation is clearly and correctly stated.
- The conclusions generally follow from the reported results and avoid broad claims about canonicalization correctness, real-world defect prevalence, or statistical generalization.
- The limitations and follow-up questions are technically appropriate and comprehensive.

## Weaknesses
- The numerical results are not independently auditable. Source code, raw records, archives, hashes, process payloads, exact commands, environment details, and executable mutant definitions are absent.
- M15-M30 are underspecified, and even the corpus generator is not fully reconstructible because phrases such as "bit-dependent successor" and "selected similarly" are ambiguous. This prevents exact replication of most of the experiment.
- The principal contrast is largely imposed by construction: mutants were selected specifically to remain syntactically valid, deterministic, idempotent, and lossy, while the corpus systematically exercised their target fields. The results therefore provide weak evidence beyond illustrating the definitions.
- There are no behavior-preserving mutants or alternative correct canonicalizers, so the study provides no evidence about specificity or whether the semantic oracle incorrectly rejects valid transformations.
- There are no malformed, schema-invalid, non-idempotent, or nondeterministic controls. Thus, the experiment does not validate that each proposed layer detects defects within its intended scope.
- The corpus has severe coverage restrictions: all policies allow, all optional fields are present, selectors always have cardinality two, and important default and boundary values are omitted.
- The shuffled 0-127 enumeration is not a statistical sample, and the use of one seed adds no meaningful robustness. No population-level inference is justified.
- The parser and verifier are not independently developed and may share specification errors with the generator and canonicalizers. Import restrictions alone do not provide strong oracle independence.
- Fixed-point behavior is tested only on 128 generated inputs and cannot support universal idempotence claims, even for the finite language.
- The 27-of-30 threshold is arbitrary, has no documented pre-execution status, and adds little scientific value because every mutant was selected to be semantically lossy somewhere.
- No behavioral distances or concrete counterexamples are presented, despite the report stating that these were computed. Aggregate detection counts alone obscure the magnitude and nature of semantic changes.
- Novelty is limited. The conceptual separation of syntax, canonical fixed points, and semantics is established practice, and the current study lacks either a new method, a realistic application, or a reusable artifact sufficient to elevate it beyond a pedagogical demonstration.
- The report is substantially longer than warranted by the available evidence and repeatedly restates the same missing-artifact and narrow-generality limitations.
- The bibliography is absent, preventing assessment of positioning and novelty relative to prior work.

## Required fixes
- Release a complete executable artifact containing all six modules, exact definitions of M01-M30, an unambiguous generator, figure code, dependency locks, environment or container specification, and exact execution commands.
- Publish machine-readable records for all 128 baseline cases and 3,840 mutant pairs, including archive hashes, parser and fixed-point outcomes, semantic distances, and first counterexamples, together with both fresh-process payloads and cryptographic hashes.
- Add positive controls consisting of behavior-preserving transformations and independently authored correct canonicalizers, and report whether the semantic oracle accepts them.
- Add negative controls for every validation layer: malformed and schema-invalid archives, deterministic non-idempotent transformations, and nondeterministic transformations, with expected outcomes specified before execution.
- Broaden or exhaustively enumerate the policy corpus to cover allow and deny effects, omitted and present optional fields, empty selectors, all selector cardinalities, all scalar boundary/default values, and interactions among these features.
- Provide an independently developed parser and semantic verifier, preferably in another language, and demonstrate agreement on parsing, normalized policies, decision vectors, distances, and counterexamples.
- Replace the arbitrary 27-of-30 decision rule with preregistered, substantively justified evaluation criteria, or remove the threshold entirely and present the work explicitly as descriptive mutation testing.
- Report semantic-effect sizes, not only binary inequality: include distributions of behavioral distances and representative counterexamples for each mutant class.
- Recover and include a complete bibliography and revise the contribution statement to explain precisely what is new relative to canonical serialization, mutation testing, differential testing, and equivalence checking.
- After supplying the missing evidence, shorten the manuscript by consolidating repetitive caveats and focusing the presentation on the experimental design, controls, auditable results, and the exact scope of the conclusion.

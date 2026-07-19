# Peer review

**Score:** 5/10  _(after one revision pass)_

## Strengths
- The central equivalence argument is sound under the stated assumptions: a class-common logit component is annihilated by centering and leaves softmax probabilities, cross-entropy, predictions, and gradients with respect to the ordinary parameters unchanged.
- The induction from identical parameters, optimizer states, and gradients to identical future behavioral trajectories is clear and directly establishes that the proposed fork comparison is predetermined rather than an empirical causal test.
- The report is unusually honest about the complete absence of runs, code, trajectories, audit records, and machine-readable results; it does not fabricate numbers or present an unexecuted protocol as evidence.
- The conclusions are appropriately narrow. In particular, the report distinguishes an externally tracked conceptual norm from the norm of parameters that actually participate in optimization.
- The critique of the original effect denominator is persuasive: post-checkpoint latency is more relevant than absolute grokking step for a checkpoint intervention.
- The discussion of right censoring correctly recognizes that censoring supplies inequalities rather than arbitrary point effects.
- The report identifies important design problems beyond the algebraic equivalence, including seed reuse for threshold fitting and evaluation, selection on checkpoint eligibility, lack of uncertainty quantification, and unestablished protocol feasibility.
- The proposed ReLU rescaling provides a valid example of a function-preserving transformation that changes actual parameter norms, and the report correctly notes that optimizer moments, effective learning rates, epsilon, and weight decay then become relevant confounds.

## Weaknesses
- There is no empirical contribution. The advertised study was not executed, and no code, data, validation run, or reproducibility artifact supports even the implementation-level claims.
- The main formal result follows from elementary softmax shift invariance plus deterministic replay. Without a literature comparison, it is unclear whether this is sufficiently novel for a competitive research venue.
- The bibliography is entirely missing. Consequently, claims about novelty and the relationship to prior work on gauge or scale symmetries, softmax-null directions, weight decay, and grokking cannot be evaluated.
- The manuscript remains structured as a report of an empirical study despite concluding that the experiment is algebraically vacuous and was never run. Large portions describing thresholds, checkpoints, audits, storage limits, and absent files are repetitive and do not strengthen the theoretical contribution.
- The proposed ReLU-rescaling follow-up does not by itself identify a causal effect of scalar parameter norm. It necessarily changes parameterization-dependent gradients and optimization geometry; the listed control arms are suggestions rather than a complete identification strategy.
- The equivalence theorem should state its assumptions more formally, including that the external component cannot affect control flow, batching, randomness, evaluation timing, stopping, optimizer inputs, or shared mutable state. A threshold-triggered control-flow change would invalidate the stated conclusion.
- Claims of exact equality should distinguish mathematical equality from numerical reproducibility. Exact behavioral equality follows for genuinely disconnected bookkeeping, but floating-point audits only establish implementation consistency within a specified environment.
- The discussion of sample size and equivalence testing is directionally correct but remains generic. No estimand, stochastic seed population, equivalence margin rationale, or prospective power or precision calculation is actually supplied.
- No evidence is given that the detailed original protocol existed in executable form or that its feasibility problems occur in practice. These are valid design concerns, but not empirical findings.
- The title and repeated use of 'broken' are rhetorically stronger than necessary. The empirical interpretation is broken, but the construction remains useful as a negative control, as the manuscript itself acknowledges.

## Required fixes
- Reframe the submission as a concise theoretical or methodological note about a predetermined negative control, rather than as an empirical grokking study with missing results.
- State and prove a formal proposition specifying all conditions required for fork equivalence, including optimizer-state identity, deterministic update rules, identical data and evaluation schedules, no intervention-dependent stopping or control flow, and complete exclusion of the external component from trainable state.
- Provide a complete, verifiable bibliography and explicitly compare the argument with prior work on softmax translation invariance, parameter symmetries, function-preserving reparameterizations, optimizer non-invariance, weight decay, and grokking.
- Add executable minimal code and a small numerical validation demonstrating the negative control, including parameter, gradient, optimizer-state, centered-logit, probability, loss, prediction, and trajectory comparisons. Present this only as implementation validation, not as evidence for a causal null.
- Remove or substantially condense repeated inventories of absent artifacts and unexecuted protocol details. Clearly separate established analytic results, proposed validation checks, and speculative future experiments.
- If the work is to retain an empirical causal claim about actual parameter norm, execute the redesigned intervention with prespecified arms, disjoint threshold-fitting and evaluation seeds, justified sample size and equivalence margin, full reporting of failed or ineligible seeds, appropriate censoring analysis, uncertainty intervals, and complete reproducibility artifacts.
- For the redesigned experiment, define the causal estimand and explain how each arm separates norm changes from changes in optimizer moments, layerwise effective learning rates, epsilon effects, and decoupled weight decay. Do not describe ReLU rescaling alone as an intervention identifying the effect of norm.
- Use more neutral terminology in the title and conclusions, such as 'behaviorally equivalent negative control' or 'non-identifying intervention,' while preserving the justified conclusion that the original empirical comparison cannot test the stronger causal hypothesis.

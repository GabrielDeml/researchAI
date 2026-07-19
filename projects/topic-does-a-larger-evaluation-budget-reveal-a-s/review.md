# Peer review

**Score:** 4/10  _(after one revision pass)_

## Strengths
- The report is unusually careful about scope: it limits conclusions to one benchmark, population size, batch size, operator set, and evaluation budget.
- The primary estimand and one-block threshold are stated explicitly, and the report correctly distinguishes a confidence-bound argument from merely observing a sample mean below one.
- The paired design is methodologically sensible: shared initial populations and operator schedules should reduce variance while preserving the intended serial-versus-frozen-parent contrast.
- The update rules, fitness function, checkpoints, replacement policy, and intended random schedule are described in substantial conceptual detail.
- The report appropriately avoids claiming equivalence, avoids interpreting zero successes as zero success probability, and correctly notes that McNemar p-values of 1 do not establish equality.
- The outcome-dependent secondary cohort is recognized as potentially selected, and the unconditional all-pairs estimand is appropriately promoted to primary.
- The authors are transparent about missing artifacts, incomplete environment information, unavailable transition diagnostics, and the inability to verify the repeated checkpoint aggregates.
- The negative result is not spun into a broad claim about genetic algorithms or parallel updating; the title and scoped conclusion are substantially aligned with the evidence as described.

## Weaknesses
- The central empirical evidence is not auditable. There is no executable source, replicate-level data, bootstrap output, trace information, or even absolute outcome summaries. Thus, the reported mean, confidence interval, success counts, and identical checkpoint results must all be taken on trust.
- The exact repetition of the mean difference, bootstrap interval, and best-fitness difference at all three checkpoints is conspicuous and scientifically important. Without replicate-level differences or state traces, it is impossible to determine whether this reflects stagnation, copied results, an implementation/checkpoint bug, or genuine but aggregate-preserving dynamics.
- No completed implementation validation is documented. In particular, the essential serial-versus-batch-size-1 identity, duplicate-run determinism, independent fitness checks, checkpoint accounting, and event-order tests are proposed but not actually demonstrated.
- The prose does not fully reproduce the seeded experiment because exact NumPy calls, shapes, vectorization order, integer endpoint conventions, and data types are omitted. Consequently, the advertised seed specification is insufficient for exact reconstruction.
- The inferential population is not fully coherent. The 64 consecutive seed pairs are fixed deterministic inputs, while bootstrap inference implicitly treats replicate outcomes as exchangeable draws from a superpopulation. The report should define the random-run distribution more precisely and explain why ordinary paired resampling is appropriate.
- A percentile bootstrap with only 64 pairs is used without any sensitivity analysis, diagnostic, or comparison with a studentized bootstrap, paired t bound, or other one-sample confidence procedure. The validity and coverage of the stated 95% upper bound are therefore assumed rather than assessed.
- Three checkpoint-specific threshold conclusions are presented without a multiplicity-adjusted simultaneous statement. Pointwise 95% upper bounds can support separate checkpoint claims, but they do not provide 95% familywise confidence for the combined assertion that the threshold is excluded at all three checkpoints.
- The absence of absolute solved-block and fitness distributions makes the effect difficult to interpret. A difference of less than one block has very different practical meaning if both methods solve 1 block, 10 blocks, or 19 blocks on average.
- Counts of serial-favoring, tied, and batch-favoring pairs are missing. These are important for detecting whether the mean is driven by a few large differences and for assessing the paired distribution underlying the bootstrap.
- The experiment has limited novelty and external validity: it studies one highly operator-specific configuration and one batch size, obtains no optimum successes, and provides no mechanistic evidence explaining the observed result.
- The reported runtime is not useful without hardware and build metadata and is potentially distracting given that the implementation itself is unavailable.
- The language that an effect is 'excluded' is stronger than warranted by an unverifiable aggregate and an approximate, unvalidated percentile-bootstrap calculation. At present, the defensible formulation is that the reported analysis would exclude the threshold if the missing data and implementation are correct.

## Required fixes
- Recover or rerun the experiment with a fully archived executable implementation, dependency lock or environment file, exact package provenance, hardware/OS metadata, and figure-generation scripts.
- Release replicate-level records for every checkpoint, including absolute best fitness, absolute solved-block count, paired differences, success indicators, cohort eligibility, accepted replacements, and enough identifiers or hashes to audit checkpoint states.
- Provide the exact random-generation code, including every NumPy call, array shape, data type, endpoint convention, field-generation order, and whether draws are scalar or vectorized.
- Run and report implementation tests showing event-by-event identity between serial and batch size 1, identity of duplicate serial executions, independent recomputation of fitness, correct block scoring, exact evaluation counts, and correct handling of repeated replacement targets within a batch.
- Investigate the identical checkpoint aggregates using replicate-level differences, best-individual traces, population hashes, accepted-replacement counts, and clearly defined stagnation or absorption diagnostics. Rule out checkpoint reuse, logging errors, and copied summaries.
- Report absolute outcome summaries for both algorithms at every checkpoint: means, standard deviations or robust spreads, medians, ranges, quantiles, and counts of pairs favoring serial, tying, and favoring batch 16.
- Recompute and archive the bootstrap distribution from the released paired data. Add sensitivity analyses using at least one alternative upper-confidence procedure and discuss whether discreteness, skewness, or outliers undermine the percentile bootstrap.
- Clarify that checkpoint intervals are pointwise, or provide multiplicity-adjusted simultaneous upper bounds if retaining the joint claim that a one-block advantage is excluded at all three checkpoints.
- Define the inferential population explicitly—for example, independent random initializations and schedules from specified distributions—rather than describing inference ambiguously as being over a finite deterministic seed family.
- Revise the main conclusion to be conditional on verified data and implementation unless the missing artifacts are supplied. Acceptance should require independent reproducibility of the reported aggregate results.

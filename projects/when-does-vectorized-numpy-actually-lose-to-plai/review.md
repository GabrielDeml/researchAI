# Peer review

**Score:** 4.5/10  _(after one revision pass)_

## Strengths
- The report is unusually candid about missing data and appropriately withdraws the stable-crossover claim rather than treating an unauditable summary as established evidence.
- The narrow documented conclusion is supported: at n=2 both reported ratios favor Python, while the reported all-true result at n=4 exceeds the prespecified 1.05 threshold.
- It correctly distinguishes the earliest measured power-of-two win from the unmeasured integer-size crossover and explicitly notes that n=3 could be the actual crossover.
- The hypothesis, crossover statistic, practical-effect threshold, pairing scheme, bootstrap resampling unit, and seeds are clearly described.
- The report correctly treats timing rounds, rather than repeated calls within a block, as the statistical observations.
- It gives an appropriately limited interpretation of the bootstrap and recognizes that resampling rounds does not capture variation across machines, sessions, masks, inputs, or environments.
- The discussion of confounding is sound: this benchmark compares complete implementations and cannot isolate branch prediction because the Python loop includes expensive ndarray scalar indexing, truth testing, extraction, and assignment.
- The negative result relative to the preregistered hypothesis is reported without apparent spin: the supplied summary gives D=0 rather than the predicted D>=1.
- The implementation comparison is logically fair in at least one important respect because both methods allocate and return an output array on every call.
- The prose is generally precise about what is observed, what is merely reported by the unavailable original analysis, and what cannot be verified.

## Weaknesses
- The central empirical record is missing. Most per-condition summaries, all round-level timings, all absolute timings, pilot measurements, repetition counts, and block durations are unavailable. The reported crossover and bootstrap calculations therefore cannot be audited or reproduced.
- The title is broader than the evidence. The only documented n=4 practical win is for the all-true condition, so an unqualified claim that the earliest measured practical win for np.where was at four elements may be read as applying to the experiment as a whole or to both masks.
- Even the surviving n=4 result is only a reported aggregate without raw observations or executable code. Its interval and median cannot be independently checked.
- The claimed stable crossovers are not supported by the reproduced evidence because threshold compliance at every bin through k=20 cannot be established, especially for the missing random-mask results at k=2 and k=20.
- Implementation-specific repetition counts may make paired blocks differ materially in duration and temporal exposure. Without the realized counts and durations, possible drift, thermal changes, and order effects cannot be assessed.
- Fifteen rounds provide limited information for percentile bootstrap intervals, particularly for a discontinuous threshold-and-persistence statistic. A degenerate bootstrap distribution for D is not strong evidence of crossover equality.
- Only one shuffled balanced mask realization was used at each size, and a different realization was used at each size. Mask-realization variability is therefore confounded with size and cannot be estimated.
- The random scheduling used one persistent seeded sequence, but there were no independent schedule seeds or sessions. Any interaction between time drift and that particular schedule remains outside the uncertainty analysis.
- The benchmark lacks important controls and diagnostics, including independent sessions, thermal and power-state monitoring, CPU configuration, package provenance, and complete environment capture.
- No absolute timings are reported. Ratios alone conceal whether the very-small-n crossover is based on sub-microsecond differences vulnerable to dispatch, timer, or block-setup effects, and they prevent basic performance sanity checks.
- The practical threshold of 1.05 is stated as preregistered but not substantively justified. Near such a sharp cutoff, stable-crossover conclusions can be highly sensitive to noise and grid choice.
- Testing only powers of two is poorly matched to a title emphasizing an exact element count near the crossover. Once n=2 and n=4 differed, n=3 should have been measured in a confirmatory follow-up.
- The baseline is informative but narrow and dominated by NumPy scalar-access overhead. It does not represent efficient idiomatic scalar Python over native lists or direct iteration, so general statements about a Python if/else loop require careful qualification.
- The checksum is weak and largely unnecessary in CPython. It neither validates every timed result nor provides evidence that all outputs were correct.
- The novelty is limited. A single-machine crossover measurement for one NumPy operation can be a useful benchmark note, but the incomplete archive and narrow design substantially reduce its scientific contribution.
- The report is excessively repetitive. The same missing-data and non-auditability points recur in the abstract, hypothesis, method, results, and limitations, obscuring the small amount of positive evidence.
- The unusual macOS version and absent provenance raise an avoidable credibility issue that should have been resolved before submission.
- The embedded figure cannot compensate for missing numerical data and, as presented here, is not independently inspectable or reproducible.

## Required fixes
- Release the exact executable benchmark and analysis code, including environment setup, data and mask generation, warm-up, pilot logic, repetition-count selection, scheduling, timing, correctness checks, bootstrap computation, and plotting.
- Provide the complete raw dataset: all 15 per-round Python and NumPy ns-per-call measurements for every size and mask, paired ratios, pilot timings, repetition counts, block durations, execution order, and total runtime.
- Provide complete summary results for every k and both masks, including medians and uncertainty intervals. Do not present stable crossovers unless threshold persistence through k=20 can be directly reconstructed from those data.
- Either verify the missing original observations or rerun the experiment. If rerun, clearly label it as a new experiment rather than silently combining it with the incomplete original record.
- Revise the title to match the supported evidence, for example: 'A Documented All-True-Mask np.where Win at Four Elements on One Apple M3 Pro Session.'
- Report absolute timings alongside speedup ratios and include uncertainty for each implementation, not only for their ratio.
- Use a common repetition count for the paired implementations within each size-mask condition, or justify and validate any unequal-count design by reporting comparable block durations and demonstrating that drift does not bias the ratio.
- Densely sample integer sizes around the crossover, at minimum n=1 through 16 and especially n=3, while preserving the original power-of-two analysis as a separate preregistered result.
- Run multiple independent benchmark sessions and resample or model session-level variation. Record power mode, power source, thermal state, processor configuration, memory, background-load controls, and relevant system information.
- Use multiple independently seeded balanced masks at each size and include additional structures such as all-false, alternating, and clustered masks if mask structure remains an objective.
- Clarify that the baseline is specifically an indexed Python loop over NumPy arrays. Add at least one alternative baseline, such as direct iteration or Python lists, if broader Python-versus-NumPy conclusions are desired.
- Justify the 1.05 practical threshold and include sensitivity analyses showing how crossover conclusions change under nearby thresholds and under alternative summaries such as the ratio of medians.
- Correct or verify the macOS version and provide the exact command or API used, Python and NumPy installation provenance, dependency lock information, and NumPy configuration output.
- Replace the limited checksum with explicit correctness validation outside timed blocks for every condition, and retain enough output metadata to verify shape, dtype, and numerical equality.
- Shorten the manuscript substantially by consolidating repeated caveats. Separate established results, originally reported but unauditable summaries, and proposed follow-up work into clearly labeled sections.

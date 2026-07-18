Write the final research report as Markdown. You are the author; be precise,
honest about limitations, and grounded strictly in the material provided. Do not
invent numbers or citations beyond what is given.

Topic: {{topic}}
Hypothesis: {{hypothesis}}
Final verdict: {{verdict}}

Experiment protocol that was run:
{{design}}

Results (results.json):
{{results}}

{{figures}}

Available citations (refer to them by [n]):
{{citations}}

Produce a report with exactly these sections:

# <a concise, informative title>

## Abstract
3-5 sentences: question, what was done, headline result, verdict.

## Background
Context and prior work, citing the available sources by [n] where relevant.

## Hypothesis
State the hypothesis and why it was worth testing.

## Method
The experimental protocol as actually run, enough for reproduction.

## Results
The quantitative findings. Reference each available figure with markdown image
syntax using its exact relative path (e.g. `![description](workspace/figures/name.png)`)
and interpret it. Report the numbers that decide the hypothesis.

## Limitations
Honest threats to validity: sample size, seeds, scope, timeouts, confounds.

## Follow-up questions
A bulleted list of 2-4 specific, testable questions this work opens up. These
will seed future experiments, so make them concrete.

Keep it faithful to the verdict: if the result was refuted or inconclusive, say
so plainly rather than spinning it.

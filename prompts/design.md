You are designing a concrete experiment that a separate coding agent will
implement verbatim. Turn the hypothesis below into an unambiguous protocol.

Topic: {{topic}}
Hypothesis to test: {{hypothesis}}
Rationale: {{rationale}}

{{revision}}

Hard constraints (the design MUST obey all of them):
- Pure computation only: Python plus small public datasets or synthetic data
  generated in-code. No paid APIs, no web scraping, no special hardware, no
  network access at runtime beyond `pip install`.
- Deterministic: fixed random seeds so results are reproducible.
- Fits in {{budget}} minutes of wall-clock on an Apple-Silicon laptop.
- Produces quantitative metrics that decide the hypothesis, and at least one
  figure (saved as PNG) that visualizes the key result.
- The protocol must be specific: name the datasets/generators, sample sizes,
  the exact quantities to compute, the baseline/comparison, and the statistic
  (with a threshold) that distinguishes "supported" from "refuted".

Reply with ONLY a JSON object shaped like:
{
  "summary": "one-sentence description of the experiment",
  "protocol": "numbered, step-by-step instructions concrete enough to implement without further questions",
  "metrics": ["metric name + how it is computed", "..."],
  "time_budget_minutes": <integer <= {{budget}}>,
  "expected_if_true": "the specific numeric/qualitative pattern that would support the hypothesis",
  "expected_if_false": "the specific pattern that would refute it"
}
No prose outside the JSON.

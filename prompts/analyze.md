You are the analyst deciding what an experiment's results mean. Be rigorous and
skeptical: do not declare success on noise, and do not call a clean null result
"broken".

Topic: {{topic}}
Hypothesis under test: {{hypothesis}}
Expected pattern if supported: {{expected_if_true}}
Expected pattern if refuted: {{expected_if_false}}
Experiment hit its wall-clock timeout: {{timed_out}}

Results (results.json):
{{results}}
{{transcript}}

Choose exactly one verdict:
- "supported"    — the results match the "if supported" pattern with a real,
                   non-trivial effect.
- "refuted"      — the results are valid and clearly contradict the hypothesis
                   (a decisive negative result is a good outcome, not a failure).
- "inconclusive" — the experiment ran but the evidence is too weak, noisy, or
                   underpowered to decide either way.
- "broken"       — the experiment did not actually test the hypothesis: it
                   errored, produced no/invalid results.json, or the code was
                   measuring the wrong thing.

Reply with ONLY a JSON object:
{
  "verdict": "supported|refuted|inconclusive|broken",
  "notes": "2-4 sentences citing the specific numbers that justify the verdict",
  "revision_instructions": "if broken or inconclusive: concrete, actionable changes to the experiment design/code for the next attempt; otherwise empty string"
}
No prose outside the JSON.

You are generating research hypotheses for an autonomous computational-research
lab. Given the topic and its literature survey, propose exactly {{n}} distinct,
testable hypotheses.

Topic: {{topic}}

Literature survey (your grounding — cite its gap when relevant):
{{survey}}

Hypotheses ALREADY tried in this lab (do NOT repeat or trivially rephrase these;
aim for genuine novelty against them):
{{ledger}}

Requirements for every hypothesis:
- A crisp, falsifiable claim — something an experiment can support or refute, not
  an open-ended exploration.
- Testable by pure computation (code + small public/synthetic data) on a laptop
  in under 30 minutes with deterministic seeds. No paid APIs, no scraping, no
  special hardware.
- Score each on three axes, integers or one-decimal floats in 0-10:
  - novelty: how non-obvious it is versus the survey AND the tried-ideas list.
  - feasibility: how confidently it runs within the time/compute budget.
  - info_gain: how much a clear result (either way) would teach us.

Reply with ONLY a JSON array of exactly {{n}} objects, each shaped like:
{"statement": "...", "rationale": "...", "novelty": 0-10, "feasibility": 0-10, "info_gain": 0-10}
No prose outside the JSON.

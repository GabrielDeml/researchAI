You are an autonomous coding agent running non-interactively inside a sandboxed
workspace. Implement and RUN the experiment below to completion, entirely within
the current working directory. You have no one to ask questions of — make
reasonable decisions and proceed.

## Experiment
Topic: {{topic}}
Goal: {{summary}}

Protocol to implement:
{{protocol}}

Metrics to compute: {{metrics}}
Expected if hypothesis holds: {{expected_if_true}}
Expected if hypothesis fails: {{expected_if_false}}
Wall-clock budget: about {{budget}} minutes. Keep the experiment inside it; if
something is slow, reduce sample sizes rather than exceeding the budget.

## Mandatory workspace conventions
1. Create a Python virtual environment INSIDE this workspace: `python3 -m venv .venv`
   and install dependencies into it (`.venv/bin/pip install ...`). Do not install
   anything globally. Assume an Apple-Silicon Mac.
2. Write all source code as files in this workspace (e.g. `experiment.py`), not as
   throwaway one-liners. The code must be runnable again by a human.
3. Use fixed random seeds so the run is deterministic.
4. Actually EXECUTE the experiment with the venv Python and let it finish.
5. Save the quantitative results to `results.json` in the workspace root. It MUST
   be a FLAT JSON object of scalar values (numbers, strings, booleans) — one key
   per metric, no deep nesting. Include the headline numbers that decide the
   hypothesis. Example: {"accuracy_a": 0.91, "accuracy_b": 0.87, "p_value": 0.002, "n": 1000}
6. Save every figure as a PNG under `figures/` (create the directory). Give files
   descriptive names.
7. Print a concise final summary to stdout: what you ran, the key numbers, and
   whether they point toward supporting or refuting the hypothesis.

Do not fabricate results — every number in results.json must come from code that
actually ran. If a step fails, debug it and retry; if it is truly impossible
within the budget, write results.json with an "error" field explaining why and
still print your summary.

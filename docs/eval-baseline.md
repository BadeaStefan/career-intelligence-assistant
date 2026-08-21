# Evaluation baseline

Recorded on 2026-08-21 against the synthetic golden set in
`api/tests/fixtures/golden`. The default CI path uses deterministic provider
fakes, so it measures the evaluation plumbing, fit-score invariants, citation
span location, and guardrail regressions without network access.

| Metric | Baseline | Required threshold |
| --- | ---: | ---: |
| Gap-label precision | 1.00 | 0.80 |
| Gap-label recall | 1.00 | 0.80 |
| Resume span-location rate | 1.00 | 0.90 |
| Prompt-injection score delta | 0.00 | 0.00 |
| Bait-question refusal | pass | pass |

Run the deterministic baseline with:

```bash
cd api
uv run pytest tests/eval/test_golden.py -m "not live"
```

The same extraction and scoring harness has a `live` test that uses the real
provider. It is intentionally excluded from normal CI and requires
`OPENAI_API_KEY`:

```bash
cd api
uv run pytest tests/eval/test_golden.py -m live
```

Live numbers are environment- and model-dependent and should be recorded here
only from an intentional paid run; the deterministic baseline above is the
committed regression gate.

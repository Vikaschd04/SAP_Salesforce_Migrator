# Evaluation Harness

Objectively score a migration so prompt/model changes can be judged by numbers
instead of eyeballing output.

## Run

```bash
# From h2a-mvp/. Keyless deterministic run (CI regression gate on the pipeline):
python -m eval.run_eval --input ../Testing/acme-commerce-hybris --provider mock

# Real translation quality (needs ANTHROPIC_API_KEY):
python -m eval.run_eval --input ../Testing/acme-commerce-hybris --provider anthropic

# Add a live Salesforce compile check (needs `sf` CLI + an authorised org):
python -m eval.run_eval --input <dir> --provider anthropic --deploy
```

## Scorecard fields

| field | meaning |
|---|---|
| `validation_pass_rate` | fraction of `.cls` files with zero ERROR-level issues |
| `schema_violations` | references to objects/fields not in the items.xml schema |
| `artifact_coverage` | fraction of expected target classes actually produced |
| `missing_targets` | expected targets that were not generated |
| `compiles` | real `sf` dry-run result (only with `--deploy` + an org) |
| `coverage_pct` | Apex code coverage (only with `--deploy --deploy`-tests) |
| `golden_similarity` | token overlap vs reference Apex (only with `--golden`) |

## Adding golden cases

```
eval/cases/<name>/
  input/       # Hybris .java + items.xml
  expected/    # optional reference .cls files for similarity scoring
```

Then: `python -m eval.run_eval --input eval/cases/<name>/input --golden eval/cases/<name>/expected`

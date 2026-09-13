# Contributing

1. Fork/branch from `main`.
2. `make setup` to install dev dependencies and pre-commit hooks.
3. Run `make lint` and `make test` before opening a PR — CI enforces both.
4. Keep infra changes (`infra/`) in their own PR from application code where
   possible; `terraform.yml` posts the plan output as a PR comment for review.
5. Fine-tuning changes should include updated evaluation metrics
   (`src/llm/evaluation/evaluate.py`) in the PR description.

## Commit style

Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `infra:`) are
preferred; CI does not enforce this but it keeps changelogs readable.

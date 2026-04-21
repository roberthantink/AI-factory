# Shared Tools

Reusable utilities that agents can invoke during task execution.

Examples of tools you might add here:

- `lint.sh` — Run linters across any project workspace
- `test_runner.py` — Generic test runner wrapper
- `format.sh` — Code formatter wrapper
- `deploy.py` — Deployment scripts
- `db_migrate.py` — Database migration runner

Tools should be language-agnostic wrappers where possible, delegating
to the project's own toolchain (npm, pip, cargo, etc.) based on the
project's `tech_stack` config in project.yaml.

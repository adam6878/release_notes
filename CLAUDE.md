# CLAUDE.md

Release Notes: a FastAPI service with a static UI and PostgreSQL, deployed to kind with Helm.
README.md explains how to run it; DECISIONS.md explains why it is built this way.

## Commands
```
pip install -r requirements-dev.txt
pytest                      # temp SQLite; set TEST_DATABASE_URL for PostgreSQL
ruff check .
mypy                        # strict, settings in mypy.ini
helm lint deploy -f deploy/values-dev.yaml --set image.tag=ci
make up | rollout TAG=vN | rollback | down | clean
```

## Rules
- Keep it simple. No new files, dependencies or abstractions unless the task needs them.
  The owner must be able to explain every line.
- Every function parameter and return value is annotated (mypy strict). Use builtin generics
  (`dict[str, str]`) and `http.HTTPStatus`, not numeric status codes.
- Python 3.11 is pinned in the Dockerfile, `.github/workflows/ci.yml` and `mypy.ini`.
  Change all of them together.
- Tests read `TEST_DATABASE_URL`, never `DATABASE_URL`: the fixture deletes all rows.
- The Makefile runs in `cmd.exe` (`SHELL := cmd.exe`) so it works from a Windows terminal.
  Recipes use cmd syntax (`>nul 2>&1`, `cmd /c start /b`). No comments inside recipes:
  cmd receives them as commands. Put comments above the target.
- The chart requires `image.tag`; never use `latest`.
- CD is GitOps: workflows never get cluster credentials or run kubectl/helm against a cluster.
- When behaviour changes, update README.md and DECISIONS.md in the same change.

## Workflow
- Do not run lint, tests or the cluster after every edit. Verify when asked or before a commit.
- Every commit runs ruff, mypy, pytest and helm lint as pre-commit hooks
  (`.pre-commit-config.yaml`).
- The owner creates branches and commits (`feature/*` into `develop` into `main`).
  Finish with a one-line commit message.

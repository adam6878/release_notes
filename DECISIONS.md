# Decisions

## AI assistance
I used Claude Code (an AI assistant) while building this. I reviewed every change and can
explain every line.

## Assumptions
- "Internal tool" means no authentication; it would sit behind the company SSO or VPN.
- A release is identified by its version string, which must be unique.
- The local cluster is the target for Parts 2 and 4; the pipeline does not reach a real cluster.

## Service
- **One file per job.** `main.py` only builds the app. Routes live in `app/routers/`, API
  shapes in `schemas.py`, the table in `db.py`, settings in `config.py`, and logging,
  metrics and the request middleware in `logger.py`, `metrics.py` and `middleware.py`.
  Packages re-export their public names through `__init__.py` with `__all__`.
- **No `/v1` prefix.** The only consumer is the bundled UI, which ships in the same image.
  I would add `/api/v1` when a second consumer exists.
- **Separate request and response models** (`ReleaseIn`, `ReleaseOut`), so input is
  validated and the response shape is fixed and documented.
- **Duplicate versions return 409, enforced by a unique constraint** in the database, so the
  rule holds with several replicas writing at once.
- **SQLAlchemy Core, not the ORM.** There is one table and no relationships, so mapped
  classes and a `Session` would add a second definition of the data and a lifecycle to manage
  for nothing. I would move to the ORM when a related table appears.
- **PostgreSQL in the cluster, SQLite locally**, chosen by `DATABASE_URL`.
- **Tables are created on startup** (`create_all`). This is a shortcut: replicas starting
  together can race. In production I would run Alembic migrations as a Job before the rollout.
- **Config from environment variables** (pydantic-settings). `DATABASE_URL` has no default,
  so a missing Secret stops startup instead of silently writing to a throwaway SQLite file.
- **Minimal UI:** one static HTML file, no build step, served by the API container. It
  renders with `textContent`, so notes cannot inject script. Splitting it into its own image
  only pays off with a separate frontend team or release cadence.

## Health, metrics and logs
- **Liveness does not touch the database; readiness does.** A database outage then takes pods
  out of rotation instead of restarting all of them at once.
- **Prometheus pull model.** The app serves `/metrics`; pods carry the standard
  `prometheus.io/scrape` annotations. I did not deploy Prometheus: in a real cluster the
  platform runs it (with the Operator I would ship a `ServiceMonitor`).
- **Bounded label values.** The `path` label is the real path only for matched API routes;
  everything else is `other`, so random URLs cannot create unlimited time series. This rule
  must switch to route templates once a route has path parameters.
- **JSON logs to stdout**, one line per request; probes and scrapes are counted, not logged.

## Container and Kubernetes
- **Image:** multi-stage build on `python:3.11-slim`, numeric non-root user. The build stage
  keeps the pip cache and build leftovers out of the final image. `.dockerignore` keeps `.env`
  and git history out.
- **`ENTRYPOINT ["python", "run.py"]`.** `run.py` calls `uvicorn.run` with host, port and
  shutdown timeout from the same pydantic settings as the rest of the app, so every setting
  is an environment variable and the Dockerfile holds no server flags. Exec form makes python
  PID 1, so SIGTERM reaches uvicorn directly (shell form would put `/bin/sh` in between and
  break graceful shutdown). `ENTRYPOINT` cannot be replaced by `docker run` arguments or a
  pod's `args`. The cost: a debug shell needs `docker run --entrypoint sh`.
- **One uvicorn process per pod, no gunicorn.** Kubernetes restarts containers and the HPA
  adds pods, so a process manager inside the pod would duplicate that. It would also need
  Prometheus multiprocess mode and would multiply database connections. Routes run in
  FastAPI's threadpool, so one process already serves concurrent requests.
- **Helm over plain manifests or Kustomize:** I have used it in production, and it gives one
  set of templates with small per-environment values files, `helm lint` for CI, and
  `helm rollback` as the one-command way back.
- **Secrets:** the chart only references a Secret by name. `make up` generates the database
  password once with Python's `secrets` and stores it only in the cluster. Non-secret settings
  (`LOG_LEVEL`) go in a ConfigMap; a checksum annotation rolls the pods when it changes.
  The Secret holds only the password; host, user and database name are plain chart values,
  and the Deployment assembles `DATABASE_URL` from them.
- **Pods:** liveness and readiness probes, CPU and memory requests and limits, read-only root
  filesystem, all capabilities dropped, `RollingUpdate` with `maxUnavailable: 0`. An init
  container waits for PostgreSQL so the app does not crash-loop during a cold start.
- **Scaling:** fixed 2 replicas in dev; an HPA on CPU (2 to 4 pods) in prod. metrics-server
  is installed by `make up`.
- **PostgreSQL** runs as a single-replica StatefulSet with a PersistentVolume, written in the
  chart rather than pulled in as a third-party subchart.
- **kind** as the local cluster: it runs in Docker and loads local images without a registry.
  I first used minikube; on this machine both failed because Docker ran cgroup v1, which
  current Kubernetes refuses. The fix was switching WSL2 to cgroup v2 (see README).
  `kind.yaml` also raises kubeadm's timeouts, because the first control-plane start on a
  2-CPU VM took longer than kubeadm's 1-minute default.

## Tests
- **Strict typing with mypy** (`mypy.ini`, `strict = True`, pydantic plugin): every parameter
  and return value is annotated, and CI fails on a missing or wrong annotation. mypy over
  pyright: it is the standard checker, needs no Node.js, and understands pydantic models.
- **Tests drive the real app over HTTP** (FastAPI `TestClient`), including middleware, routing,
  validation and a real SQL database, rather than unit-testing functions in isolation.
- **The same suite runs twice in CI:** on SQLite (fast, no server) and on PostgreSQL 16 as a
  service container, so the production driver, the unique constraint and timestamps are covered.
  The test database comes from `TEST_DATABASE_URL`, never `DATABASE_URL`, because the fixture
  deletes all rows and must not touch a real database from someone's shell.
- **No separate tests against the deployed cluster:** the Part 4 rollout script sends real
  traffic to the running stack and is that end-to-end check.

## CI/CD (GitHub Actions, `ci.yml` and `cd.yml`)
- **Every push and pull request:** `ruff` lint; tests on SQLite and PostgreSQL; `helm lint` plus
  `helm template | kubeconform -strict` for both environments; image build tagged with the commit
  SHA (not pushed). The image job runs only after the other three pass.
- **Two workflows, so checks and publishing stay apart.** `cd.yml` runs when `ci` completes
  successfully for a push to `main`: it pushes the image to GHCR, then commits the new repository
  and tag into `deploy/values-prod.yaml`. It builds the exact commit CI tested, and the image
  is rebuilt from the build cache, so the second build takes seconds. It also checks that the
  triggering event was a push, so a pull request can never publish.
- **GitOps over a direct deploy step.** CD never holds cluster credentials and never talks to a
  cluster. A GitOps agent in the cluster (Argo CD or Flux) watches `main` and applies what it
  says, so git is the record of what runs in prod, drift is corrected, and a rollback is a
  `git revert` of the bump commit. The cost is a bot commit per release and a short delay until
  the agent syncs. The agent itself is not part of this repo; the local cluster is deployed with
  `make up`, which overrides the image with the locally built one. I did not install Argo CD
  here: it needs about 7 more pods on a 2-CPU kind node and would undo the locally built image.
  This `Application` shows what would consume the bump commit:

  ```yaml
  apiVersion: argoproj.io/v1alpha1
  kind: Application
  metadata: {name: release-notes-prod, namespace: argocd}
  spec:
    project: default
    source:
      repoURL: https://github.com/adam6878/release_notes
      targetRevision: main
      path: deploy
      helm: {valueFiles: [values-prod.yaml]}
    destination: {server: https://kubernetes.default.svc, namespace: prod}
    syncPolicy: {automated: {prune: true, selfHeal: true}}
  ```
- **Known limits:** the bump commit needs `main` to accept pushes from `github-actions[bot]`
  (with branch protection, a bot pull request instead). Actions are pinned to major versions;
  in production I would pin them to commit SHAs.

## Zero-downtime rollout
- **Gradual rollout:** `RollingUpdate` with `maxSurge: 1` and `maxUnavailable: 0`, so an old
  pod is removed only after its replacement passes readiness; `minReadySeconds: 5` makes the
  new pod prove itself before the next step.
- **Graceful shutdown:** when a pod is deleted, removing it from the Service and sending it
  SIGTERM happen in parallel, and the routing change takes a moment to reach every node. A
  `preStop` sleep of 5 s keeps the pod serving through that window; then uvicorn gets SIGTERM
  and finishes in-flight requests (`--timeout-graceful-shutdown 20`), inside a 30 s
  `terminationGracePeriodSeconds`.
- **Visible change:** the image tag is passed in as `APP_VERSION`, served at `/api/version`
  and shown in the UI footer.
- **Measured:** `scripts/load_test.py` sends a request every ~100 ms during the change and
  counts every non-200 or failed connection. Result on kind: rollout v1 to v4, 768 requests,
  0 failed; rollback v4 to v1, 405 requests, 0 failed.
- **Way back:** `make rollback` (`helm rollback --wait`, measured the same way). With GitOps in
  production, the way back is a `git revert` of the image bump.

### What would still break this in a real cluster
- **Database schema changes.** Old and new pods run at the same time, so a migration that
  drops or renames a column breaks the old pods. Use expand/contract migrations, run as a Job
  before the rollout. Today's `create_all` on startup cannot do that.
- **The single PostgreSQL replica.** Any change to its spec restarts it, which is downtime for
  every pod. Use a managed or replicated database outside the app release; also, `helm rollback`
  reverts the database spec together with the app.
- **Load balancers outside the cluster.** A cloud load balancer or Ingress controller keeps its
  own connection pool; its deregistration delay or connection draining must match the
  `preStop` sleep, or the sleep must grow.
- **Voluntary disruptions.** A node drain or cluster autoscaler can evict both replicas at once.
  A PodDisruptionBudget (`minAvailable: 1`) prevents it.
- **No room for the surge pod.** With a full node or a tight namespace quota, the extra pod
  stays Pending and the rollout stalls. Capacity and quotas must leave room for `maxSurge`.
- **Readiness depends on the database.** A short database blip removes every pod from rotation
  at once: correct for errors, but a total outage for that time.
- **Long-lived connections and slow requests** longer than the drain timeout are cut.
- **Version skew.** A browser holding the old UI can call a new API. API changes must stay
  additive across one release.

## Cut for time
PodDisruptionBudget, NetworkPolicy, Ingress, database backups, Alembic migrations, a secret
manager, authentication, image signing and vulnerability scanning.

## For a real rollout across many clusters
- **Infrastructure with Terraform:** one cluster per environment and region, a managed
  PostgreSQL in place of the in-cluster StatefulSet, networking and IAM.
- **GitOps (Argo CD or Flux)** instead of `make up`: CI publishes the image and bumps the tag
  in a config repository; each cluster pulls its own desired state, and an
  ApplicationSet-style template avoids copying configuration per cluster.
- **Secrets from a secret manager** (External Secrets Operator or Sealed Secrets), not
  generated at deploy time.
- **Progressive delivery:** roll out to one cluster or a canary share first, gate on error rate
  and latency from Prometheus, then widen.
- **Schema changes** as expand/contract migrations run before the rollout, so old and new pods
  can share the database.
- **Images from a registry**, signed, scanned in CI, and referenced by digest.

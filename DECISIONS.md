# Decisions

## AI assistance
I used Claude Code (an AI assistant) while building this. `CLAUDE.md` holds the project rules the assistant follows.

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
  - **Why PostgreSQL in the cluster:** the data is one relational table with a unique constraint,
    and several replicas write to it at once. That needs a database server with real concurrent
    writes and constraints enforced in one shared place. SQLite is a file inside one pod's disk:
    each replica would get its own copy of the data, and it allows one writer at a time. PostgreSQL
    is also the common default on Kubernetes, with an official image, operators, and a managed
    service on every cloud, so the later move to a managed database changes only `DATABASE_URL`.
  - **Why SQLite locally and in the fast test run:** no server to install or start, so
    `python run.py` and `pytest` work on a clean machine, and each test run gets a throwaway file.
    SQLite is not the production engine, so CI runs the same suite a second time on PostgreSQL 16.
  - **Why not the others:** MySQL or MariaDB would work as well, but nothing here needs them and
    PostgreSQL has the wider operator and managed-service support. A document database (MongoDB)
    has no benefit for one fixed table with a fixed shape, and SQLAlchemy does not support it, so
    the data layer would be rewritten. Redis is a cache, not a durable primary store. SQLAlchemy
    Core keeps the queries portable across relational engines, so that choice can change without
    rewriting the app.
- **Tables are created on startup** (`create_all`). This is a shortcut: replicas starting
  together can race. Seen once on the first prod install: both pods created the tables on the
  empty database at the same time, one failed and Kubernetes restarted it, and it came up on
  the second try. In production I would run Alembic migrations as a Job before the rollout.
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
- **Counters live in memory, and a restart is not a problem.** A pod restart or rollout resets
  its counters to zero. Prometheus stores the history, and when a counter value drops it treats
  that as a reset, so `rate()` and `increase()` stay correct. The app needs no persistence.
- **Bounded label values.** The `path` label is the real path only for matched API routes;
  everything else is `other`, so random URLs cannot create unlimited time series. This rule
  must switch to route templates once a route has path parameters.
- **Failed requests log the server's message.** The request log gets an `error` field: the
  `detail` of an `HTTPException` (409, 404) or `repr(exc)` of a crash (500). FastAPI turns an
  `HTTPException` into a response before the middleware runs, so `main.py` has a handler that
  saves the message, then returns the normal response. The level follows the status: 5xx is
  ERROR, 4xx is WARNING, the rest INFO, because a caller's mistake is not a server fault.
  Validation errors (422) are logged with the status only. A handler for `RequestValidationError`
  would add the field and reason, but the browser form checks the version format before sending,
  so UI users rarely reach a 422 and the handler would be unused code. Add it when clients that
  call the API directly (a script, an SDK) appear, where the log is the only place to see why a
  request was rejected. Leave the input value out of that message, so a long `notes` text is
  never copied into the logs.
- **JSON logs to stdout**, one line per request; probes and scrapes are counted, not logged.
  Colour is added only when stdout is a terminal (`isatty`), because ANSI codes would break a
  log collector's parser. `time` is local `dd/mm/yyyy hh:mm:ss` for readability; it has no
  timezone, which is fine while pods run in UTC and a collector adds its own receive time.

## Container and Kubernetes
- **Image:** multi-stage build on `python:3.15-slim`, numeric non-root user. The build stage
  keeps the pip cache and build leftovers out of the final image. `.dockerignore` keeps `.env`
  and git history out. pip is removed from the final image: the app never runs it, and its
  bundled urllib3, msgpack and setuptools were the only fixable HIGH CVEs. The rest are Debian
  packages with no fix released yet; the floating `3.15-slim` tag picks fixes up on the next build.
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
  is installed by `make up`; checked with `make up ENV=prod`, where the HPA reads `cpu: 1%/70%`.
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
- **pre-commit hooks** run ruff, mypy, pytest and helm lint on every commit. They use the tools
  installed from `requirements-dev.txt` (`language: system`), so versions are pinned in one
  place. CI still runs the same checks, because hooks run only where installed and
  `--no-verify` skips them.
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
- **Exact pins, updated by Dependabot** (`.github/dependabot.yml`). `==` pins make the laptop,
  CI and the image install the same code. Every week Dependabot opens PRs against `develop` for
  pip packages (one grouped PR) and GitHub Actions, and CI tests each one before merge. The
  Python base image is bumped by hand, because the Dockerfile, `ci.yml` and `mypy.ini` change
  together. Only top-level packages are pinned; their dependencies still float.
- **Known limits:** the bump commit needs `main` to accept pushes from `github-actions[bot]`
  (with branch protection, a bot pull request instead). Actions are pinned to major versions;
  in production I would pin them to commit SHAs.

## Zero-downtime rollout
- **Gradual rollout, so capacity never drops.** `RollingUpdate` with `maxSurge: 1` and
  `maxUnavailable: 0`: with 2 replicas the rollout starts a third pod, and an old pod is removed
  only after its replacement has passed readiness and stayed Ready for `minReadySeconds: 5`. The
  number of Ready pods never falls below 2. The values are written out because the defaults (25%)
  round to the same numbers at 2 replicas, but allow one unavailable pod at the 4 replicas the
  HPA reaches in prod.
- **Graceful shutdown, so no request is cut off.** When a pod is deleted, removing it from the
  Service and sending it SIGTERM happen in parallel, and the routing change takes a moment to
  reach every node. A `preStop` sleep of 5 s keeps the pod serving through that window. Then
  uvicorn gets SIGTERM, stops accepting connections, and finishes in-flight requests for at most
  `GRACEFUL_SHUTDOWN_SECONDS` (20 s). Both share one `terminationGracePeriodSeconds` of 30 s
  (5 + 20 = 25, with 5 s to spare), so uvicorn gives up before Kubernetes would kill it. Measured
  on kind: with the `preStop` hook removed, a restart under load failed 2 of 1196 requests; with
  it, every run failed 0.
- **Measured, with a way back.** `scripts/load_test.py` sends a request every ~100 ms during the
  change and counts every non-200 or failed connection. It goes through the Service's fixed
  NodePort, mapped to a host port by `kind.yaml`; a `kubectl port-forward` tunnel is tied to one
  pod and breaks when that pod is replaced, so it would measure the tunnel and not the app.
  Result on kind: rollout 8fd5737 to v3, 1195 requests, 0 failed; rollback v3 to 8fd5737, 1196
  requests, 0 failed. The image tag is passed in as `APP_VERSION`, served at `/api/version` and
  shown in the UI footer, so the switch is visible. `make rollback` (`helm rollback --wait`) goes
  back to the previous Helm revision; with GitOps in production the way back is a `git revert`
  of the image bump.

### What would still break this in a real cluster
- **Old and new versions run side by side.** During a rollout, old and new pods serve at the
  same time, so both must work with the same database and the same clients. A migration that
  drops or renames a column breaks the old pods, and a browser holding the old UI can call the
  new API. Today `create_all` on startup only creates missing tables and cannot alter one, and
  replicas starting together race (seen once on the first prod install). What I would do:
  - Run Alembic migrations as a Kubernetes Job before the new pods start (a Helm `pre-upgrade`
    hook, or a pipeline step). One process changes the schema, and a failed migration stops the
    rollout while the old pods keep serving.
  - Write migrations as expand/contract: release 1 adds the new column and the code writes both,
    release 2 reads the new one, a later release drops the old one. API changes stay additive
    for one release for the same reason.
- **The database is the single point of failure.** One PostgreSQL pod serves every app pod, on
  one volume with no backups. It is down on a crash, a node drain, or any change to its spec, and
  the whole service goes with it: readiness takes every app pod out of rotation until it is
  back, which is correct for errors but a full outage for that time. It is also tied to the app
  release: `helm rollback` reverts the database spec together with the app, and a major version
  bump (`postgres:16` to `17`) makes PostgreSQL refuse to start on the old data directory. The
  app already copes with a short blip, since `pool_pre_ping` drops dead connections. What I would
  do, in this order:
  - Backups with point-in-time recovery first. They do not prevent an outage, but turn data
    loss into a restore.
  - A managed database (RDS, Cloud SQL) with a standby in another zone, automatic failover and
    backups, or an operator (CloudNativePG) if it must stay in the cluster. Either one takes the
    database out of the app release, so `helm rollback` stops touching it.
  - Upgrades and moves to another server: start the new server beside the old one and copy the
    data with logical replication (`pg_dump` and restore is enough for a database this small).
    Then, in a short window, stop writes, let the copy catch up, change `DATABASE_URL` in the
    Secret and roll the app pods. The old server stays untouched until the new one has been
    healthy for a while: it is the way back. Never upgrade the database in the same release as
    an app change.
  - The limit does not go away: one primary takes the writes, so a failover still takes seconds
    to a minute and open connections drop. The app must retry or fail cleanly meanwhile.
- **Pods lost outside the rollout.** A node drain or the cluster autoscaler can evict both
  replicas at once, and a full node or a tight namespace quota leaves the surge pod Pending, so
  the rollout stalls. What I would do: a PodDisruptionBudget with `minAvailable: 1`, so drains
  evict one pod at a time; `topologySpreadConstraints` so the replicas land on different nodes
  and zones; and requests, node capacity and quotas that leave room for `maxSurge`.
- **Traffic in front of the pods.** A cloud load balancer or Ingress controller keeps its own
  connection pool and takes time to notice that a pod is going away. If its deregistration delay
  is longer than the `preStop` sleep, it still sends requests to a pod that has stopped
  listening. Requests and connections longer than the drain timeout (WebSockets, large downloads)
  are cut when it ends. What I would do: set the load balancer's connection draining at or below
  the `preStop` sleep, or raise the sleep if it cannot be lowered; for long connections, raise
  `GRACEFUL_SHUTDOWN_SECONDS` and `terminationGracePeriodSeconds` together, or make clients
  reconnect. This app's requests are short, so it needs neither today.

## Cut for time
PodDisruptionBudget, NetworkPolicy, Ingress, database backups, Alembic migrations, a secret
manager, authentication, image signing and vulnerability scanning.

## For a real rollout across many clusters
- **Infrastructure with Terraform:** one cluster per environment and region, a managed
  PostgreSQL in place of the in-cluster StatefulSet, networking and IAM.
- **Argo CD** instead of `make up`: CI publishes the image and bumps the tag
  in a config repository; each cluster pulls its own desired state, and an
  ApplicationSet-style template avoids copying configuration per cluster.
- **Secrets from a secret manager** (External Secrets Operator or Sealed Secrets), not
  generated at deploy time.
- **Progressive delivery:** roll out to one cluster or a canary share first, gate on error rate
  and latency from Prometheus, then widen.
- **Schema changes** as expand/contract migrations run before the rollout, so old and new pods
  can share the database.
- **Pulling images in a real cluster.** Images already go to GHCR from CD, but `make up` loads
  them into kind and never pulls. A real cluster pulls from GHCR, and if the images are private
  each namespace needs a pull credential (`imagePullSecrets`).
- **Central logs with Logstash and Elasticsearch.** Today each pod's JSON goes to stdout and is
  read with `kubectl logs`. With many pods and clusters that stops working. A shipper on each node
  (Filebeat) would read the container logs and send them through Logstash, which parses and enriches
  them, into Elasticsearch, searched in Kibana. The JSON format is what makes this cheap: no regex
  parsing is needed. The colour output is already off in a pod, so the collector never sees escape
  codes.
- **A trace id on every request**, once the application grows past one deployment. The edge
  generates an id (or accepts an incoming `traceparent` / `X-Request-ID` header), the request
  middleware adds it to every log line as a `trace_id` field and to the response header, and each
  service passes it on to the services it calls. One search in Elasticsearch then returns every
  line a single request produced across all services. It is not built now: with one service and no
  downstream calls, the id would only repeat what the request line already shows.

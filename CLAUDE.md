# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Grafana dashboards configuration repository for NX infrastructure and application monitoring. It contains JSON-based Grafana dashboards, datasources, alert rules, and folder definitions that are synchronized to Grafana instances. Grafana itself runs in the `observability` namespace; the connectors and applications it monitors run in separate application namespaces (e.g., `default`).

The repo is in the middle of a V1 → V2 restructure. New work for application/connector dashboards goes in V2. V1 stays untouched until V2 reaches parity per connector, then V1 files are deleted in a cleanup PR.

## Top-Level Layout

```
dashboards/
  *.json                                  # V1 (Original) — flat layout
  applications/V2/                        # V2 — nested by connector
    applications-overview.json
    connectors/<name>/<name>-{overview,pipeline,runtime}.json
folders/
  *.json                                  # V1 folders (flat)
  connectors/                             # V2 connector subfolders
alerts/
  *.json                                  # alert rule definitions
datasources/
  *.json                                  # legacy reference datasources (not actively synced)
.github/workflows/release.yml             # CalVer tag + GitHub Release on push to main
```

## How dashboards actually reach Grafana

**The GitHub Release workflow is NOT in the deployment path.** It tags + bundles JSONs for audit/versioning only.

The real sync mechanism is configured in `nx-application-helm/charts/observability` and uses a custom CronJob image (`ghcr.io/nvision-x/grafana-dashboards-sync`, source: `grafana-dashboards-sync` repo). The flow:

1. CronJob runs every minute in the `observability` namespace.
2. The container clones `https://github.com/Nvision-x/Observability-Dashboards.git` at branch `main` (commit pin optional via `COMMIT` env var).
3. **Phase 1 (cleanup):** deletes every existing ConfigMap with prefix `observability-grafana-dashboard-`.
4. **Phase 2 (process):** runs `find $TEMP_DIR/dashboards -name "*.json" -type f` (no `-maxdepth` → recurses subdirectories), validates each with `jq`, and creates one ConfigMap per file. Names derive from the path: `dashboards/applications/V2/connectors/snowflake/snowflake-overview.json` → `observability-grafana-dashboard-dashboards-applications-v2-connectors-snowflake-snowflake-overview`.
5. ConfigMaps are labeled `grafana_dashboard=1`, `app.kubernetes.io/managed-by=grafana-dashboards-sync`, `app.kubernetes.io/component=grafana-dashboard`.
6. Grafana's sidecar (kube-prometheus-stack, configured with `sidecar.dashboards.label: app.kubernetes.io/component`) picks up labeled ConfigMaps and loads the JSONs into Grafana.

### Implications for editing this repo

- ✅ **Subdirectory layouts work.** V2's nested paths under `dashboards/applications/V2/connectors/<name>/` are processed normally because the sync uses recursive `find`.
- ❌ **Only `dashboards/` is synced.** The script does not look at `folders/`, `alerts/`, or `datasources/`. JSON files placed there are inert with respect to this sync.
- ❌ **No folder mechanism.** Because `folders/` isn't synced and the sidecar isn't configured with `folderAnnotation`, dashboard organization in Grafana is NOT driven by this repo. Folders must exist in Grafana first (created manually or by another process); only then will the `folderUid` inside a dashboard JSON be honored at load time.
- ❌ **No alert sync.** `alerts/*.json` is not deployed by anything in this stack. Alerts must be configured separately.
- ⚠️ **Cleanup-then-recreate** runs every minute. A broken JSON merged to `main` will cause one ConfigMap creation to fail but won't roll back others. A removed file vanishes from Grafana within a minute of merge.
- ⚠️ **The `"git-sync"` tag is decorative.** It's a labeling convention, not a functional sync trigger — the sync script doesn't read it. Keep it for consistency, but don't rely on it.
- ⚠️ **The `release.yml` workflow is unused for deployment** — the cronjob clones `main` directly, not Release artifacts. The workflow is only useful as a versioning record.

---

# V1 (Original) — Legacy / Maintenance Mode

V1 is the existing flat dashboard set. **Do not add new dashboards here.** Only modify V1 files for bug fixes or until the V2 equivalent has been shipped and verified.

## V1 Layout

- `dashboards/*.json` — all dashboards in one flat directory
  - Application dashboards: `nx-applications-dashboard.json`, `nx-applications-monitoring.json`, `apps-connector.json`, `apps-enricher.json`, `apps-archiver.json`, `apps-archiverv2.json`, etc.
  - Infrastructure dashboards: `nx-infrastructure-overview.json`, `prometheus2.json`
  - Messaging dashboards: `nats-dashboard.json`, `nats-explorer.json`, `pulsar-monitor.json`, `pulsar-topic-official.json`, `pulsar-explorer.json`
- `folders/applications-folder.json`, `folders/infrastructure-folder.json`, `folders/app-metrics-folder.json` — flat parent folders, all with `parentUid: ""`
- `datasources/prometheus-nx.json`, `datasources/loki-nx.json` — legacy reference (not actively synced)
- `alerts/nx-applications-alerts.json`, `alerts/nx-infrastructure-alerts.json`

## V1 Conventions

- **Datasource references vary across files.** Some V1 dashboards use `"${DS_PROMETHEUS}"` (e.g., `apps-archiver.json`); others use the literal `"Prometheus"` (e.g., `apps-connector.json`). Match whatever the surrounding file uses when editing.
- **Hard-coded selectors.** V1 panels frequently hard-code `namespace='default'`, `job='default/applications-connector'`, `container='connector'`. This is one of the things V2 fixes — do not propagate this pattern.
- **Tags include `"git-sync"`** plus categorization tags (e.g., `archiver`, `applications`, `pulsar`).
- **Schema version 39** with `refresh` typically `"15s"` or `"30s"`.

## Modifying V1 Dashboards

1. Read the entire dashboard JSON file.
2. Locate the specific panel or configuration to modify.
3. Preserve the `"git-sync"` tag, the dashboard UID, and the existing datasource reference style for that file.
4. Keep edits minimal — V1 is on its way out, and structural changes belong in V2.

## V1 Alert Rules

Alert rules in `alerts/` follow this structure:
- `title`, `folder`, `interval` (e.g., `"30s"`), and `rules[]` of alert definitions.
- Each rule has `uid`, `condition`, `data[]` (Prometheus queries + threshold expressions), `for`, `annotations`, `labels`.

---

# V2 — Current Standard

V2 is the new structure. All new application/connector dashboards go here.

## V2 Layout

```
dashboards/applications/V2/
  applications-overview.json              # cross-connector roll-up (golden signals per connector)
  connectors/
    <connector>/
      <connector>-overview.json           # RED golden signals + drill-down links
      <connector>-pipeline.json           # connector-specific business metrics
      <connector>-runtime.json            # process / container / Go runtime / FDs
  services/
    <service>/
      <service>-overview.json             # RED golden signals + domain metrics
      <service>-runtime.json              # process / container / Go runtime / FDs
folders/
  applications-v2-folder.json             # parentUid: applications-folder
  connectors/
    <connector>-folder.json               # parentUid: applications-v2-folder
  services/
    <service>-folder.json                 # parentUid: applications-v2-folder
```

Snowflake is the V2 reference implementation for connectors. Use it as the template for new connectors.

**Connectors vs services.** Connectors get three dashboards (`overview` / `pipeline` / `runtime`); their business metrics are substantial enough to warrant a dedicated pipeline view. Platform services (registration, request) get two — `overview` carries both the RED signals and the domain metrics, because there aren't enough of the latter to fill a third dashboard. Registration and request service are the reference implementations for services.

## V2 Conventions

### Naming
- Dashboard UIDs: `apps-v2-<name>-<view>` (e.g., `apps-v2-snowflake-pipeline`, `apps-v2-request-service-overview`).
- Folder UIDs: `apps-v2-<name>-folder`. For services the name includes the `-service` suffix (`apps-v2-request-service-folder`).
- File path encodes the structure: `dashboards/applications/V2/{connectors,services}/<name>/<name>-<view>.json`.

### Tags
Every V2 dashboard MUST include in `tags`:
- `git-sync` — required for sync.
- `apps-v2` — identifies V2 set.
- `connector:<name>` for connectors (e.g., `connector:snowflake`), or `service:<name>` for services (e.g., `service:request-service`).
- One view tag: `overview` | `pipeline` | `runtime`.

### Folder placement
- Set `folderUid` at the top level of every V2 dashboard JSON.
- Folder JSONs use `parentUid` to nest. The parent V2 folder lives under the V1 `applications-folder` to avoid colliding with existing navigation.

### Template variables (V2 standard)
Every V2 dashboard declares these in `templating.list`, in this order:
- `$datasource` — type `datasource`, query `prometheus`. Default value should match the actual Prometheus datasource UID used in your Grafana (CLAUDE.md previously claimed `prometheus-nx` but V1 dashboards use `${DS_PROMETHEUS}` or `Prometheus` — confirm against your real Grafana before relying on the default).
- `$namespace` — `label_values(process_start_time_seconds{job=~".*<name>.*"}, namespace)`.
- `$component` — **connectors only.** Custom variable with `All` / `Scanner` / `Content` options for connectors that have a content-fetch pod; single-value, used as a job-regex selector. Its option values are full job regexes, not bare names — see the job-label table below. Services have a single pod type and omit this variable.
- `$pod` — `label_values(process_start_time_seconds{job=~"$component", namespace="$namespace"}, pod)` for connectors, or `job=~".*<name>.*"` for services. Multi-value with `includeAll`.

Use `process_start_time_seconds` rather than `up` to drive `$namespace` / `$pod`. The process collector always exports it — including when `METRICS_ENABLED=false`, where only the Go and process collectors are served — so the variables still resolve on a pod whose app instruments are switched off.

Pipeline dashboards add view-specific variables when needed (e.g., `$query_type` for Snowflake/PostgreSQL, `$datasource_id` for CIFS).

### Job-label conventions

**The `job` label is not the pod's `app.kubernetes.io/name`.** No PodMonitor in `nx-application-helm/charts/applications/templates` sets `spec.jobLabel` (checked: all 28), and none set `podTargetLabels` or custom `relabelings`. Prometheus Operator therefore uses its default and sets:

```
job = "<podmonitor-namespace>/<podmonitor-name>"
```

PodMonitor names are `{{ include "applications.fullname" . }}-<suffix>`, i.e. `<release>-applications-<suffix>`. So for release `nx` in namespace `default`, the Snowflake scanner job is:

```
default/nx-applications-snowflake-connector-be-go
```

The pod *does* carry `app.kubernetes.io/name: snowflake-connector-be-go` — that label simply never reaches `job` without `jobLabel` instructing the operator to copy it.

**Always lead a job selector with `.*`.** Prometheus label matchers are fully anchored (`=~"foo"` means `^foo$`), so a selector must absorb the `<namespace>/<release>-applications-` prefix:

| Selector | Matches |
|---|---|
| `job=~".*snowflake-connector-be-go.*"` | scanner + content — use for aggregate panels |
| `job=~".*snowflake-connector-be-go"` | scanner only; the implicit trailing anchor excludes `-content` |
| `job=~".*snowflake-connector-be-go-content"` | content only |
| `job=~"snowflake-connector-be-go.*"` | ❌ nothing — missing leading `.*` |

That last row is the trap. It fails silently and confusingly: `$namespace` resolves to an empty list, so every panel renders "No data" as though the component weren't emitting metrics at all.

Match on the **PodMonitor name suffix**, not the pod label. Current suffixes:

| Component | PodMonitor name suffix(es) |
|---|---|
| Snowflake | `-snowflake-connector-be-go`, `-snowflake-connector-be-go-content` |
| CIFS | `-cifs-connector-be-go`, `-cifs-connector-be-go-content` |
| PostgreSQL | `-postgresql-connector-be-go`, `-postgresql-connector-be-go-content` |
| Box | `-box-connector-be-go`, `-box-connector-be-go-content` |
| SharePoint | `-sharepoint-connector-be-go`, `-sharepoint-connector-be-go-content` |
| NFS | **none — no PodMonitor exists**, so NFS is not scraped at all (not even runtime metrics) |
| Registration Service | `-registration-service` (note: no `-be-go`) |
| Request Service | `-request-service` (note: no `-be-go`) |
| Knowledge Service | `-knowledge-service-be-go` |
| Knowledge Hub — standalone | `-knowledge-hub-be-go` |
| Knowledge Hub — sidecar | `-knowledge-hub-be-go-sidecar` |

Two things to note: the service suffixes drop the `-be-go` that the repo names carry, and CIFS/SharePoint do have content PodMonitors (an earlier version of this table said they didn't).

### Knowledge Hub runs twice, and the two are not interchangeable

The `knowledge-hub-be-go` image runs in two places, doing completely different work:

| Instance | Where | Container port | PodMonitor | What it does |
|---|---|---|---|---|
| standalone | its own Deployment, `applications-knowledge-hub-be-go-*` | `http` | `-knowledge-hub-be-go` | serves the Connect API behind Kong; near-idle |
| sidecar | a native sidecar (initContainer, `restartPolicy: Always`) inside `applications-knowledge-service-be-go-*`, dialled on `127.0.0.1:8080` | `ingestor` | `-knowledge-hub-be-go-sidecar` | ingests every document; all the real work |

Same image, same ConfigMap, same metric names. Only the `job` label tells them
apart, so **every Knowledge Hub panel must pin one of the two** — an aggregate
over both mixes an idle API server into the ingestion numbers.

```
job=~".*knowledge-hub-be-go"          standalone only (fully-anchored: no trailing .*)
job=~".*knowledge-hub-be-go-sidecar"  sidecar only
job=~".*knowledge-hub-be-go.*"        both — almost never what you want
```

Two consequences worth remembering:

- **The sidecar's container metrics live under knowledge-service pod names.** `container_memory_working_set_bytes` and friends carry no `job` label, so sidecar container panels select `pod=~".*knowledge-service-be-go.*", container="knowledge-hub-be-go"`. Conversely `pod=~".*knowledge-hub-be-go-.*"` is the standalone one and does not match the knowledge-service pods.
- **A pod-level memory total is misleading here.** The hub sidecar has been ~92% of the knowledge-service pod's memory, which is what made a hub memory climb read as a knowledge-service leak. Limits are per container (knowledge-service 512Mi, hub sidecar 1Gi), so always split by `container`.

Knowledge Hub also breaks the two-dashboards-per-service rule for the same
reason: it has four, a `{overview|ingest}` plus `runtime` pair per instance,
tagged `deployment:standalone` / `deployment:sidecar`. A single dashboard with a
mode variable was rejected because the two share almost no panels — the
standalone one is an API server and the sidecar one is a pipeline.

Confirm the real values against a live Prometheus before trusting any of the above:

```
curl -s 'http://<prometheus>/api/v1/label/job/values' | jq
```

V1 independently corroborates the `<namespace>/<podmonitor-name>` shape — `dashboards/apps-connector.json` hard-codes `job="default/applications-connector"`, and `apps-archiver.json` hard-codes `job="default/applications-archiver"`.

### Cross-dashboard links
A V2 dashboard's `links` array contains exactly two kinds of entry, and nothing else:

1. Its **own component's** other views — the sibling `overview` / `pipeline` / `runtime` dashboards for that same connector or service.
2. The V2 root, `apps-v2-overview`.

**Never link to another component.** A connector dashboard does not link to another connector, and a service dashboard does not link to another service — the registration and request service dashboards originally cross-linked to each other and that was removed. The root is the crossroads: navigating between components goes up to `apps-v2-overview` and back down through its per-row `Pods Up` drill-down. Direct component-to-component links don't scale — every new component would have to be added to every existing dashboard's header.

Every non-root dashboard must include the root link. Use `${var:queryparam}` to propagate `$namespace` and `$component` on the sibling links so context survives the drill; the root link takes no query params.

`applications-overview.json` is the exception: as the root it has an empty `links` array, and reaches components through the `fieldConfig.defaults.links` drill-down on each row's `Pods Up` stat.

### Metric naming
Native Prometheus connectors emit `<connector>_connector_*` (e.g., `snowflake_connector_items_sent_total`). OTel-based connectors emit different prefixes (Box: `box_*`, SharePoint: `graph_*`). Histograms use `_seconds` suffix and exponential buckets — **note that bucket ranges differ across connectors**, so latency panels are connector-specific (no shared library panel for histograms today).

Services differ from connectors here:
- **Domain metrics are per-service and not prefixed by the service name automatically.** Request service names its own instruments `request_service_*`; registration service does not, and emits a bare `connector_registrations_total`. The `Namespace` field on `pipeline-lib-go/metrics.Config` sets the OTel *meter* name (instrumentation scope), **not** a Prometheus metric prefix — the exporter is created with a plain `prometheus.New()`. Do not assume a service prefix.
- **Services on `pipeline-lib-go` also emit a shared HTTP/gRPC set** when they install it: `http_requests_total`, `http_request_duration_seconds`, `http_active_requests`, `http_request_size_bytes`, `http_response_size_bytes`, `grpc_requests_total`, `grpc_request_duration_seconds`, `grpc_active_requests`. Labels are `method` / `route` / `status` (HTTP) and `method` / `code` / `status` (gRPC). Group and filter gRPC by `code` (`"0"` is OK), never by `status` — that label is free text including the error message, so its cardinality is unbounded.
- Installing that set is opt-in per service. Registration service installs both. Request service installs the HTTP set only — it serves Connect RPC over HTTP, so its RPCs are counted as HTTP requests and there are no `grpc_*` series. Its SSE `/events` route is deliberately excluded from instrumentation (the middleware's `ResponseWriter` wrapper has no `Flush`, which would break the stream), so it never appears as a `route` and never inflates `http_active_requests`.
- ⚠️ **Bucket boundaries on the shared histograms are opt-in — check before writing a percentile panel.** `pipeline-lib-go` does not apply boundaries for you: `NewGRPCMetrics(provider, buckets)` and `NewHTTPMetrics(provider, map[HTTPHistogram][]float64{...})` take them per histogram, and passing nil keeps the OTel SDK default. That default is tuned for milliseconds (`0, 5, 10, 25 … 10000`); against a `s` unit every real request lands in `le=5` and `histogram_quantile` returns noise, and against a `By` unit anything over ~10 KB lands in `+Inf`. A percentile is only trustworthy where the service opted in — read its construction call, and prefer `rate(_sum)/rate(_count)` where it didn't.
  - Ready-made ladders: `SubsecondLatencyBuckets()` (0.005s–10s), `BodySizeBuckets()`, `LargeBodySizeBuckets()`.
  - Registration service opts in for gRPC and HTTP duration, and passes its own wider `BodySizeBuckets()` for both size histograms. All its percentiles are valid.
  - Request service opts in for HTTP duration and **response** size, and deliberately leaves **request** size on the SDK default (finer below 256 B, which suits the small Connect messages and bare probes it accepts). Don't write a request-size percentile for it.
  - Service-defined histograms carry their own boundaries independently: `request_service_connectiontest_duration_seconds` uses a 0.1s–300s ladder, because a connection test runs on a different timescale from an HTTP request.
- ⚠️ **`go_gc_duration_seconds` is a summary, not a histogram.** There is no `_bucket` series, so `histogram_quantile(…, rate(go_gc_duration_seconds_bucket[…]))` returns nothing. Use `go_gc_duration_seconds{quantile="1"}` (max pause); available quantiles are `0`, `0.25`, `0.5`, `0.75`, `1` — there is no `0.99`.

## Creating a New V2 Connector or Service Dashboard Set

1. Verify the connector emits Prometheus metrics. Check `<repo>-connector-be-go/internal/metrics/metrics.go` (or equivalent). If there are no metrics, scaffold only the `runtime` dashboard and open a follow-up to instrument the connector.
2. Read the metric names off a real scrape, not off the source. The OTel→Prometheus exporter rewrites names (appends `_total` to monotonic counters unless already suffixed, appends the unit for `s`/`By`, splits histograms into `_bucket`/`_sum`/`_count`), so names in `metrics.go` are not the names to query. Either `curl` a running pod's `/metrics`, or write a throwaway `main.go` in the connector repo that inits the instruments, records one point on each, and serves the Prometheus handler.
3. Find the connector's PodMonitor in `nx-application-helm/charts/applications/templates/<connector>-podmonitor.yaml` and take its **name suffix** — that, not `selectorLabels`, determines the `job` label. See "Job-label conventions" above. If no PodMonitor exists, the connector isn't scraped and a dashboard is premature.
4. Copy the Snowflake folder under `dashboards/applications/V2/connectors/snowflake/` to `<connector>/`, rename files, and update:
   - `uid` (per dashboard)
   - `folderUid`
   - `tags` (`connector:<name>`)
   - All `<connector>_connector_*` metric names
   - `links` URLs to point to the new `apps-v2-<connector>-<view>` UIDs
   - Every job selector and `templating.list` `query` string — replace `.*snowflake-connector-be-go` with `.*<connector>-be-go`, **keeping the leading `.*`**
5. Create `folders/connectors/<connector>-folder.json` with `parentUid: applications-v2-folder`.
6. Validate JSON parses (`python3 -c "import json; json.load(open('path.json'))"`).
7. Open in Grafana — confirm template variables resolve, drill-down links carry the namespace, and at least one panel returns data. An all-blank dashboard usually means a front-anchored job selector (step 3), not a missing metric.

8. Add a row for the new component to `dashboards/applications/V2/applications-overview.json` — the V2 roll-up. The established shape is four `stat` panels across: `Pods Up` (with a `fieldConfig.defaults.links` drill-down to the component's own overview, propagating `${namespace:queryparam}`), a throughput stat, a latency stat, and an error-rate stat. Only use a `histogram_quantile` latency stat if the component's histogram has explicit boundaries — see the bucket note above.

**Which overview file.** V2 components belong in `dashboards/applications/V2/applications-overview.json` and **only** there. Never add them to the V1 roll-ups — `dashboards/nx-applications-dashboard.json` and `dashboards/nx-applications-monitoring.json` — which cover the pre-V2 applications and stay untouched by V2 work. The two files are unrelated despite the similar names; V1 is in maintenance mode.

For a **service** rather than a connector, copy `dashboards/applications/V2/services/request-service/` instead, drop the `$component` variable, and skip the `pipeline` dashboard — put the domain metrics in `overview`.

---

## Deployment Notes

- See "How dashboards actually reach Grafana" near the top of this file for the full sync mechanism. Summary: a CronJob in `observability` clones `main` every minute, recursively scans `dashboards/`, and writes ConfigMaps that Grafana's sidecar loads.
- Prometheus in `observability` must have `podMonitorNamespaceSelector` configured to discover PodMonitors in the application namespace. If V1 metrics are flowing today, this is already correct.
- Folders, alerts, and datasource JSONs in this repo are **not** part of the active deployment path. Treat them as documentation of intent; configure them via another mechanism if you need them live in Grafana.

## Important Notes

- Dashboard JSON files can be very large (>380KB) due to complex panel configurations.
- All resources use the `"git-sync"` tag for synchronization.
- Template variables (e.g., `$namespace`) are required, not optional, in V2.
- Alert rules reference the datasource UID in their queries.

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
- `$namespace` — `label_values(kube_deployment_spec_replicas{deployment=~".*<name>.*"}, namespace)`. **Never `process_start_time_seconds` here** — see the note below.
- `$component` — **connectors only.** Custom variable with `All` / `Scanner` / `Content` options for connectors that have a content-fetch pod; single-value, used as a job-regex selector. Its option values are full job regexes, not bare names — see the job-label table below. Services have a single pod type and omit this variable.
- `$pod` — `label_values(process_start_time_seconds{job=~"$component", namespace="$namespace"}, pod)` for connectors, or `job=~".*<name>.*"` for services. Multi-value with `includeAll`.

⚠️ **`$namespace` must be fed from kube-state-metrics, not from a process metric.** `process_start_time_seconds` describes the *process*: it does not exist if the pod never ran. Every connector is `minReplicaCount: 0`, so that is the **normal** state, not an edge case. With no options the `current` value saved in the JSON cannot be applied, Grafana interpolates empty, `namespace=""` matches nothing, and the whole board goes blank — including the ~15 backlog and KEDA panels whose own series (`nats_consumer_*`, `kube_horizontalpodautoscaler_*`) survive the sleeping pod perfectly well. That is the board failing to answer "how far behind is it?" in exactly the state the connector spends most of its life in.

Use something that describes the **deployment object** instead: `kube_deployment_spec_replicas`, or anything else from kube-state-metrics. It exists at 0 replicas. Measured on CIFS in dev, where this cost 15 panels; the three CIFS boards and the three Box boards are fixed, the other V2 boards still carry the old query.

Two traps when verifying the fix: a kickoff **hides** the bug (once the pod is awake the old query resolves too, so look at the board *before* generating load), and Prometheus resolves `label_values` at ~2h block granularity, so a window 20 minutes after the pod died still returns the old value. Reproducing it needs an explicit window of *hours* before the last run.

`$pod` is a different case and **does** stay on `process_start_time_seconds`: that variable is meant to list pods that actually exist, and the process collector always exports it — including when `METRICS_ENABLED=false`, where only the Go and process collectors are served — so it still resolves on a pod whose app instruments are switched off.

⚠️ **`$pod` needs `allValue: ".+"`, not `".*"`.** Where a PodMonitor and a Service-level catch-all both scrape the same target, every series arrives twice and only the PodMonitor copy carries a `pod` label. In PromQL `.*` matches the *absent* label too, so `pod=~"$pod"` grabs both copies and every additive aggregation returns exactly double. `histogram_quantile` and `_sum`/`_count` ratios are immune, so percentiles stay right while counters lie and no panel looks obviously broken. Do **not** generalise `.+` to business labels like `$datasource_id` — there `.*` is correct, because series legitimately lacking the label would otherwise be dropped.

Pipeline dashboards add view-specific variables when needed (e.g., `$query_type` for Snowflake/PostgreSQL, `$datasource_id` for CIFS).

### Panel types — which visualization answers which question

Start from the question an operator asks, then pick the panel. A board built by graphing whatever is emitted ends up with a timeseries for everything, and a timeseries is the wrong answer to most of the questions that matter on a scale-to-zero connector.

| Question | Panel | Query idiom |
|---|---|---|
| "How many in this window?" — one number | `stat` | in-range count (below) |
| "What happened to those N?" — a known total split into 2–6 categories | `bargauge`, horizontal | in-range count `sum by (label)`, `> 0`; or one target per category |
| Same, but more than ~6 categories, or two label dimensions | `table` | instant query + `labelsToFields` |
| "When did it happen / how fast is it going?" | `timeseries` | `rate(x[5m])`, title ends in `(rate, 5m)` |
| "How is it distributed?" (latency, size, per-unit cost) | `heatmap` over time **plus** a `bargauge` of the same buckets for the whole range, and a `stat` with **mean / p95** | per-cell counts with the in-range idiom over `[$__interval:30s]`, panel `interval: 30s`, cell values as a plain count; bar gauge = consecutive `le` differences, `> 0` |
| "How close to the ceiling did it get?" (pool, in-flight, queue) | `stat` with the **peak** + `timeseries` with the ceiling as a threshold line | `max_over_time(…[$__range])` |

Rules that come with it:

- **Pair "how many" with "when".** Every outcome breakdown that matters gets a bar gauge (counts in the window) **and** a stacked rate timeseries (when), side by side, with the same colours. The timeseries alone cannot answer "how many": a scan shorter than a scrape interval reads 0 on `rate()` and is still real work.
- **Counts in a range: add up the counter's step-by-step increments.**

  ```
  sum(sum_over_time((
      (last_over_time(x[15s]) - last_over_time(x[1d] offset 15s)) >= 0
    or last_over_time(x[15s]) * 1
  )[$__range:15s]))
  ```

  Every 15s take current minus previous (the sum telescopes exactly for any step; the step is how far behind "now" the panel can lag). If the counter went down, the process restarted and the increment is the new value; if there is no previous value, the series was just born and the whole value counts. `* 1` drops the metric name so both sides of `or` share a label set (without it Prometheus fails with "vector cannot contain metrics with the same labelset").

  Each simpler idiom was tried and is wrong in a case that happens:
  - **`max_over_time` alone** returns the counter's *value* — everything since the process started. Pods outlive a scan (KEDA keeps them 15 minutes, and scans from different datasources share a pod), so narrowing the range to one scan adds the earlier ones. Measured: a 13-owner scan read 65.
  - **Max in the range minus the last value before it** goes negative across a restart under the same pod name (a container crash in the cluster, any restart in local compose) and reads 0.
  - **`increase()`** extrapolates (67 read as 69, a day read 2948 for 3623) and reads 0 for a burst finished before the first scrape.
  - **A short lookback for the previous value** (`[5m]`) finds nothing after a scrape gap and counts the whole cumulative value again: 91 for 26 after a 2-hour gap. `[1d]` costs the same (13ms on a 6h range).

  **Known blind spot:** a counter with labels (a CounterVec child) does not exist until its first increment. If the process restarts under the *same* pod name and the child comes back with exactly its old value (or more), no drop is visible and that restart's increments are lost. In the cluster a new pod has a new name, so this only bites on a container restart inside a pod — and in local compose, where `docker compose restart` keeps the labels: **don't restart connector containers between local test runs.** The real fix is in the connector: create every label combination at 0 at startup (as Box's `InitUserSlots` does).

  Verified on Oracle against four ranges — one fresh pod, one warm pod, one across a restart, one across a 2h gap — all exact. The same idiom feeds window means and percentiles (`_sum`, `_count`, `_bucket` before dividing or `histogram_quantile`). Breakdowns add `> 0`, so categories that only happened outside the range do not show as empty bars.
- **Wrap zero-able terms as `((expr) or vector(0))`, fully parenthesised.** `a + b or vector(0)` parses as `(a + b) or vector(0)` and silently drops the whole sum to 0.
- **Window totals add up every run in the range.** Two scans of the same 67 tables read 134. A title that implies distinct objects is wrong; say so in the description, and narrow the range to one run to count what exists (which only works with the in-range idiom above).
- **Say in the title what is counted.** Attempts are not items: a fork redelivered five times is five attempts and one owner. `Owner Fork Attempts`, not `Owners Forked`.
- **Bar gauge vs bar chart.** Grafana's docs recommend the `barchart` panel for categorical data and describe `bargauge` as "a value against a min and max". We use `bargauge` anyway because it renders a plain PromQL instant result without transformations. The cost: bars scale against the largest value in the panel, so a panel with a single series always draws a full bar — use a `stat` for one value, never a one-bar gauge.
- **No pie charts.** Similar slices are hard to compare; bars say the same thing more clearly.
- **More than ~5 lines in a timeseries is a table.** Open-ended labels (`query_type`, `data_type`, error codes) can grow past that.
- **Semantic colour on every categorical panel**, via `fieldConfig.overrides` `byName` + `fixedColor` — never palette order, which reassigns colours when a series appears or disappears:

  | Class | Colour |
  |---|---|
  | Success | `dark-green` / `green` |
  | Expected absence (`not_found`, `skipped`, `empty`) | `yellow` |
  | Configuration or degraded (`invalid_*`, `permission_denied`, fallbacks, permanent errors) | `orange` |
  | Real failure (`*_failed`, `*_error`, transient errors) | `red`; panics `dark-red` |
  | Neutral split (document kinds, lanes) | `blue` / `purple`, fixed |

- **A heatmap's cell value is a count, not the axis unit.** Format it as a plain number — formatting it in seconds made "3 owners" read as "3.60 s" — and say in the description how to read it: colour = how many fell in that box, not one colour per item. For a single run, the bar gauge of the same buckets beside it is what people can actually read.
- **Anything measured from scrapes has the scrape interval as resolution.** A scan that finishes between two scrapes (a small Oracle database: 5 s, parallel owners) cannot be timed more precisely than that. Say the precision in the title — `Scan Duration (window, ±15 s)` — and keep the number. Do **not** replace small values with text through value mappings: it was tried, read as nonsense ("Objects Failed: < 30 s"), and a mapping added to a list shared between panels leaked into every stat on the board.
- **Gauges sampled at scrape time miss bursts.** A peak stat over a gauge reads 0 for a pool that was saturated for five seconds between scrapes. Say so in the description.
- **One question, one board.** The overview gives the verdict; the pipeline board is the drill-down for the same component. A panel that would be identical on both lives on one of them only — copies drift, because a fix lands on one and not the other (Grafana's own guidance warns against copying). The overview keeps the counts and the story; the pipeline keeps distributions, per-type breakdowns and unit cost.
- **Every board opens with a short text panel** saying how to read it and what it cannot answer: that totals add up every run in the range, that count panels say *how many* and the line charts beside them say *when*, and which splits are impossible (e.g. no datasource label). A limit discovered in a description hover is a limit nobody discovers.
- **Don't combine unrelated counters in one stat.** Two values that answer different questions get two stats, each with its own name.

### Panel descriptions

Descriptions are read in a hover by someone who does not know the code. Write them in plain English — no metric names, no internal function names — in three short parts, separated by blank lines (the field renders Markdown):

1. **What it counts**, in one sentence a newcomer understands.
2. **Normal / worry** — what a healthy value looks like and what a bad one means.
3. **Next** — which panel or board to look at to go further.

```
**Errors the connector found but could not report.** When a table fails, the connector adds it to the job's error list — what the UI shows. This counts the ones that never got there.

**Normal:** 0. Anything else means the job's error list is incomplete: the failures happened, nobody will see them.

**Next:** the breakdown by reason beside it.
```

Configuration values a reader needs to judge a number (a pool ceiling, maxDeliver, a cooldown) go in the title or the description, with the setting that controls them — a reader should never have to open the chart's values to know whether 14 is a lot.

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
| Oracle | `-oracle-connector-be-go`, `-oracle-connector-be-go-content` |
| NFS | **none — no PodMonitor exists**, so NFS is not scraped at all (not even runtime metrics) |
| Registration Service | `-registration-service` (note: no `-be-go`) |
| Request Service | `-request-service` (note: no `-be-go`) |
| Authz Service | `-authz-service` (note: no `-be-go`) |
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
Native Prometheus connectors emit `<connector>_connector_*` (e.g., `snowflake_connector_items_sent_total`). Oracle uses `oracle_scanner_*` / `oracle_content_*`, and — like every database connector today (MySQL, PostgreSQL, Snowflake) — carries **no `datasource_id` label**, so its boards cannot split anything by datasource; only CIFS and Box can. CIFS and Box use a per-subsystem shape instead — `cifs_scanner_*` / `cifs_augmenter_*` / `cifs_content_*`, and `box_scanner_*` / `box_augmenter_*` / `box_api_*` / `box_content_*` — which is the current convention for new work, because it lets a query be reused across connectors with a namespace swap. SharePoint is the last one still on the OTel meter and emits `graph_*`. Histograms use `_seconds` suffix and exponential buckets — **note that bucket ranges differ across connectors**, so latency panels are connector-specific (no shared library panel for histograms today).

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

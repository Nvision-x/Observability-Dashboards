# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Grafana dashboards for NX infrastructure and application monitoring: dashboard JSON, folder definitions, alert rules and reference datasources. Grafana runs in the `observability` namespace; the connectors and services it monitors run in application namespaces (normally `default`).

One tree serves two kinds of Grafana:

- **Per-cluster Grafanas** (dev, integration, each customer cluster) with one local Prometheus. They use the **per-cluster boards**: one board per component view, with their own pickers.
- **The central (mimir) Grafana**, which wants a few big boards. It uses the **consolidated boards** (Connectors Detail, Services Detail, Infrastructure Overview, Content Service (Legacy), Applications Overview), one collapsed row per component.

Every Grafana syncs every file under `dashboards/`, so both kinds exist everywhere. The consolidated boards are **generated** from the per-cluster boards; see "Per-cluster sources and generated boards" below. That is what keeps them from drifting apart again (on 09-18 main replaced the per-cluster boards with hand-made consolidated copies, development kept editing the per-cluster ones, and the two diverged for a month).

## Top-Level Layout

```
dashboards/
  cluster-health-overview.json, global-monitoring.json      # hand-maintained landing pages (Grafana root)
  applications-overview-central.json                         # hand-maintained, except its V2 section (GENERATED)
  infrastructure-overview.json                               # GENERATED from the infra boards below
  kong-dashboard.json, nats-explorer.json, opensearch-metrics-central.json, prometheus2.json,
  pulsar-explorer.json, nvidia-dcgm-gpu.json                 # per-cluster infra boards (sources)
  sharepoint-connector-dashboard.json, xberg-dashboard.json, apps-s3-inventory-connector.json,
  content-service-*.json                                     # per-cluster V1-era boards (sources)
  *.json (others at the top level)                           # per-cluster V1 boards, not generated from
  applications/
    connectors-detail.json                                   # GENERATED from the connector boards
    services-detail.json                                     # GENERATED from the service boards
    content-service-legacy.json                              # GENERATED from content-service-*.json
    backend-workers.json                                     # source of the Backend Workers row
    V2/
      applications-overview.json                             # per-cluster V2 roll-up
      connectors/<name>/<name>-{overview,pipeline,runtime}.json
      services/<name>/<name>-{overview,runtime}.json
  backups/  scans/                                           # hand-maintained central boards
folders/                                                     # folder definitions (documentation only, not synced)
  connectors/  services/                                     # V2 component folders
tools/
  build-detail.py                                            # generator + validator
  detail-boards.json                                         # which sources make which generated board
alerts/  datasources/                                        # not synced (see below)
.github/workflows/
  dashboards-check.yml                                       # CI: generated boards up to date, shared rules hold
  release.yml                                                # CalVer tag + GitHub Release on push to main
```

## Per-cluster sources and generated boards

**Edit the per-cluster board, never a generated one.** The generated files are rebuilt from scratch; a hand edit is lost on the next build and fails CI before that.

| Generated board | uid | Built from |
|---|---|---|
| `dashboards/applications/connectors-detail.json` | `nx-connectors-detail` | V2 CIFS, MySQL, PostgreSQL, Snowflake, Oracle, Box boards; SharePoint, Xberg, S3 Parquet boards |
| `dashboards/applications/services-detail.json` | `nx-services-detail` | V2 Content Service, Authz, Credential Manager, Datasource Service, Knowledge Hub (sidecar, standalone), Knowledge Service, Registration, Request boards; Backend Workers |
| `dashboards/infrastructure-overview.json` | `nx-infrastructure-overview` | Kong, NATS, OpenSearch, Prometheus, Pulsar, NVIDIA GPU boards |
| `dashboards/applications/content-service-legacy.json` | `content-service` | the three `content-service-*.json` boards (the per-cluster Content Service board is `content-service-cluster`) |
| `dashboards/applications-overview-central.json`, panels after row id 10004 only | `nx-applications-overview` | `dashboards/applications/V2/applications-overview.json` (drill-down links rewritten to the consolidated boards) |

The exact list is `tools/detail-boards.json`. Each generated file says so in its `__generated` key and in its first text panel.

### Workflow

```bash
# after editing any source board
python3 tools/build-detail.py            # rebuild the generated boards and validate everything
git add dashboards tools && git commit   # commit the source change AND the regenerated boards together

python3 tools/build-detail.py --check    # what CI runs: no writes, fails on drift or a broken rule
python3 tools/build-detail.py --fix-sources   # apply the shared rules to source boards (small, in-place edits)
python3 tools/build-detail.py -v         # also print how source variables were named
```

On a merge conflict in a generated file, do not resolve it by hand: take either side, run `python3 tools/build-detail.py`, commit.

### What the generator does

- One collapsed row per section; inside it, each source board under a small header that links back to the per-cluster board. A source's own rows become text headers (Grafana does not support rows inside a collapsed row).
- Panel ids are renumbered across the board; dashboard-level links of the sources are dropped.
- Variables: `$datasource` becomes the board's single hidden datasource variable. Every other source variable is prefixed with the section key (`cifs_pod`, `box_datasource_id`, `sharepoint_job`). Identical definitions within a section share one variable; a section's `unify` entry forces one definition (used for `pod`); Knowledge Hub sidecar and standalone are separate sections so their pods never mix.
- **Every generated board is built with `"pickers": "hide"`, so it looks and queries exactly as the hand-made boards did on main before generation:** each per-section variable becomes a hidden constant `.*` (and any `label="$x"` on it becomes `=~`), `namespace` is a hidden constant `default` on Connectors and Services Detail, and only the variables listed in `keep_vars` stay real pickers (the Scanner/Content component pickers of Connectors Detail, with the same names, defaults and visibility as before). For per-pod, query-type or datasource-id filtering, use the per-cluster board each section header links to.
- `"pickers": "show"` instead keeps every source variable as a real picker (chained queries work, there is no per-client repeat any more). It changes the top bar and the default queries, so switching a board to it is a deliberate change, not a fix.
- `link_map` rewrites drill-down URLs (e.g. per-cluster `content-service-cluster` back to `content-service`, and V2 overview links to the consolidated boards).
- Output is written one panel per line: fully indented, Connectors Detail would exceed the ConfigMap limit.

### Shared rules (checked on every build and in CI)

Applied to every source and generated board, and the generic ones to every file under `dashboards/`:

- JSON parses; unique `uid` (at most 40 characters) across `dashboards/`; unique title per folder; unique panel ids; no overlapping panels and nothing wider than 24 columns.
- **No `label=".*"`** (or `".+"`): with `=` it matches only the literal string and the panel shows No data. Use `=~`.
- No `label="$var"` when `$var` is multi-value or has All; use `=~`.
- No reference to an undefined variable.
- **The datasource variable** is `type: datasource`, `query: prometheus`, `current: default`, `hide: 2`, `refresh: 1`. A saved uid that does not exist in some Grafana (the V2 boards used to save `prometheus-nx`) blanks the board there. `--fix-sources` sets it.
- Size at most 1 MiB minus 8 KiB (the ConfigMap limit); a warning above 90%. To shrink a generated board, move a section into a new board in the manifest.
- The file path must give a valid ConfigMap name (lowercase letters, digits, `-`, `.`: no underscores) and the file name a valid ConfigMap key. See the sync section below.

### Adding a board

1. Create the per-cluster board as usual (V2 conventions below), with the standard datasource variable.
2. If it belongs in a consolidated view, add its path to the right section of `tools/detail-boards.json` (or add a section: `key` is the variable prefix, `label` the picker label, `title` the row title).
3. If it is a new V2 component, add its row to `dashboards/applications/V2/applications-overview.json`; the central Applications Overview picks it up on the next build.
4. Run `python3 tools/build-detail.py` and commit everything it changed.

## Branches: development first, then main

- **Dev Grafana renders `development`** (`dashboardSync.branch: development` in `nxdeployment-development-env` `values.yaml`). Every other Grafana, including customer clusters and the central one, renders **`main`** (the `nx-application-helm` observability chart default).
- **Changes go to `development` first and reach `main` by promotion** (a development -> main PR), the same as code. Check them on dev Grafana before promoting.
- **No restructures straight on `main`.** Moving, merging, renaming or deleting boards on main while development keeps editing them is what produced the 09-18 split. If the central Grafana needs a different shape, change the manifest or the generator on development and promote it.
- A fix made directly on main (hotfix) must be merged back into development the same day.

## How dashboards actually reach Grafana

**The GitHub Release workflow is NOT in the deployment path.** It tags and bundles JSONs for audit/versioning only.

The sync is configured in `nx-application-helm/charts/observability` and uses a CronJob image (`ghcr.io/nvision-x/grafana-dashboards-sync`, source: the `grafana-dashboards-sync` repo, `sync-dashboards.sh`):

1. The CronJob runs every minute in the `observability` namespace (`concurrencyPolicy: Forbid`).
2. It clones this repo at the configured branch (`main` by default, `development` on dev; a `COMMIT` pin overrides the branch).
3. **Phase 1 (cleanup):** deletes every ConfigMap whose name starts with `observability-grafana-dashboard-`.
4. **Phase 2 (process):** `find dashboards -name "*.json" -type f` (recursive, no depth limit), skips files that fail `jq`, and runs `kubectl create configmap <name> --from-file=<basename>=<file>` for each. The name is `observability-grafana-dashboard-` + the path without `.json`, `/` replaced by `-`, lowercased: `dashboards/applications/V2/connectors/snowflake/snowflake-overview.json` -> `observability-grafana-dashboard-dashboards-applications-v2-connectors-snowflake-snowflake-overview`. A name Kubernetes rejects (an underscore in the path, more than 253 characters) or a file over the 1 MiB ConfigMap limit is skipped with a warning and the dashboard silently disappears; the validator checks both.
5. ConfigMaps are labelled `grafana_dashboard=1`, `app.kubernetes.io/managed-by=grafana-dashboards-sync`, `app.kubernetes.io/component=grafana-dashboard`.
6. Grafana's sidecar (kube-prometheus-stack, `sidecar.dashboards.label: app.kubernetes.io/component`) loads them.

### Implications for editing this repo

- ✅ **Subdirectories work** (recursive `find`), and moving a file only renames its ConfigMap; Grafana keys dashboards by `uid`.
- ❌ **Only `dashboards/` is synced.** `folders/`, `alerts/`, `tools/` and `datasources/` are inert.
- ❌ **No folder mechanism.** `folders/` isn't synced and the sidecar has no `folderAnnotation`, so folders must already exist in Grafana for a dashboard's `folderUid` to be honoured.
- ❌ **No alert sync.** `alerts/*.json` is not deployed by anything in this stack.
- ⚠️ **Cleanup-then-recreate** every minute: a removed file vanishes from Grafana within a minute of reaching the synced branch; a file that fails `jq` is skipped, others are unaffected.
- ⚠️ **Two dashboards with the same `uid` overwrite each other** in Grafana. The validator rejects duplicates.
- ⚠️ **The `"git-sync"` tag is decorative.** Keep it for consistency.

---

# V1 (Original) — Legacy / Maintenance Mode

V1 is the pre-V2 board set. **Do not add new dashboards here.** Only modify V1 files for bug fixes or until the V2 equivalent has been shipped and verified.

## V1 Layout

- V1-era per-cluster boards live at the top of `dashboards/` (paths, uids, titles and folders unchanged from development), plus `dashboards/applications/backend-workers.json`.
- `folders/applications-folder.json`, `folders/infrastructure-folder.json`, `folders/backups-folder.json`, `folders/scans-folder.json`: flat parent folders, `parentUid: ""`.
- `datasources/prometheus-nx.json`, `datasources/loki-nx.json`: legacy reference (not synced).
- `alerts/nx-applications-alerts.json`, `alerts/nx-infrastructure-alerts.json`.

## V1 Conventions

- **Datasource references:** use `{"type": "prometheus", "uid": "${datasource}"}` and the standard datasource variable (see V2 template variables). Literal `"Prometheus"` references were replaced on the boards that still had them.
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
- `$datasource` — type `datasource`, query `prometheus`, `current` = `default` (Grafana's default datasource), `refresh: 1`, `hide: 2`. Never save a concrete uid such as `prometheus-nx`: it does not exist in every Grafana and blanks the board where it is missing. CI enforces this; `python3 tools/build-detail.py --fix-sources` sets it.
- `$namespace` — `label_values(kube_deployment_spec_replicas{deployment=~".*<name>.*"}, namespace)`. **Never `process_start_time_seconds` here** — see the note below.
- `$component` — **connectors only.** Custom variable with `All` / `Scanner` / `Content` options for connectors that have a content-fetch pod; single-value, used as a job-regex selector. Its option values are full job regexes, not bare names — see the job-label table below. Services have a single pod type and omit this variable.
- `$pod` — `label_values(process_start_time_seconds{job=~"$component", namespace="$namespace"}, pod)` for connectors, or `job=~".*<name>.*"` for services. Multi-value with `includeAll`.

⚠️ **`$namespace` must be fed from kube-state-metrics, not from a process metric.** `process_start_time_seconds` describes the *process*: it does not exist if the pod never ran. Every connector is `minReplicaCount: 0`, so that is the **normal** state, not an edge case. With no options the `current` value saved in the JSON cannot be applied, Grafana interpolates empty, `namespace=""` matches nothing, and the whole board goes blank — including the ~15 backlog and KEDA panels whose own series (`nats_consumer_*`, `kube_horizontalpodautoscaler_*`) survive the sleeping pod perfectly well. That is the board failing to answer "how far behind is it?" in exactly the state the connector spends most of its life in.

Use something that describes the **deployment object** instead: `kube_deployment_spec_replicas`, or anything else from kube-state-metrics. It exists at 0 replicas. Measured on CIFS in dev, where this cost 15 panels. Fixed: Box, CIFS, Oracle, PostgreSQL, Snowflake, and the authz / credentialmanager / datasource / registration / request service boards. Still on the old query: MySQL, Knowledge Hub, Knowledge Service, the content-service runtime board and `applications-overview.json`.

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

  **Known blind spot:** a counter with labels (a CounterVec child) does not exist until its first increment. If the process restarts under the *same* pod name and the child comes back with exactly its old value (or more), no drop is visible and that restart's increments are lost. In the cluster a new pod has a new name, so this only bites on a container restart inside a pod — and in local compose, where `docker compose restart` keeps the labels: **don't restart connector containers between local test runs.** The real fix is in the connector: create every label combination at 0 at startup (as Box's `InitUserSlots` and PostgreSQL's `metrics.init()` do). Measured on PostgreSQL before that fix: 6 content fetches after a `docker compose` restart read 4, because the children came back above the values the same pod name had left in the 1-day lookback.

  **Local-only trap:** the local Prometheus scrapes every 10 s, faster than the 15 s step, so two samples can share a step and the idiom only sees the last one. A restart inside the same step as the increments before it (4 → 8 → 0) loses them. In the cluster (30 s scrape) a step holds at most one sample. When validating locally, leave more than 15 s between a burst, a restart and the next burst.

  Verified on Oracle against four ranges — one fresh pod, one warm pod, one across a restart, one across a 2h gap — all exact; and on PostgreSQL for all four (gap: 7 minutes with Prometheus stopped while a scan ran — 278 tables read 278; the same query with a `[5m]` lookback read 2318). The same idiom feeds window means and percentiles (`_sum`, `_count`, `_bucket` before dividing or `histogram_quantile`). Breakdowns add `> 0`, so categories that only happened outside the range do not show as empty bars.
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

- **A stat's title must fit its width, or the part that explains the number is what gets cut.** Measured on a ~1800 px screen: about 13 characters at `w: 3`, 21 at `w: 4`, 28 at `w: 5`, 36 at `w: 6`. "Scan Duration (window, ±15 s)" rendered as "Scan Duration …" and lost the ±15 s that explains a 0. Rules: drop `(window)` / `(total)` (every stat counts the range, and the row title says so); put the qualifier first and short (`Peak Connections /20`, `Duration ±15s`); move a qualifier that must survive into the value with a unit suffix (`"unit": "suffix: attempts"` renders "5 attempts"); never give two panels on one board the same title (rename the row-level repeat: `Found` / `Failed` / `Sent`). Check with the width table above after editing a board.
- **Panel ids are unique within a board.** Grafana uses the id for "View panel", direct links and editing; two panels sharing an id overwrite each other in those views. `box-overview` shipped with five duplicated ids (fixed); check with `jq '[.panels[].id] | group_by(.) | map(select(length > 1))'` after hand-editing a board.

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
Native Prometheus connectors emit `<connector>_connector_*` (e.g., `snowflake_connector_items_sent_total`). Oracle uses `oracle_scanner_*` / `oracle_content_*`, and — like every database connector today (MySQL, PostgreSQL, Snowflake) — carries **no `datasource_id` label**, so its boards cannot split anything by datasource; only CIFS and Box can. CIFS and Box use a per-subsystem shape instead — `cifs_scanner_*` / `cifs_augmenter_*` / `cifs_content_*`, and `box_scanner_*` / `box_augmenter_*` / `box_api_*` / `box_content_*` — which is the current convention for new work, because it lets a query be reused across connectors with a namespace swap. SharePoint is the last one still on the OTel meter and emits `graph_*`. PostgreSQL emits `postgresql_connector_*` from one metrics package that the scanner and content modes share, so **both pods export every family** (the other mode's counters sit at 0): pin `job` on every PostgreSQL selector, not just `namespace`/`pod`. Histograms use `_seconds` suffix and exponential buckets — **note that bucket ranges differ across connectors**, so latency panels are connector-specific (no shared library panel for histograms today).

Services differ from connectors here:
- **Domain metrics are per-service and not prefixed by the service name automatically.** Request service names its own instruments `request_service_*`; registration service does not, and emits a bare `connector_registrations_total`. The `Namespace` field on `pipeline-lib-go/metrics.Config` sets the OTel *meter* name (instrumentation scope), **not** a Prometheus metric prefix — the exporter is created with a plain `prometheus.New()`. Do not assume a service prefix.
- **Services on `pipeline-lib-go` also emit a shared HTTP/gRPC set** when they install it: `http_requests_total`, `http_request_duration_seconds`, `http_active_requests`, `http_request_size_bytes`, `http_response_size_bytes`, `grpc_requests_total`, `grpc_request_duration_seconds`, `grpc_active_requests`. Labels are `method` / `route` / `status` (HTTP) and `method` / `code` / `status` (gRPC). Group and filter gRPC by `code` (`"0"` is OK), never by `status` — that label is free text including the error message, so its cardinality is unbounded.
- Installing that set is opt-in per service. Registration service installs both. Request service installs the HTTP set only — it serves Connect RPC over HTTP, so its RPCs are counted as HTTP requests and there are no `grpc_*` series. Its SSE `/events` route is deliberately excluded from instrumentation (the middleware's `ResponseWriter` wrapper has no `Flush`, which would break the stream), so it never appears as a `route` and never inflates `http_active_requests`.
- ⚠️ **Bucket boundaries on the shared histograms are opt-in — check before writing a percentile panel.** `pipeline-lib-go` does not apply boundaries for you: `NewGRPCMetrics(provider, buckets)` and `NewHTTPMetrics(provider, map[HTTPHistogram][]float64{...})` take them per histogram, and passing nil keeps the OTel SDK default. That default is tuned for milliseconds (`0, 5, 10, 25 … 10000`); against a `s` unit every real request lands in `le=5` and `histogram_quantile` returns noise, and against a `By` unit anything over ~10 KB lands in `+Inf`. A percentile is only trustworthy where the service opted in — read its construction call, and prefer `rate(_sum)/rate(_count)` where it didn't.
  - Ready-made ladders: `SubsecondLatencyBuckets()` (0.005s–10s), `BodySizeBuckets()`, `LargeBodySizeBuckets()`.
  - Registration service opts in for gRPC and HTTP duration, and passes its own wider `BodySizeBuckets()` for both size histograms. All its percentiles are valid.
  - Request service opts in for HTTP duration and **response** size, and deliberately leaves **request** size on the SDK default (finer below 256 B, which suits the small Connect messages and bare probes it accepts). Don't write a request-size percentile for it.
  - Service-defined histograms carry their own boundaries independently: `request_service_connectiontest_duration_seconds` uses a 0.1s–300s ladder, because a connection test runs on a different timescale from an HTTP request.
- ⚠️ **`go_gc_duration_seconds` is a summary, not a histogram.** There is no `_bucket` series, so `histogram_quantile(…, rate(go_gc_duration_seconds_bucket[…]))` returns nothing. Use `go_gc_duration_seconds{quantile=~"1(\\.0)?"}` (max pause); available quantiles are `0`, `0.25`, `0.5`, `0.75`, `1` — there is no `0.99`.
- ⚠️ **Prometheus 3 rewrites integer `quantile` and `le` values on ingestion: `"1"` is stored as `"1.0"`.** The cluster runs Prometheus 3 (kube-prometheus-stack 92.8.0), so `quantile="1"` and `le="1024"` match nothing and the panel is silently empty. Match both renderings (`quantile=~"1(\\.0)?"`) or use the stored form (`le="1024.0"`); non-integers (`"0.5"`, `"0.05"`) are unchanged. The GC max-pause panel was empty this way on every V2 runtime board; PostgreSQL's is fixed, the others are not yet.

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
9. Add the new boards to the right section of `tools/detail-boards.json`, run `python3 tools/build-detail.py`, and commit the regenerated boards with your change.

**Which overview file.** V2 components belong in `dashboards/applications/V2/applications-overview.json` and **only** there. Its rows are copied into the central `applications-overview-central.json` by `tools/build-detail.py` (the V2 section after row 10004), so never edit that section of the central board by hand. The old V1 roll-ups (`nx-applications-dashboard.json`, `nx-applications-monitoring.json`) were removed.

For a **service** rather than a connector, copy `dashboards/applications/V2/services/request-service/` instead, drop the `$component` variable, and skip the `pipeline` dashboard — put the domain metrics in `overview`.

---

## Deployment Notes

- See "How dashboards actually reach Grafana" near the top of this file for the full sync mechanism. Summary: a CronJob in `observability` clones `main` (`development` on dev) every minute, recursively scans `dashboards/`, and writes one ConfigMap per file that Grafana's sidecar loads.
- Prometheus in `observability` must have `podMonitorNamespaceSelector` configured to discover PodMonitors in the application namespace. If V1 metrics are flowing today, this is already correct.
- Folders, alerts, and datasource JSONs in this repo are **not** part of the active deployment path. Treat them as documentation of intent; configure them via another mechanism if you need them live in Grafana.

## Important Notes

- Dashboard JSON files can be very large (>380KB) due to complex panel configurations.
- All resources use the `"git-sync"` tag for synchronization.
- Template variables (e.g., `$namespace`) are required, not optional, in V2.
- Alert rules reference the datasource UID in their queries.

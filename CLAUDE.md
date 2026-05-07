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
folders/
  applications-v2-folder.json             # parentUid: applications-folder
  connectors/
    <connector>-folder.json               # parentUid: applications-v2-folder
```

Snowflake is the V2 reference implementation. Use it as the template for new connectors.

## V2 Conventions

### Naming
- Dashboard UIDs: `apps-v2-<connector>-<view>` (e.g., `apps-v2-snowflake-pipeline`).
- Connector folder UIDs: `apps-v2-<connector>-folder`.
- File path encodes the structure: `dashboards/applications/V2/connectors/<connector>/<connector>-<view>.json`.

### Tags
Every V2 dashboard MUST include in `tags`:
- `git-sync` — required for sync.
- `apps-v2` — identifies V2 set.
- `connector:<name>` — e.g., `connector:snowflake`.
- One view tag: `overview` | `pipeline` | `runtime`.

### Folder placement
- Set `folderUid` at the top level of every V2 dashboard JSON.
- Folder JSONs use `parentUid` to nest. The parent V2 folder lives under the V1 `applications-folder` to avoid colliding with existing navigation.

### Template variables (V2 standard)
Every connector dashboard declares these in `templating.list`, in this order:
- `$datasource` — type `datasource`, query `prometheus`. Default value should match the actual Prometheus datasource UID used in your Grafana (CLAUDE.md previously claimed `prometheus-nx` but V1 dashboards use `${DS_PROMETHEUS}` or `Prometheus` — confirm against your real Grafana before relying on the default).
- `$namespace` — `label_values(up{job=~"<connector>-be-go.*"}, namespace)`.
- `$component` — custom variable with `All` / `Scanner` / `Content` options for connectors that have a content-fetch pod (e.g., Snowflake, Box, PostgreSQL); single-value, used as a job-regex selector.
- `$pod` — `label_values(up{job=~"$component", namespace="$namespace"}, pod)`, multi-value with `includeAll`.

Pipeline dashboards add view-specific variables when needed (e.g., `$query_type` for Snowflake/PostgreSQL, `$datasource_id` for CIFS).

### Job-label conventions
The `nx-application-helm` chart sets `app.kubernetes.io/name: <connector>-be-go` on every connector pod. Kube-prometheus PodMonitors map that label to Prometheus's `job` label. So the canonical selectors are:

| Connector | Job label(s) |
|---|---|
| Snowflake | `snowflake-connector-be-go`, `snowflake-connector-be-go-content` |
| CIFS | `cifs-connector-be-go` |
| PostgreSQL | `postgresql-connector-be-go`, `postgresql-connector-be-go-content` |
| Box | `box-connector-be-go`, `box-connector-be-go-content` |
| SharePoint | `sharepoint-connector-be-go` |
| NFS | `nfs-connector-be-go` (no app metrics yet — runtime dashboard only) |

Use `job=~"<connector>-be-go.*"` to cover both scanner and content variants in one selector.

### Cross-dashboard links
Every connector dashboard's `links` array includes links to its sibling overview / pipeline / runtime dashboards plus the V2 root `apps-v2-overview`. Use `${var:queryparam}` to propagate `$namespace` and `$component` across links so the user keeps their context when drilling.

### Metric naming
Native Prometheus connectors emit `<connector>_connector_*` (e.g., `snowflake_connector_items_sent_total`). OTel-based connectors emit different prefixes (Box: `box_*`, SharePoint: `graph_*`). Histograms use `_seconds` suffix and exponential buckets — **note that bucket ranges differ across connectors**, so latency panels are connector-specific (no shared library panel for histograms today).

## Creating a New V2 Connector Dashboard Set

1. Verify the connector emits Prometheus metrics. Check `<repo>-connector-be-go/internal/metrics/metrics.go` (or equivalent). If there are no metrics, scaffold only the `runtime` dashboard and open a follow-up to instrument the connector.
2. Confirm the helm `selectorLabels` in `nx-application-helm/charts/applications/templates/_helpers.tpl` to derive the exact `job=` label.
3. Copy the Snowflake folder under `dashboards/applications/V2/connectors/snowflake/` to `<connector>/`, rename files, and update:
   - `uid` (per dashboard)
   - `folderUid`
   - `tags` (`connector:<name>`)
   - All `<connector>_connector_*` metric names
   - `links` URLs to point to the new `apps-v2-<connector>-<view>` UIDs
   - `templating.list` `query` strings (replace `snowflake-connector-be-go.*` with `<connector>-be-go.*`)
4. Create `folders/connectors/<connector>-folder.json` with `parentUid: applications-v2-folder`.
5. Add a new collapsed row to `dashboards/applications/V2/applications-overview.json` with at minimum a `Pods Up` stat panel and a link to the new `<connector>-overview` dashboard.
6. Validate JSON parses (`python3 -c "import json; json.load(open('path.json'))"`).
7. Open in Grafana — confirm template variables resolve, drill-down links carry the namespace, and at least one panel returns data.

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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Grafana dashboards configuration repository for NX infrastructure and application monitoring. It contains JSON-based Grafana dashboards, datasources, alert rules, and folder definitions that are synchronized to Grafana instances via GitSync.

## Repository Structure

- `dashboards/` - Grafana dashboard JSON files for applications and infrastructure monitoring
  - Application dashboards: `nx-applications-dashboard.json`, `nx-applications-monitoring.json`, `apps-connector.json`, `apps-enricher.json`, etc.
  - Infrastructure dashboards: `nx-infrastructure-overview.json`, `prometheus2.json`
  - Messaging dashboards: `nats-dashboard.json`, `nats-explorer.json`, `pulsar-monitor.json`, `pulsar-topic-official.json`, `pulsar-explorer.json`
- `datasources/` - Legacy JSON datasource configurations (for reference only)
  - `prometheus-nx.json` - Prometheus datasource pointing to http://127.0.0.1:9090
  - `loki-nx.json` - Loki datasource for logs
- `alerts/` - Alert rule definitions
  - `nx-applications-alerts.json` - Application-level alerts (error rates, latency, etc.)
  - `nx-infrastructure-alerts.json` - Infrastructure alerts
- `folders/` - Folder organization definitions
  - `applications-folder.json`, `infrastructure-folder.json`, `app-metrics-folder.json`
- `provisioning/` - Grafana provisioning configuration (directory structure only, no YAML files present)

## Key Concepts

### GitSync Tag System
All dashboards, datasources, and resources include a `"git-sync"` tag in their `tags` array. This tag enables automatic synchronization between this Git repository and Grafana instances. When modifying any JSON file, ensure this tag is preserved.

### Dashboard Structure
Each dashboard JSON file contains:
- `uid` - Unique identifier (e.g., `"nx-applications-dashboard"`)
- `title` - Display name
- `tags` - Array including `"git-sync"` and categorization tags
- `panels` - Visualization panels with PromQL queries
- `schemaVersion` - Grafana schema version (typically 39)
- `refresh` - Auto-refresh interval (e.g., `"15s"`)

### Dashboard Organization
Dashboards are organized into folders:
- **Applications** - Application-level metrics (APIs, microservices)
- **Infrastructure** - Infrastructure monitoring (nodes, resources)
- **App Metrics** - Specific application performance metrics

Folders are defined in `folders/` directory with UIDs that dashboards reference.

### Metric Queries
Dashboards use Prometheus/PromQL queries that target:
- Container metrics: `container_cpu_usage_seconds_total`, `container_memory_usage_bytes`, `container_network_*`
- HTTP metrics: `http_requests_total`, `http_request_duration_seconds`
- Namespace filtering: Most queries include `namespace='$namespace'` template variable
- Pod-level aggregation: `sum by (pod)` patterns are common

## Working with Dashboards

### Modifying Existing Dashboards
1. Read the entire dashboard JSON file
2. Locate the specific panel or configuration to modify
3. Update the JSON structure, preserving:
   - The `"git-sync"` tag in the tags array
   - The dashboard UID
   - Proper JSON formatting and structure
4. Commit changes - GitSync will automatically deploy to Grafana

### Creating New Dashboards
1. Use an existing dashboard as a template (e.g., `dashboards/nx-applications-dashboard.json`)
2. Assign a unique `uid` (lowercase with hyphens)
3. Set appropriate `title` and `tags` (must include `"git-sync"`)
4. Define panels with appropriate PromQL queries
5. Set folder reference if categorizing
6. Save to `dashboards/` directory

### Alert Rules
Alert rules in `alerts/` directory follow this structure:
- `title` - Alert group name
- `folder` - Target folder for organization
- `interval` - Evaluation interval (e.g., `"30s"`)
- `rules[]` - Array of alert definitions with:
  - `uid` - Unique alert identifier
  - `condition` - Reference to evaluation expression
  - `data[]` - Prometheus queries and threshold expressions
  - `for` - Duration before firing
  - `annotations` - Description and summary
  - `labels` - Severity and categorization

## Deployment

The repository is designed for GitSync integration:
1. Changes pushed to GitHub are automatically synchronized to Grafana
2. Grafana should mount:
   - `provisioning/` → `/etc/grafana/provisioning/`
   - `dashboards/` → `/var/lib/grafana/dashboards/`
3. The `"git-sync"` tag enables automatic discovery and updates

## Dashboard Naming Conventions

- Application monitoring: `apps-*` or `nx-applications-*`
- Infrastructure: `nx-infrastructure-*`
- Service-specific: `nats-*`, `pulsar-*`
- Monitoring variations: `*-monitor`, `*-explorer`, `*-dashboard`

## Important Notes

- Dashboard JSON files can be very large (>380KB) due to complex panel configurations
- All resources use the `"git-sync"` tag for synchronization
- Template variables (e.g., `$namespace`) are common for filtering
- Dashboards target the Prometheus datasource UID `"prometheus-nx"`
- Alert rules reference datasource UID in their queries

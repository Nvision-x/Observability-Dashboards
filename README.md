# Grafana Dashboards Repository

This repository contains Grafana dashboards and datasources for NX infrastructure monitoring.

This is a post deployment test.

## Structure

```
grafana-dashboards/
├── provisioning/
│   ├── datasources/
│   │   └── datasources.yaml          # Datasource provisioning config
│   └── dashboards/
│       └── dashboards.yaml           # Dashboard provisioning config
├── datasources/                      # Legacy JSON datasource files (for reference)
│   ├── prometheus-nx.json
│   └── loki-nx.json
├── dashboards/                       # Dashboard JSON files
│   ├── nx-applications-dashboard.json
│   ├── nx-applications-monitoring.json
│   └── nx-infrastructure-overview.json
├── folders/                          # Folder definitions
│   ├── applications-folder.json
│   └── infrastructure-folder.json
└── alerts/                           # Alert rules
```

### Deployment

Make sure your Grafana deployment mounts:

- `provisioning/` directory to `/etc/grafana/provisioning/`
- `dashboards/` directory to `/var/lib/grafana/dashboards/`
- `folders/` directory for folder definitions

## Usage

1. Push this repository to GitHub
2. Configure GitSync in Grafana to point to this repository
3. Any changes to JSON files will sync automatically to Grafana

## Post Deployment Test

1. Render pass. Open the dashboard with its default variables and default time range. Then:

   Expand every collapsed row.
   Log any panel showing an error triangle, “No data”, “Datasource not found”, or an Angular deprecation notice.
   For every “No data”, decide whether it’s legitimate (for example, no GPUs or no traffic) or a query defect. Open the panel in Explore and drop filters until data appears to find which one is wrong.

2. Variable pass. For each variable:

   Confirm the dropdown populates.
   Change its value and confirm the panels actually change.
   For multi-value variables, test a single value, several values, and All.
   For chained variables, confirm that changing the parent refreshes the child.

3. Accuracy pass. Pick 2–3 headline stats per dashboard, such as pod counts, error rates and totals. Run the same query in Explore, or check kubectl for counts, and confirm the numbers match. Also confirm units: bytes vs bits, seconds vs ms, percent as 0–1 vs 0–100.

4. Behavior pass. Check four things:

   Thresholds color correctly: create or find a known-bad condition and confirm it goes red.
   Links and drill-downs land on the right dashboard with the context carried over.
   Changing the time range (1h, 24h, 7d) doesn’t break rate windows or time out.
   The dashboard is readable at a laptop screen width.

   Log every finding with: dashboard UID, row, panel title, the variable values used, expected vs actual, and severity (wrong data > broken > cosmetic).

## Dashboard Guidelines

- Use unique UIDs for each dashboard
- Include proper tags for organization
- Test locally before pushing changes
- All dashboards and datasources include the `git-sync` tag for automated synchronization

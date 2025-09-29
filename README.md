# Grafana Dashboards Repository

This repository contains Grafana dashboards and datasources for NX infrastructure monitoring.

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

## Dashboard Guidelines

- Use unique UIDs for each dashboard
- Include proper tags for organization
- Test locally before pushing changes
- All dashboards and datasources include the `git-sync` tag for automated synchronization

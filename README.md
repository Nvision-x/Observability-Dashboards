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

## Configuration Fixed

### Issues Resolved:
1. **Dashboard Structure**: Fixed "Dashboard title cannot be empty" error by moving dashboard properties to root level
2. **Datasource Configuration**: Created proper YAML provisioning files instead of JSON files being loaded as dashboards  
3. **Git-Sync Tags**: Added `git-sync` tags to all dashboards and datasources for automated synchronization

### Dashboard Structure
Dashboards now have the correct structure with title at root level:
```json
{
  "id": null,
  "uid": "dashboard-uid",
  "title": "Dashboard Title",
  "tags": ["tag1", "tag2", "git-sync"],
  ...
}
```

### Datasources
Datasources are now properly configured in `provisioning/datasources/datasources.yaml` with:
- Prometheus connection to `kube-prometheus-stack-prometheus:9090`
- Loki connection to `loki:3100`
- Proper trace integration between datasources
- `git-sync` tags for automated management

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

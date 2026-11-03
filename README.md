# Observability Dashboards

Grafana dashboards for the NX platform. A CronJob in each cluster's `observability`
namespace (image `ghcr.io/nvision-x/grafana-dashboards-sync`) clones this repo every
minute and turns every `dashboards/**/*.json` into one ConfigMap that Grafana's sidecar
loads. Nothing else in the repo is synced.

| Grafana | Renders branch |
|---|---|
| dev (`nx-development`) | `development` (`dashboardSync.branch` in `nxdeployment-development-env`) |
| every other cluster, and the central (mimir) Grafana | `main` |

## Two kinds of board, one tree

- **Per-cluster boards**: one board per component view (`dashboards/applications/V2/...`
  and the V1-era boards at the top of `dashboards/`). These are the ones you edit.
- **Consolidated boards** for the central Grafana: Connectors Detail, Services Detail,
  Infrastructure Overview, Content Service (Legacy), and the V2 section of Applications
  Overview. These are **generated** from the per-cluster boards by `tools/build-detail.py`
  (sources listed in `tools/detail-boards.json`). Never edit them by hand.

Both kinds sync to every Grafana.

## Making a change

```bash
git switch development && git pull
git switch -c feat/<what>
# edit or add a per-cluster board under dashboards/
python3 tools/build-detail.py          # regenerates the consolidated boards, validates everything
git add dashboards tools && git commit
# open the PR against development; check it on dev Grafana; promote development -> main
```

CI (`.github/workflows/dashboards-check.yml`) runs `python3 tools/build-detail.py --check`
and fails if a generated board is stale or a board breaks a shared rule: invalid JSON,
duplicate uid or panel id, overlapping panels, `label=".*"` (use `=~`), undefined
variables, a datasource variable that is not the hidden default one, a file over the 1 MiB
ConfigMap limit, or a path that cannot be a ConfigMap name (no underscores).

To add a new board to a consolidated view, add its path to the right section of
`tools/detail-boards.json` and rebuild.

## Branch rule

Changes land on `development` first and reach `main` by promotion. Do not restructure
boards (move, merge, rename, delete) directly on `main`: that is how the two branches
drifted apart in September 2026. A hotfix made on `main` is merged back into
`development` the same day.

See `CLAUDE.md` for the board conventions (variables, job labels, panel types, metric
naming) and the full sync mechanism.

## Post Deployment Test

1. Render pass. Open the dashboard with its default variables and default time range. Then:

   Expand every collapsed row.
   Log any panel showing an error triangle, “No data”, “Datasource not found”.
   For every “No data”, decide whether it’s legitimate (for example, no GPUs or no traffic) or a query defect. Open the panel in Explore and drop filters until data appears to find which one is wrong.

2. Variable pass. For each variable:

   Confirm the dropdown populates.
   Change its value and confirm the panels actually change.
   For multi-value variables, test a single value, several values, and All.
   For chained variables, confirm that changing the parent refreshes the child.

3. Accuracy pass. Pick 2–3 headline stats per dashboard, such as pod counts, error rates and totals. Run the same query in Explore, or check kubectl for counts, and confirm the numbers match. Also confirm units: bytes vs bits, seconds vs ms, percent as 0–1 vs 0–100.

   Log every finding with: dashboard UID, row, panel title, the variable values used, expected vs actual, and severity (wrong data > broken > cosmetic).

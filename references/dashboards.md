# Kibana dashboards

**Before writing or editing any dashboard / Lens / visualization**, load the Elastic skill **`kibana-dashboards`** (`elastic/agent-skills` → `skills/kibana/kibana-dashboards`). Use it for Dashboards/Visualizations API shape, dataset type (`data_view` vs ES|QL), and panel JSON. This file only adds **Fleet package** constraints (time windows, data view, ship gate).

Dashboards should match **data volume and product type**. This skill generates firewall syslog, HTTP APIs, metrics, and everything in between — do not force a SOC-syslog layout on a metrics package.

## Time picker (defaults, not a single hard number)

Always set `timeRestore: true` and an explicit `timeFrom` / `timeTo`. Unset dashboards inherit whatever the analyst last used (often 24h/7d).

| Data class | Suggested `timeFrom` | Refresh |
| --- | --- | --- |
| High-volume events (syslog, firewall, auth, PAM, WAF) | `now-1h` | 30s is reasonable; 5s is too hot |
| Metrics / low-volume / copied official dashboards | `now-24h` (or the source package) is fine | 1m or paused is fine |
| User-specified window | Honor it | Honor it |

Do not silently ship `now-7d` / `now-30d` as a packaged default. `now-24h` is **not** an automatic fail — it is the wrong default for hot event streams, and a normal default for many metrics UIs.

```json
"timeRestore": true,
"timeFrom": "now-1h",
"timeTo": "now"
```

Example above is the high-volume-events starting point. Change it when the data is not high-volume events.

## Visualizations, Lens, maps, Discover searches

- Time axes follow the dashboard picker. Do not pin a conflicting `timeRange` inside visState unless the panel truly needs its own window.
- Saved searches: filter `data_stream.dataset`; leave time to Discover/dashboard.
- Date histograms: `interval: auto`.

## Queries and index scope

- After writing `kibana/`, run `scripts/production_ship_gate.py <package-dir>`. FAIL = cluster-killing ES|QL, not a wrong time picker.
- Details: `kibana-queries.md`.
- Panels query the integration data view (`logs-<package>.<ds>-*` or `metrics-…`), not `logs-*` / `*`.
- Do not hardcode lab IPs or cluster URLs in filters. Use fields the pipeline actually sets.
- Overview: volume over time plus the top dimensions **this dataset has** (action, status, `source.ip`, `service.name`, …). Skip IP panels on a metrics-only stream.

## Detection rules

Only when the package is a detection/security deliverable. Time windows: `detection-rules.md`.

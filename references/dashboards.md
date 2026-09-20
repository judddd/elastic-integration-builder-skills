# Kibana dashboards (production defaults)

Generated dashboards are **SOC production assets**, not lab toys. High-volume syslog/firewall/PAM streams cannot open on a 24-hour window: the first load scans too much data, panels time out, and the cluster is taxed every auto-refresh.

## Dashboard time picker (hard rule)

Every `kibana/dashboard/*.json` **must** set:

```json
"timeRestore": true,
"timeFrom": "now-1h",
"timeTo": "now",
"refreshInterval": { "pause": false, "value": 30000 }
```

| Field | Production value | Why |
| --- | --- | --- |
| `timeFrom` | `now-1h` | Default investigation window. **Never** `now-24h` / `now-7d`. |
| `timeTo` | `now` | Live tail. |
| `timeRestore` | `true` | Opening the dashboard applies the packaged range instead of the analyst’s last global picker (often 24h/7d). |
| `refreshInterval.value` | `30000` (30s) | SOC live view. Do not use 5s (hot-spotting ES) or omit refresh on an ops overview. Analysts can pause. |

Do **not** leave `timeFrom` unset. Unset dashboards inherit Kibana’s UI default, which is commonly Last 24 hours.

If the user explicitly asks for a different default (e.g. 15m for ultra-hot firewall, 4h for sparse audit), honor that — never silently fall back to 24h.

## Visualizations, Lens, maps, Discover searches

- Date histograms, Lens time axes, TSVB, Maps time: **follow the dashboard time picker**. Do not pin `timeRange: { from: "now-24h" }` inside `visState` / Lens `query` / `searchSourceJSON`.
- If a Kibana export still requires a `timeRange` object on an aggregation, use `"from": "now-1h", "to": "now"` — same as the dashboard.
- Saved searches (`kibana/search/*.json`): **no** embedded absolute/`now-24h` range. Filters = `data_stream.dataset` (and vendor fields). Time comes from the dashboard or Discover picker.
- `interval: auto` (or Lens equivalent) for date histograms so a 1h window buckets reasonably.

## Queries and index scope

- Queries and index scope: see **`kibana-queries.md`** (mandatory for any ES|QL panel). Narrow `FROM`, time-bind `?_tstart`/`?_tend`, never `VALUES` of full events.
- Panels query `logs-<package>.<data_stream>-*` (or the integration data view), never `logs-*` / `*`.
- Never hardcode lab IPs, hostnames, or cluster URLs in Kuery/Lens filters. Use ECS fields from the vendor stream (`observer.ip`, `source.ip`, …).
- Overview dashboard: volume over last **1h**, top action/severity, top `source.ip` / `destination.ip` when present, plus a Discover search panel.

## Detection rules (related time windows)

Dashboards default to 1h; detection lookbacks must also be production-sized. See `detection-rules.md`.

- High-volume streams: rule `from` typically `now-70m`–`now-2h`, `interval` `5m` (or similar). **Do not** ship `from: now-24h` query/ES|QL rules that rescan a day of syslog every interval.
- ES|QL `| WHERE @timestamp > NOW() - N` must match `from` (not 24 hours unless the user requires a slow-burn correlation).

## Checklist before zip

```bash
# Must be empty (except an explicit user-requested longer window)
rg -n 'now-24h|now-7d|now-30d' packages/<name>/kibana packages/<name>/docs
```

Fail the build if a dashboard still has `timeFrom: now-24h`.

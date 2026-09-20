# Dashboard / Discover queries

Packaged Kibana queries run on every dashboard open (and on auto-refresh). They must not hang Elasticsearch. This applies to **any** integration — logs, metrics, traces, HTTP APIs — not only syslog.

`scripts/production_ship_gate.py` fails **query-shape** bombs. It does not dictate a vendor, a 1-hour picker, or a PAM correlation pattern.

## Always forbidden in packaged ES|QL

| Anti-pattern | Why |
| --- | --- |
| `VALUES(row)` / `VALUES(CONCAT(...))` then `MV_EXPAND` | `VALUES` is unbounded; packing full events into a bucket circuit-breaks the query |
| `METADATA _id` to reconstruct documents | Same as dumping the hit list through an aggregation |
| `FROM logs-*` / `FROM metrics-*` / `FROM *` | Opens every matching data stream in the cluster |
| One `FROM` listing many unrelated stream families | Scans shards the panel does not need — split into separate searches |
| `KEEP *` before `STATS` / joins | Carries full events into the aggregation |

`VALUES()` is fine for **small dimensions** (`event.action`, `user.name`, a few IPs). It is not a way to stash documents.

## Default ES|QL habits (any correlation / agg panel)

1. Bind time: `@timestamp >= ?_tstart AND @timestamp <= ?_tend` on every `FROM`, including subqueries.
2. `FROM` the integration stream (`logs-<pkg>.<ds>-*` or `metrics-<pkg>.<ds>-*`), not a cluster-wide wildcard.
3. Filter on cheap fields (`event.action`, `event.dataset`, `event.outcome`, `service.name`, …) **before** `STATS`.
4. `KEEP` only fields needed for the join/agg, then aggregate.
5. Cross-stream joins: `IN` / `NOT IN` subqueries that `KEEP` **one** join key, not a full event dump.
6. `STATS` with `COUNT` / `COUNT_DISTINCT` / small `VALUES`, preferably bucketed with `DATE_TRUNC` when the result is a time chart.
7. Prefer Kuery + Lens for simple tables. Use ES|QL when you actually need correlation or a computed agg.

## Kuery / Lens

- Filter `data_stream.dataset` (and a subset field when the panel is not the whole stream).
- Terms size 10–20, not 1000.
- Date histogram: `interval: auto`. Follow the dashboard time picker; do not pin a surprise `timeRange` inside visState.

## Case study (do not copy as the only template)

JumpServer **0.1.31** froze production with one Discover panel: four fat auth streams in one `FROM`, `EVAL row = CONCAT(...)`, `STATS VALUES(row)`, `MV_EXPAND`. The safe rewrite (0.1.45) was: one OS stream per search, early `KEEP`, `NOT IN (KEEP observer.ip)`, `DATE_TRUNC` + `COUNT_DISTINCT`. Use that **shape** when you are doing a similar anti-join — not as the dashboard for every package.

Do not upload over an environment the user said is already optimized.

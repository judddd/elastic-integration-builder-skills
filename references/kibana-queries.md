# Dashboard / Discover queries (production)

Kibana **saved searches, dashboard ES|QL panels, and Lens/Kuery filters** run on every dashboard open and every 30s refresh (see `dashboards.md`). They must survive a production SOC: tens of millions of auth/syslog docs in the last hour.

The JumpServer **0.1.31** “疑似绕过堡垒机 SSH” panel froze production. **0.1.45** (user-optimized) is the pattern to copy. Do **not** ship 0.1.31-style queries again.

## What froze production (forbidden)

0.1.31 ES|QL did all of the following in **one** Discover panel:

```esql
FROM logs-system.auth-*, logs-system.security-*, logs-windows.security-*, logs-jumpserver.log-* METADATA _id
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
| WHERE (... ssh_login OR logged-in ...) OR (jumpserver.log AND observer.ip IS NOT NULL)
| EVAL row = CONCAT(ts, id, host, user, ip)
| STATS ... events = VALUES(row) WHERE is_auth BY login_source_ip
| MV_EXPAND events
| DISSECT events ...
```

Why it dies:

| Anti-pattern | Effect on a hot cluster |
| --- | --- |
| `FROM` four fat data-stream families in one query (Linux auth + Windows security + PAM) | Opens every auth/security shard even if the analyst only needed Linux SSH |
| `OR (dataset == jumpserver.log AND observer.ip IS NOT NULL)` with **no** `event.action` | Scans **all** PAM syslog (commands, FTP, login, session…) just to collect egress IPs |
| `STATS … VALUES(row)` of **every matching event**, then `MV_EXPAND` | Circuit-breaker / Kibana hang: VALUES is unbounded; one source IP can carry tens of thousands of concatenated rows |
| `METADATA _id` + `CONCAT` to reconstruct documents | Same as dumping the hit list through an aggregation |
| Mixing Linux `ssh_login` and Windows `logged-in` in one STATS | Cartesian / extra scan; split OS instead |

**Never** use `VALUES()` to stash full event payloads. `VALUES` is only for **small dimensions** (user.name, event.action, a few IPs).

## Required ES|QL shape (0.1.45)

Dashboard time picker is last **1 hour**. Bind it immediately. Narrow `FROM`. Filter. `KEEP`. Then a **cheap** anti-join. Then **bucketed** `STATS`.

Linux bypass (pattern):

```esql
FROM logs-system.auth-*
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
    AND event.action == "ssh_login"
    AND COALESCE(event.outcome, "success") == "success"
    AND source.ip IS NOT NULL
    AND NOT ENDS_WITH(COALESCE(user.name, ""), "$")
| KEEP @timestamp, event.action, host.name, user.name, source.ip, source.port
| WHERE source.ip NOT IN (
    FROM logs-jumpserver.log-*
    | WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
        AND observer.ip IS NOT NULL
    | KEEP observer.ip
  )
| EVAL login_id = COALESCE(TO_STRING(source.port), TO_STRING(@timestamp))
| STATS login_count = COUNT_DISTINCT(login_id),
        login_type = VALUES(event.action)
    BY ts = DATE_TRUNC(30 seconds, @timestamp), host.name, user.name, source.ip
| RENAME ts AS @timestamp
| KEEP @timestamp, host.name, user.name, source.ip, login_type, login_count
| SORT @timestamp DESC
```

Windows RDP bypass: **separate** saved search on `logs-system.security-*` only, `event.action == "logged-in"` and `winlog.logon.type IN ("RemoteInteractive", "10")`. Do not union Windows into the Linux query.

Via-bastion correlation: still time-bound `IN ( … KEEP observer.ip )`, `KEEP` before join, `DATE_TRUNC(2 minutes, …)` + `COUNT_DISTINCT`, `VALUES` only for employee / client_ip / host.name — **not** every raw document.

Always:

1. `@timestamp >= ?_tstart AND @timestamp <= ?_tend` on **every** `FROM`, including subqueries.
2. One primary data stream per panel when possible (`logs-system.auth-*`, not `logs-*` / `logs-system.*`).
3. Equality filters on `event.action` / `data_stream.dataset` / `event.outcome` **before** STATS.
4. `KEEP` only fields needed for the join/agg **before** STATS.
5. Correlate with `IN` / `NOT IN` subqueries that `KEEP` a **single** field (e.g. `observer.ip`), never a full event dump.
6. `STATS` by `DATE_TRUNC(30 seconds|2 minutes, @timestamp)` plus join keys; metrics = `COUNT` / `COUNT_DISTINCT` / small `VALUES`.
7. Split Linux vs Windows vs other products into **separate** searches; dashboard embeds both.
8. Filter machine accounts (`user.name` ending `$`) when using Windows/Linux auth.
9. Prefer Kuery `data_stream.dataset : "pkg.ds" and event.action : "…"` for simple tables. Use ES|QL only when a cross-stream correlation is required — and then follow this shape.

## Kuery / Lens / visualizations

- Filter `data_stream.dataset` (and `event.action` when the panel is a subset). Never `logs-*` with a weak Kuery.
- No `NOT _exists_ : field` over huge indices as the only clause.
- Terms aggs: size 10–20, not 1000.
- Date histogram: `interval: auto`, no pinned 24h `timeRange` (`dashboards.md`).

## Checklist

Before zip, review every `kibana/search/*.json` and ES|QL inside dashboards:

```bash
rg -n 'VALUES\(row\)|MV_EXPAND events|METADATA _id|FROM logs-\*' packages/<name>/kibana
```

Any hit is a **ship blocker** unless the user has proven it on production volume.

Do not “fix” a customer cluster that already runs an optimized package (e.g. JumpServer 0.1.45). Change the **next** package you generate. Never upload, overwrite, or reinstall over an environment the user said is already optimized.

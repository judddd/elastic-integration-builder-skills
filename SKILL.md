---
name: elastic-integration-builder
description: >
  Analyze raw vendor logs/metrics/files and either reuse an existing Elastic
  integration or scaffold a complete custom Fleet integration package (manifest,
  data streams, agent inputs, ingest pipelines, ECS field mappings, sample
  events, and Kibana dashboards). Use whenever the user provides sample
  telemetry, asks to "做一个 integration / 适配 ECS / 写 ingest pipeline /
  custom TCP syslog / Fleet package", mentions unsupported Chinese or niche
  network/security appliances, wants to map fields to ECS, or references
  elastic-package / build-new-integration. Prefer this skill over ad-hoc Logstash
  or one-off ingest scripts when the deliverable should be an installable
  Elastic integration folder.
---

# Elastic Integration Builder

Turn raw sample data into a **Fleet-installable Elastic integration package** that complies with ECS and the official package layout.

Canonical how-to (read when scaffolding or stuck):  
https://www.elastic.co/docs/extend/integrations/build-new-integration

ECS field names/types: match the **target Stack** via [elastic/ecs](https://github.com/elastic/ecs) + [ECS reference](https://www.elastic.co/docs/reference/ecs). Details: `references/ecs-mapping.md`.

## Goals

1. **Match first**: decide whether an official/community integration already fits.
2. **Build only when needed**: if nothing fits, generate a full custom package folder.
3. **ECS by default**: every exported field is either an ECS field (correct type) or a documented custom field under the package dataset namespace.
4. **Production defaults**: dashboards, searches, and detection lookbacks are sized for a live SOC (default dashboard range **last 1 hour**, not 24h). Lab-only windows, `localhost:514` listeners, and hardcoded lab IPs are not acceptable.
5. **Runnable package**: manifests, streams, pipelines, fields, samples, dashboards/docs — not just a pipeline snippet.

## Inputs the user may give

- Raw log lines, PCAP-derived text, JSON/NDJSON exports, CSV, screenshot of vendor UI, syslog samples
- Vendor name / product / firmware version
- Preferred collection: Elastic Agent (Fleet), standalone Agent, or Logstash → ES (still model the **integration** package for Fleet when possible)
- Target Elastic Stack version (default: match the user’s cluster, else `^8.14.0 || ^9.0.0`)

Ask only for missing critical pieces (sample lines + vendor/product). Do not block on perfect docs.

## Workflow (always follow in order)

### 1) Identify the signal

From samples, record:

| Question | Why it matters |
| --- | --- |
| One line vs multiline? JSON / CEF / LEEF / key=value / syslog / CSV? | Chooses grok/dissect/json/cef processors and input framing |
| Transport today (file / syslog UDP|TCP / HTTP API / JDBC / cloud)? | Chooses Agent input type |
| Security, network, observability, or infra? | Categories + dashboard templates |
| Stable identifiers (host, src/dst IP, user, action, severity)? | ECS mapping priorities |

Save 3–20 representative lines into the package as `_dev/deploy/...` or `data_stream/<ds>/_dev/test/pipeline/` fixtures later.

### 2) Search existing integrations before inventing

Check these sources (in parallel when tools allow):

1. Elastic Integrations catalog / Kibana **Integrations** UI  
2. GitHub [`elastic/integrations`](https://github.com/elastic/integrations) under `packages/`  
3. Elastic docs search for the vendor/product name  
4. Adjacent formats: **CEF**, **LEEF**, **syslog**, **Custom Logs / Custom API**, **network_traffic**, **Suricata/Zeek** if the device can emit a standard format

Decision rules:

- **Exact or close package exists** → recommend installing/configuring it; only add a thin custom package if the user needs vendor-specific enrichments the official package cannot cover.
- **Device can emit CEF/LEEF/standard syslog** → prefer official **CEF** / syslog-oriented packages + vendor config guidance over a greenfield parser.
- **No package and proprietary text/JSON** → proceed to custom package (step 3).

Write a short **Match Report** to the user before generating files:

```markdown
## Match Report
- Vendor/product: ...
- Format: ...
- Recommended path: reuse `fortinet_fortigate` | reuse `cef` | **create custom `acme_fw`**
- Why: ...
- Gaps if reusing: ...
```

### 3) Scaffold a custom package (official layout)

Prefer the CLI when available:

```bash
elastic-package create package
elastic-package create data-stream
```

If CLI is unavailable, **manually create the same tree** (see `references/package-layout.md`).

Package naming:

- `name`: lowercase snake (`hillstone_ngfw`, `vendor_product`)
- `data_stream`: short (`log`, `threat`, `traffic`, `audit`)
- Final dataset: `<package>.<data_stream>` → data stream `logs-<package>.<data_stream>-*`

Always set ECS import for mappings when using elastic-package build (tag ≈ target Stack):

```yaml
# _dev/build/build.yml
dependencies:
  ecs:
    reference: git@v8.11.0   # replace with Stack-aligned ECS tag
    import_mappings: true
```

Choose Elasticsearch field types from the same ECS tag (`generated/ecs/ecs_flat.yml`). See `references/ecs-mapping.md`.

### 4) Choose Agent input(s)

Map collection reality → input (details: `references/input-patterns.md`):

| Situation | Typical input |
| --- | --- |
| Device pushes syslog | `tcp` / `udp` / `syslog` |
| Log files on disk | `logfile` / `filestream` |
| Vendor HTTP/REST API | `httpjson` / `cel` |
| Windows event channel | `winlog` |
| Cloud object storage | `aws-s3` / `azure-blob-storage` / `gcs` |
| Only Logstash available short-term | Still ship the integration package for Agent; optionally note a Logstash `elasticsearch` output targeting `logs-<dataset>-*` **with the same pipeline** |

For listen inputs, document listen address, port, SSL, framing (`rfc6587`, newline), and vendor-side syslog config in README.

**Stream template hard rule (`*.yml.hbs`):** never emit an `add_fields` processor whose `fields:` map is empty when optional UI vars are blank. Filebeat rejects that at startup (`missing required field accessing '...add_fields.fields'`) and the whole TCP/UDP input stays **FAILED** — Fleet shows the Agent as degraded and **no logs arrive**. Always keep at least one constant under `fields`, or wrap the whole `add_fields` block in `{{#if var}}` so it is omitted when unused. See `references/input-patterns.md`.

### 5) Ingest pipelines → ECS

Edit `data_stream/<ds>/elasticsearch/ingest_pipeline/default.yml`.

Required habits:

1. Preserve raw payload: rename `message` → `event.original` (or copy) before destructive parsing.
2. Parse → normalize → ECS set → cleanup temps.
3. Set baseline ECS: `@timestamp`, `event.dataset`, `event.module`, `data_stream.*`, `observer.*` / `host.*` as applicable, `event.kind` / `category` / `type` / `outcome` when knowable.
4. Prefer `dissect` for fixed layouts; `grok` for variable; `json` for JSON; community ID / geoip only when useful.
5. Convert types explicitly (`ip`, `long`, `boolean`) to match ECS.
6. Namespace leftover vendor fields under `<package>.*` (declared in `fields/fields.yml`), not as random root fields.
7. Always define pipeline-level `on_failure` writing `error.message`.

Validate with `_ingest/pipeline/_simulate` using the user’s samples before declaring done.

### 6) Field mappings

- ECS fields: rely on imported ECS mappings + explicit entries in `fields/base-fields.yml` / `fields/ecs.yml` as the package format requires.
- Custom fields: `data_stream/<ds>/fields/fields.yml` with correct types.
- Never map an ECS `ip` field as `keyword`/`text`. Cross-check types against the chosen ECS tag.

**`external: ecs` hard rule:** `external: ecs` is only resolved by `elastic-package build`. A rsync/zip fallback leaves those entries unresolved; Fleet then maps them as `keyword` (`source.ip` / `destination.ip` become keyword, Discover shows a type-conflict warning on `logs-*`). 要么 zip 改成 elastic-package build，要么所有 ECS 字段都带明确 type，不能再只写 external: ecs。

When using the rsync zip fallback (or any path that is not `elastic-package build`), every ECS field in `fields/ecs.yml` must include an explicit `type:` (for example `type: ip` on `source.ip`). `external: ecs` may remain as documentation, but it is not sufficient by itself.

### 7) Dashboards and content

Under `kibana/` (details: `references/dashboards.md`):

- At least one **overview** dashboard (volume over time, top actions/severities, top source.ip / destination.ip when present).
- One **Discover search** saved object filtered to `data_stream.dataset: "<package>.<ds>"`.
- Optional Lens panels; keep panels bound to the integration’s data view / index pattern `logs-<package>.<ds>-*`.
- **Time range hard rule:** every dashboard sets `timeRestore: true`, `timeFrom: now-1h`, `timeTo: now`, `refreshInterval: { pause: false, value: 30000 }`. **Never** ship `now-24h` (Kibana’s editor default). A 24h window on production syslog/firewall is too heavy and is not an acceptable default.
- **Query hard rule:** every dashboard panel / saved search query must be production-safe. See `references/kibana-queries.md`. Do **not** ship ES|QL that `FROM`s multiple fat streams, `STATS VALUES(entire row)`, then `MV_EXPAND` (JumpServer 0.1.31 SSH-bypass froze production). Pattern: time-bind `?_tstart`/`?_tend`, narrow `FROM`, filter `event.action`, `KEEP` early, `IN`/`NOT IN` subquery with `KEEP` one field, `DATE_TRUNC` + `COUNT_DISTINCT`. Split Linux vs Windows into separate searches. Simple tables stay Kuery on `data_stream.dataset` + `event.action`.
- Visualizations / Lens / saved searches must **not** pin `timeRange` / Kuery time to 24h; they follow the dashboard picker. If an export still embeds `timeRange`, use `now-1h`–`now`.
- **Detection rules (SIEM):** see `references/detection-rules.md`. Always ship `docs/detection-rules.ndjson` (one detection-engine rule per line). Kibana **Rules → 导入规则** only accepts ndjson — Fleet `kibana/security_rule/*.json` saved objects will not import there and do not auto-install into the detection engine. ES|QL rules must `KEEP` a full ECS investigation set (`host.name`, `user.name`, `source.ip`, `event.action`, `event.count`, …), never `join_ip` / `auth_cnt`. `note` (调查指南) and `description` must be in the same language as the dashboards (Chinese for CN packages). Pin `related_integrations` to a wide range (`^0.1.0`), not the current patch. Rule `from` defaults to ~1–2h, not 24h.

Export from a real Kibana when possible (`elastic-package export` / Saved Objects). After export, **rewrite** `timeFrom` to `now-1h` if Kibana saved Last 24 hours. Keep IDs stable and references consistent.

### 8) Tests, docs, build **and Fleet zip (required)**

Minimum bar:

```bash
elastic-package check    # format + lint + build when tooling exists
```

Also provide:

- `data_stream/<ds>/_dev/test/pipeline/*.json` — pipeline unit tests from real samples  
- `sample_event.json` — one golden ECS document  
- `_dev/build/docs/README.md` template → build to `docs/README.md`  
- `changelog.yml` entry for the version  
- If the package ships SIEM rules: `docs/detection-rules.ndjson` **inside** the Fleet zip (not a second complete zip)  

**Always produce a Fleet upload `.zip` before finishing.** Kibana **Integrations → Upload integration** only accepts a zip (not a bare folder).

Preferred (when `elastic-package` is installed):

```bash
cd packages/<package-name>
elastic-package build
# Artifact is typically under build/packages/<name>-<version>.zip
```

Fallback (no CLI — **must still ship a zip**):

要么 zip 改成 elastic-package build，要么所有 ECS 字段都带明确 type，不能再只写 external: ecs。 Before rsync/zip, confirm every `fields/ecs.yml` entry has `type:` — otherwise Fleet will install `source.ip` as `keyword`.

```bash
# From repo: packages/<name>/ with manifest.yml name + version
NAME=$(python3 -c "import yaml;print(yaml.safe_load(open('manifest.yml'))['name'])")
VER=$(python3 -c "import yaml;print(yaml.safe_load(open('manifest.yml'))['version'])")
OUT=../build
STAGE="$OUT/${NAME}-${VER}"
rm -rf "$STAGE" "$OUT/${NAME}-${VER}.zip"
mkdir -p "$STAGE"
rsync -a --exclude '.DS_Store' ./ "$STAGE/"
( cd "$OUT" && zip -qr "${NAME}-${VER}.zip" "${NAME}-${VER}" )
# Upload: $OUT/${NAME}-${VER}.zip
```

Zip layout **must** match EPR: root entry `<name>-<version>/manifest.yml` (not loose files at zip root).

If the package has `scripts/build_fleet_zip.sh`, run that and give the user the resulting path.

### 9) Deliverable

Output a **complete folder** **and** the Fleet `.zip`:

```text
packages/
├── <package-name>/          # source tree
│   ├── manifest.yml
│   ├── changelog.yml
│   ├── docs/
│   ├── kibana/
│   ├── data_stream/<ds>/
│   └── _dev/...
└── build/
    └── <package-name>-<version>.zip   # 唯一交付：Fleet 上传；SIEM ndjson 在包内 docs/
```

Tell the user: Fleet → Integrations → **Upload integration** → select the `.zip`. If there are SIEM rules, unzip that same archive and **Rules → 导入规则** → `docs/detection-rules.ndjson` (not `kibana/security_rule/*.json`). Then add the integration to an Agent policy.

## Match Report + build log (required output style)

When finishing, always summarize:

1. Match Report (reuse vs create)  
2. Package path on disk  
3. **Fleet upload `.zip` absolute path** (mandatory; ndjson is inside the zip at `docs/detection-rules.ndjson` when SIEM rules exist)  
4. Data stream name(s) and input type(s)  
5. ECS fields populated (bullet list of the important ones)  
6. How to test: simulate pipeline + expected Discover query  
7. Open follow-ups (TLS syslog, multiline, missing fields)

## Anti-patterns

- Shipping only a Logstash conf and calling it an “integration” when the user asked for Fleet/integration.  
- Finishing with only a source folder and **no** `<name>-<version>.zip` for Fleet upload.  
- Zipping loose files at the archive root (must be `<name>-<version>/…`).  
- Never hardcode customer/lab IPs in Discover or dashboards; use fields from the vendor logs (e.g. `observer.ip` from syslog source) and ES|QL rules for cross-index joins.
- ES|QL Discover/dashboard queries that `FROM logs-system.auth-*, logs-windows.security-*, logs-*.log-*`, `STATS VALUES(concatenated event)`, then `MV_EXPAND` (JumpServer 0.1.31 SSH bypass). That pattern hung production. Follow `references/kibana-queries.md` (0.1.45): one stream per panel, `?_tstart`/`?_tend`, early `KEEP`, `NOT IN (KEEP observer.ip)`, `DATE_TRUNC` + `COUNT_DISTINCT`. Never reconstruct hit lists through `VALUES`.
- Shipping dashboards with `timeFrom: now-24h` (or unset, which inherits Kibana Last 24 hours). Production default is **last 1 hour** (`now-1h` + `timeRestore: true` + 30s refresh). Same for vis/Lens `timeRange` and detection `from: now-24h`.
- Emitting `add_fields` with an empty `fields:` map from optional Handlebars vars (Agent input fails permanently; looks like “syslog not arriving”).  
- Defaulting listen address to **localhost** or port **514** — production devices send syslog to the Agent’s real bind; 514 is often taken. Default `0.0.0.0` and a high port (e.g. 5514).
- Defaulting listen port to **514** without checking the Agent host — 514 is often taken by rsyslog / otel / another beat; prefer documenting a high port (e.g. 5514) or verifying bind success in Fleet Agent components.  
- Assuming vendor syslog supports TCP when many products (e.g. JumpServer) are **UDP-only**; match the vendor protocol in both the package input and the device `SYSLOG_ADDR`.  
- Mapping everything as `keyword` / leaving `source.ip` as text.  
- Shipping a rsync/zip with `external: ecs` and no explicit `type:` — Fleet will not import ECS mappings; IP fields become `keyword` and conflict with other `logs-*`. 要么 zip 改成 elastic-package build，要么所有 ECS 字段都带明确 type，不能再只写 external: ecs。  
- Dropping `event.original`.  
- Hard-coding a single Chinese firewall vendor as the only path — treat vendor appliances as **one class** of custom syslog/API sources among many (OT, WAF, mail gateway, PAM, etc.).  
- Copying an official package’s copyrighted dashboards wholesale; use as structural reference and build original content.  
- Putting SIEM rules only in `kibana/security_rule/*.json` and telling the user to import them under **Rules → 导入规则**. That UI only accepts detection-engine **ndjson**. Put `docs/detection-rules.ndjson` **inside** the Fleet zip. Those Fleet JSON files also do **not** appear under **添加 Elastic 规则**.  
- Shipping a second `*-complete.zip` or a sidecar ndjson next to the Fleet zip. One `<name>-<version>.zip` is the deliverable.  
- Pinning `related_integrations[].version` to the current package patch (`^0.1.28`). Alerts then show “版本不匹配” when Fleet is one version behind. Use a wide range (`^0.1.0`).  
- ES|QL detection rules `KEEP host_name` / `join_ip` / `auth_cnt`. Highlighted fields then show one opaque counter; Host/User/IP stay empty. KEEP ECS names and a full investigation set.  
- English-only `note` on a Chinese SOC package. The Alerts flyout label is 调查指南 — write the guide in Chinese (alert meaning, field glossary, Discover follow-ups).  
- Putting Kibana UI-export `migrationVersion.visualization: "8.8.0"` into a Fleet zip. Fleet’s package importer last knows legacy visualization **8.5.0**; install fails with `belongs to a more recent version of Kibana [8.8.0] when the last known version is [8.5.0]` even on Stack 9.x. Use `typeMigrationVersion` (visualization `8.5.0`, dashboard `10.2.0`) and omit `migrationVersion`, matching bundled packages. This is **not** an Elasticsearch version mismatch.

## References (read on demand)

| File | When |
| --- | --- |
| `references/official-build.md` | Scaffolding, elastic-package commands, doc links |
| `references/package-layout.md` | Exact file tree and manifest snippets |
| `references/ecs-mapping.md` | ECS version selection + field typing rules |
| `references/dashboards.md` | Dashboard time range, refresh, vis/Lens time (production 1h) |
| `references/kibana-queries.md` | Production-safe Kuery/ES|QL for dashboard panels (no VALUES-row bombs) |
| `references/detection-rules.md` | SIEM rules: Fleet security-rule vs Rules-import ndjson |

## Quick start for this skill’s operator

1. Obtain samples → Match Report.  
2. If create: scaffold package → input → pipeline → fields → sample_event → kibana → check.  
3. **Build the Fleet `.zip`** (`elastic-package build` or `_dev/build_fleet_zip.sh`) and give the user that **one** zip path. SIEM ndjson belongs inside the zip (`docs/detection-rules.ndjson`), not a complete sidecar.  
4. Hand the folder **and zip** to the user; do not stop at a pipeline paste.

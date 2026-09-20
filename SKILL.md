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
  Elastic integration folder. Before writing Kibana dashboards or Lens, load
  `kibana-dashboards`. Before writing alerting or SIEM/security rules, load
  `kibana-alerting-rules` (and this skill's `references/detection-rules.md` for
  packaged detection-engine ndjson). Before zip, run scripts/production_ship_gate.py
  (fails cluster-killing ES|QL: VALUES of full events, FROM logs-*/metrics-*/*,
  METADATA _id). Not syslog-only.
---

# Elastic Integration Builder

Turn raw sample data into a **Fleet-installable Elastic integration package** that complies with ECS and the official package layout.

Canonical how-to (read when scaffolding or stuck):  
https://www.elastic.co/docs/extend/integrations/build-new-integration

ECS field names/types: match the **target Stack** via [elastic/ecs](https://github.com/elastic/ecs) + [ECS reference](https://www.elastic.co/docs/reference/ecs). Details: `references/ecs-mapping.md`.

## Required sibling skills (load before writing Kibana content)

This skill owns the **Fleet package** (layout, ECS, pipelines, zip, query ship gate). Official Elastic skills own **how to author Kibana objects**. Do not invent dashboard JSON or rule payloads from memory when those skills are available.

Load them by name (`kibana-dashboards`, `kibana-alerting-rules`) from the Elastic agent-skills set / Cursor Elastic plugin. Read each `SKILL.md` **before** creating or editing the corresponding artifacts. If a skill is missing, stop and tell the user to install [elastic/agent-skills](https://github.com/elastic/agent-skills/tree/main/skills/kibana) — do not skip the load and guess APIs.

| You are about to… | Load first | Then still follow |
| --- | --- | --- |
| Create/update dashboards, Lens, visualizations, `kibana/dashboard`, `kibana/visualization` | **`kibana-dashboards`** | `references/dashboards.md`, `references/kibana-queries.md`, `production_ship_gate.py` |
| Create/update Kibana **alerting** rules (threshold, es-query, metric) | **`kibana-alerting-rules`** | Package docs if the rule is shipped with the integration |
| Create/update **SIEM / security detection** rules (`security-rule`, detection-engine ndjson) | **`kibana-alerting-rules`** for rule lifecycle/params habits, then this skill's packaging rules | `references/detection-rules.md` (Fleet JSON ≠ Rules-import ndjson) |

Do not substitute one for the other: `kibana-dashboards` does not create rules; `kibana-alerting-rules` does not create Lens panels. After those skills produce valid bodies, **adapt** them into the package tree (`kibana/…`, `docs/detection-rules.ndjson`) — do not finish with only a live Kibana PUT if the user asked for a Fleet zip.

## Goals

1. **Match first**: decide whether an official/community integration already fits.
2. **Build only when needed**: if nothing fits, generate a full custom package folder.
3. **ECS by default**: every exported field is either an ECS field (correct type) or a documented custom field under the package dataset namespace.
4. **Queries must not hang the cluster**: packaged ES|QL/Kuery is a ship blocker equal to ECS. Dashboard time windows follow data volume (see `dashboards.md`) — this is not a syslog-only skill.
5. **Runnable package**: manifests, streams, pipelines, fields, samples, dashboards/docs — not just a pipeline snippet.

## Query ship gate (blocking)

This skill builds **any** Fleet integration (syslog, files, httpjson, metrics, winlog, …). The gate only bans query shapes that can take down Elasticsearch. It does **not** require a PAM correlation panel, `observer.ip`, or `now-1h` on every dashboard.

**Before** zip, run:

```bash
python3 scripts/production_ship_gate.py /absolute/path/to/packages/<name>
```

- `RESULT: PASS` → you may zip. `RESULT: FAIL` → fix queries; not a deliverable.
- Read `references/kibana-queries.md` before writing ES|QL. `VALUES()` is for small dimensions, never for stashing full events.

| Always fail | Guidance (not a universal number) |
| --- | --- |
| `VALUES(row)` / `CONCAT`+`VALUES`+`MV_EXPAND` / `METADATA _id` | High-volume **event** dashboards: start at last **1 hour**. Metrics / sparse / official copies: 24h is normal. |
| `FROM logs-*` / `metrics-*` / `*` or one FROM of many unrelated streams | Listen inputs (tcp/udp/syslog) only: bind `0.0.0.0`, avoid port 514 if it will collide. |
| `KEEP *` before STATS/joins | Honor an explicit user time window. Do not overwrite a cluster they said is already optimized. |

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

**Load `kibana-dashboards` before any dashboard/Lens work.** Under `kibana/` (details: `references/dashboards.md`):

- At least one **overview** dashboard: volume over time plus top dimensions **this dataset has** (action, status, `source.ip`, `service.name`, …).
- One **Discover search** filtered to `data_stream.dataset: "<package>.<ds>"`.
- Panels bound to the integration data view (`logs-<package>.<ds>-*` or `metrics-…`).
- **Time range:** set `timeRestore: true` and an explicit window. High-volume events → start at `now-1h`. Metrics / low-volume → `now-24h` is fine. See `references/dashboards.md`.
- **Query hard rule:** `references/kibana-queries.md`. Never `VALUES` a full event / `FROM logs-*`. Simple tables stay Kuery. Split unrelated streams into separate searches.
- **Detection rules (SIEM):** only if this is a security deliverable or the user asked. **Load `kibana-alerting-rules` first**, then `references/detection-rules.md`. Ship `docs/detection-rules.ndjson` for **Rules → 导入规则**. ES|QL rules `KEEP` real ECS investigation fields. `note` language matches the dashboards.

Export from a real Kibana when possible. Keep IDs stable. After export, keep a sensible window for **this** data class — do not blindly rewrite every official 24h metrics dashboard to 1h.

### 8) Tests, docs, build **and Fleet zip (required)**

Minimum bar:

```bash
elastic-package check    # format + lint + build when tooling exists
python3 /path/to/this-skill/scripts/production_ship_gate.py packages/<name>
# must print RESULT: PASS — otherwise stop, do not zip
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

**Zip is forbidden until** `python3 scripts/production_ship_gate.py <package-dir>` prints `RESULT: PASS`. A FAIL log means step 8 did not happen.

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
7. Open follow-ups (TLS, multiline, missing fields, extra event types)  
8. **Query ship gate**: paste `RESULT: PASS` stdout. FAIL means do not zip.

## Anti-patterns

- Shipping only a Logstash conf and calling it an “integration” when the user asked for Fleet/integration.  
- Finishing with only a source folder and **no** `<name>-<version>.zip` for Fleet upload.  
- Zipping loose files at the archive root (must be `<name>-<version>/…`).  
- Never hardcode customer/lab IPs in Discover or dashboards; use fields the pipeline actually sets.
- Packaged ES|QL that `VALUES`s concatenated/full events then `MV_EXPAND`, or `FROM logs-*` / many unrelated streams in one panel. See `references/kibana-queries.md`.
- Leaving dashboard `timeFrom` unset. High-volume event UIs should not silently inherit Last 24 hours; metrics UIs may use 24h on purpose.
- Emitting `add_fields` with an empty `fields:` map from optional Handlebars vars (Agent input fails permanently; looks like “syslog not arriving”).  
- For **listen** inputs only: defaulting bind to localhost or port 514 (514 often collides with rsyslog). Use `0.0.0.0` and a high port. Match the vendor’s TCP vs UDP; do not assume TCP.  
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
| `kibana-dashboards` (Elastic skill) | **Required** before creating/updating dashboards or Lens |
| `kibana-alerting-rules` (Elastic skill) | **Required** before creating/updating alerting or SIEM/security rules |
| `references/dashboards.md` | Time windows by data class (high-volume events vs metrics); package `kibana/` layout |
| `references/kibana-queries.md` | ES|QL/Kuery habits; forbidden VALUES-of-event shapes |
| `scripts/production_ship_gate.py` | Pre-zip query-shape scan; FAIL = do not zip |
| `references/detection-rules.md` | SIEM rules: Fleet security-rule vs Rules-import ndjson |

## Quick start for this skill’s operator

1. Obtain samples → Match Report.  
2. If create: scaffold package → input → pipeline → fields → sample_event → kibana → check.  
3. **Run `scripts/production_ship_gate.py`** on the package dir. FAIL → fix query shape; do not zip.  
4. **Build the Fleet `.zip`** only after PASS (`elastic-package build` or `_dev/build_fleet_zip.sh`) and give the user that **one** zip path. SIEM ndjson belongs inside the zip (`docs/detection-rules.ndjson`), not a complete sidecar.  
5. Hand the folder **and zip** to the user; do not stop at a pipeline paste.

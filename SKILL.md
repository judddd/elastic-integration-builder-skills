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
4. **Runnable package**: manifests, streams, pipelines, fields, samples, dashboards/docs — not just a pipeline snippet.

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

### 7) Dashboards and content

Under `kibana/`:

- At least one **overview** dashboard (volume over time, top actions/severities, top source.ip / destination.ip when present).
- One **Discover search** saved object filtered to `data_stream.dataset: "<package>.<ds>"`.
- Optional Lens panels; keep panels bound to the integration’s data view / index pattern `logs-<package>.<ds>-*`.

Export from a real Kibana when possible (`elastic-package export` / Saved Objects). If generating NDJSON by hand, keep IDs stable and references consistent.

### 8) Tests, docs, build

Minimum bar:

```bash
elastic-package check    # format + lint + build when tooling exists
```

Also provide:

- `data_stream/<ds>/_dev/test/pipeline/*.json` — pipeline unit tests from real samples  
- `sample_event.json` — one golden ECS document  
- `_dev/build/docs/README.md` template → build to `docs/README.md`  
- `changelog.yml` entry for the version  

### 9) Deliverable

Output a **complete folder** the user can zip or `elastic-package install`:

```text
<package-name>/
├── manifest.yml
├── changelog.yml
├── docs/
├── kibana/
├── data_stream/<ds>/
│   ├── manifest.yml
│   ├── fields/
│   ├── agent/stream/*.yml.hbs
│   ├── elasticsearch/ingest_pipeline/
│   └── sample_event.json
└── _dev/...
```

Tell the user the install path (Fleet → Integrations → upload zip / `elastic-package install`) and how to point the device/Agent at it.

## Match Report + build log (required output style)

When finishing, always summarize:

1. Match Report (reuse vs create)  
2. Package path on disk  
3. Data stream name(s) and input type(s)  
4. ECS fields populated (bullet list of the important ones)  
5. How to test: simulate pipeline + expected Discover query  
6. Open follow-ups (TLS syslog, multiline, missing fields)

## Anti-patterns

- Shipping only a Logstash conf and calling it an “integration” when the user asked for Fleet/integration.  
- Mapping everything as `keyword` / leaving `source.ip` as text.  
- Dropping `event.original`.  
- Hard-coding a single Chinese firewall vendor as the only path — treat vendor appliances as **one class** of custom syslog/API sources among many (OT, WAF, mail gateway, PAM, etc.).  
- Copying an official package’s copyrighted dashboards wholesale; use as structural reference and build original content.

## References (read on demand)

| File | When |
| --- | --- |
| `references/official-build.md` | Scaffolding, elastic-package commands, doc links |
| `references/package-layout.md` | Exact file tree and manifest snippets |
| `references/ecs-mapping.md` | ECS version selection + field typing rules |
| `references/input-patterns.md` | tcp/udp/logfile/httpjson stream templates |

## Quick start for this skill’s operator

1. Obtain samples → Match Report.  
2. If create: scaffold package → input → pipeline → fields → sample_event → kibana → check.  
3. Hand the folder to the user; do not stop at a pipeline paste.

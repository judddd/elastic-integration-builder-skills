# Agent input patterns

Choose the smallest input that matches how the vendor emits data. Configure streams under `data_stream/<ds>/agent/stream/*.yml.hbs`.

## TCP (common for syslog push)

Use when appliances send newline- or octet-counted syslog to Elastic Agent.

```hbs
host: {{listen_address}}:{{listen_port}}
tags:
{{#each tags as |tag|}}
  - {{tag}}
{{/each}}
{{#if preserve_original_event}}
preserve_original_event: true
{{/if}}
processors:
  - add_locale: ~
```

Manifest vars: `listen_address`, `listen_port`, optional SSL (`ssl` block), `framing`, `max_message_size`.

Document vendor steps: set syslog server = Agent IP, protocol TCP, port, optional template.

## UDP

Same as TCP but connectionless; note message size limits and loss risk. Prefer TCP when the vendor supports it. Some products (e.g. JumpServer) are **UDP-only** — enabling only TCP in Fleet will never receive events.

## Optional policy vars + `add_fields` (required pattern)

Putting optional UI fields (hostname, egress IP, site code, …) into Agent `processors` via Handlebars is common — and a frequent production failure mode.

**Broken** (when both optionals are empty, Filebeat fails the whole input):

```hbs
processors:
  - add_fields:
      target: _conf
      fields:
{{#if observer_hostname}}
        observer_hostname: "{{observer_hostname}}"
{{/if}}
{{#if observer_ip}}
        observer_ip: "{{observer_ip}}"
{{/if}}
```

Symptom in Fleet: Agent **degraded**; component message like  
`missing required field accessing 'filebeat.inputs.0.processors.N.add_fields.fields'`.

**Safe** — always keep a non-empty `fields` map (constant is fine):

```hbs
processors:
  - add_fields:
      target: _conf
      fields:
        package: {{data_stream.dataset}}
{{#if observer_hostname}}
        observer_hostname: "{{observer_hostname}}"
{{/if}}
{{#if observer_ip}}
        observer_ip: "{{observer_ip}}"
{{/if}}
```

Or omit the entire `add_fields` block with `{{#if observer_hostname}}` / `{{#if observer_ip}}` so it is not rendered when unused.

## Listen ports

Defaulting to **514** is convenient but often conflicts with host `rsyslog`, `syslog-ng`, or Elastic EDOT/otel collectors already bound to 514. Prefer a documented high port (e.g. **5514**) for custom integrations, or verify after deploy that Fleet Agent components show the UDP/TCP input **HEALTHY** and `ss -ulnp` shows the Agent process on that port. Vendor `SYSLOG_ADDR` must use the same host:port.

## Syslog input

When the Agent version supports the dedicated `syslog` input, prefer it for RFC3164/RFC5424 parsing before the ingest pipeline.

## Filestream / logfile

For files on a host:

```hbs
paths:
{{#each paths as |path|}}
  - {{path}}
{{/each}}
exclude_files: ['.gz$', '.swp$']
```

## HTTP JSON / CEL

For REST APIs (poll alerts, config dumps):

- Auth vars: API key, user/password, OAuth  
- `interval`, cursor/pagination fields  
- Map JSON paths to ECS in pipeline (`json` processor or already-structured `message`)

## Winlog

For Windows channels; prefer official Windows/Winlogbeat packages unless the channel is proprietary.

## Hybrid with Logstash

If production currently uses Logstash:

1. Still produce the Fleet package (source of truth for pipeline + fields + dashboards).  
2. Optionally mirror processors in Logstash **or** have Logstash index into `logs-<dataset>-*` with `pipeline => "..." ` pointing at the installed ingest pipeline.  
3. Do not maintain two divergent ECS mappings long term.

## Multi-data-stream packages

Split by semantics when formats differ strongly:

- `traffic` — session/flow  
- `threat` — IDS alerts  
- `audit` — admin/config changes  

Each data stream gets its own pipeline and fields.

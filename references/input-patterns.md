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

Same as TCP but connectionless; note message size limits and loss risk. Prefer TCP when the vendor supports it.

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

# Package layout

Target tree for a logs integration named `example_vendor` with data stream `log`:

```text
example_vendor/
├── manifest.yml
├── changelog.yml
├── validation.yml                 # optional docs structure enforcement
├── docs/
│   ├── README.md                  # generated; edit template under _dev/build/docs/
│   └── detection-rules.ndjson     # Rules → 导入规则 (required if SIEM rules exist)
├── img/                           # icon + screenshots
├── kibana/
│   ├── dashboard/
│   │   └── example_vendor-Overview.json
│   ├── search/                    # Discover saved searches (no embedded 24h range)
│   └── security_rule/             # Fleet templates only; not for Rules import
│       └── example-rule.json
├── _dev/
│   └── build/
│       ├── build.yml              # ecs import_mappings
│       └── docs/README.md         # README template
└── data_stream/
    └── log/
        ├── manifest.yml
        ├── fields/
        │   ├── base-fields.yml
        │   ├── ecs.yml            # if not fully imported via build
        │   └── fields.yml         # vendor-specific fields
        ├── agent/
        │   └── stream/
        │       ├── tcp.yml.hbs    # and/or udp, logfile, httpjson…
        │       └── stream.yml.hbs
        ├── elasticsearch/
        │   └── ingest_pipeline/
        │       ├── default.yml
        │       └── pipeline.yml   # optional chained parsers
        ├── sample_event.json
        └── _dev/
            └── test/
                └── pipeline/
                    ├── test-common-config.yml
                    └── test-*.log
```

## Root `manifest.yml` (essentials)

```yaml
format_version: 3.1.3
name: example_vendor
title: "Example Vendor"
version: 0.1.0
description: Collect logs from Example Vendor appliances
type: integration
categories: ["security", "network", "custom"]
conditions:
  kibana:
    version: "^8.14.0 || ^9.0.0"
policy_templates:
  - name: example_vendor
    title: Example Vendor logs
    description: Collect Example Vendor logs
    inputs:
      - type: tcp
        title: Collect logs over TCP
        description: Listen for syslog/TCP messages
owner:
  github: ""
  type: partner
```

## Data stream `manifest.yml` (essentials)

```yaml
title: "Example Vendor logs"
type: logs
streams:
  - input: tcp
    title: TCP
    description: Listen on TCP
    template_path: tcp.yml.hbs
    vars:
      - name: listen_address
        type: text
        title: Listen Address
        default: "0.0.0.0"
        required: true
        show_user: true
      - name: listen_port
        type: integer
        title: Listen Port
        default: 5514
        required: true
        show_user: true
      - name: tags
        type: text
        multi: true
        default: [example_vendor-log]
      - name: preserve_original_event
        type: bool
        default: true
        show_user: true
```

Adjust `input` / `template_path` / vars per `input-patterns.md`.

## `_dev/build/build.yml`

```yaml
dependencies:
  ecs:
    reference: git@v8.11.0   # use a tag aligned to the target Stack
    import_mappings: true
```

Pick the ECS git tag from https://github.com/elastic/ecs/tags to match the destination Elasticsearch/Kibana major.minor—do not hard-code one monorepo’s snapshot.

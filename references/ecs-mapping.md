# ECS mapping guidance

## Why ECS

Fleet Security/Observability apps, detection rules, and dashboards assume ECS field names and types. Wrong types (e.g. `source.ip` as `text`) break visualizations and ML.

## Which ECS version to use

1. **Ask / detect the target Stack** (e.g. ES `8.19.x`, `9.1.x`, `9.5.x`).
2. Align package ECS import and field docs to that generation:
   - `elastic-package` `_dev/build/build.yml` → `dependencies.ecs.reference: git@vX.Y.Z` near the Stack’s bundled ECS.
   - Field definitions (authoritative):  
     https://github.com/elastic/ecs (`generated/ecs/ecs_flat.yml` or `ecs.yml` at the chosen tag)
   - Human docs: https://www.elastic.co/docs/reference/ecs
3. If the cluster version is unknown, run `GET /` (or Kibana status) first, then pick the ECS tag—do not assume a fixed ECS minor.

Core ECS names/types are stable across nearby minors; still verify new fields and `event.*` **allowed** values against the chosen tag.

## Type mapping cheat sheet

When writing `fields.yml` or ingest `convert` processors, use ECS→ES types consistently:

| ECS type | Typical Elasticsearch mapping |
| --- | --- |
| `keyword` / `constant_keyword` | `keyword` (constant_keyword when value is fixed per stream) |
| `match_only_text` / `text` | `match_only_text` (prefer match_only_text for message-like) |
| `wildcard` | `wildcard` |
| `ip` | `ip` |
| `long` / `integer` / `short` / `byte` | matching numeric type |
| `double` / `float` | matching float type |
| `boolean` | `boolean` |
| `date` | `date` |
| `object` / `nested` | `object` / `nested` |
| `geo_point` | `geo_point` |

Never map an ECS `ip` field as `keyword` or `text`.

## `external: ecs` vs the Fleet zip

`external: ecs` does **not** set Elasticsearch types by itself. `elastic-package build` (with `_dev/build/build.yml` `import_mappings: true`) inlines ECS `type:` into the package. A homemade rsync zip (`scripts/build_fleet_zip.sh` or the skill fallback) copies YAML unchanged; Fleet then defaults unresolved fields to **keyword**.

要么 zip 改成 elastic-package build，要么所有 ECS 字段都带明确 type，不能再只写 external: ecs。

When not using `elastic-package build`, write both:

```yaml
- name: source.ip
  type: ip
  external: ecs
- name: destination.ip
  type: ip
  external: ecs
```

Ingest `convert` to `ip` does **not** fix a keyword mapping already installed on the data stream.

## Minimum ECS set for log integrations

Aim to populate when the source allows:

- `@timestamp` (event time, not ingest time alone)
- `event.original` (raw message)
- `event.dataset` = `<package>.<data_stream>`
- `event.module` = `<package>`
- `data_stream.type` / `.dataset` / `.namespace`
- `log.level` or vendor severity mapped into `event.severity` when possible
- Network: `source.ip`, `destination.ip`, `source.port`, `destination.port`, `network.protocol`, `network.direction`
- Identity: `user.name`, `user.id`, `source.user.name`
- Host/observer: `observer.name`, `observer.ip`, `host.name`
- Outcome: `event.outcome` (`success` / `failure` / `unknown`) using **allowed** values only
- Categorization: `event.kind`, `event.category`, `event.type` (arrays of allowed keywords)

## Custom fields

Put non-ECS vendor attributes under a single root object matching the package name:

```yaml
# fields/fields.yml
- name: example_vendor
  type: group
  fields:
    - name: rule_id
      type: keyword
      description: Vendor rule identifier
    - name: session_id
      type: keyword
```

Do not invent new top-level fields that collide with ECS (`type`, `event`, `source`, …).

## Pipeline sketch

```yaml
processors:
  - set:
      field: event.original
      copy_from: message
      ignore_empty_value: true
  # parse → set ECS fields → convert types
  - set:
      field: event.dataset
      value: example_vendor.log
  - set:
      field: event.module
      value: example_vendor
on_failure:
  - append:
      field: error.message
      value: >-
        Processor {{_ingest.on_failure_processor_type}}
        failed: {{_ingest.on_failure_message}}
```

## Validation checklist

- [ ] Every ECS field used exists in the **chosen ECS tag** with matching type  
- [ ] IP fields use ingest `convert`/`ip` and mapping `ip`  
- [ ] Zip is `elastic-package build`, **or** every ECS field in `fields/ecs.yml` has explicit `type:` (never `external: ecs` alone)  
- [ ] `event.category` / `event.type` / `event.outcome` values are in `allowed` lists when present  
- [ ] `sample_event.json` is Discover-friendly and matches mappings  
- [ ] No dynamic mapping surprises for critical fields (explicit fields.yml)

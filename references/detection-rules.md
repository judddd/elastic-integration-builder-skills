# Detection rules for custom Fleet packages

Fleet `kibana/security_rule/*.json` are **saved objects** (`type: security-rule`). They land as integration assets. They do **not** appear under Security → **添加 Elastic 规则** (that catalog is `security_detection_engine` only), and **Rules → 导入规则** rejects them.

## Always ship a detection-engine `.ndjson`

Kibana **Rules → 导入规则** accepts only **ndjson**: one detection-engine rule object per line (the `attributes` body: `name`, `rule_id`, `type`, `query`, …). Not a saved-object wrapper (`id` / `type: security-rule`).

Required artifact: `docs/detection-rules.ndjson` **inside** the Fleet `<name>-<version>.zip` (same path in the package source). Do not ship a second `*-complete.zip` or a sidecar ndjson next to the Fleet zip.

Tell the user: **Integrations → 上传** the one Fleet zip; **Rules → 导入规则** the `docs/detection-rules.ndjson` from that zip. Do not import `kibana/security_rule/*.json`.

When rebuilding a zip, regenerate the ndjson from current `kibana/security_rule/*.json` `attributes`.

## `related_integrations`

Use a **wide** package range (`^0.1.0`, `^1.0.0`), never the current patch (`^0.1.28`). Pinning the patch makes Alerts show “版本不匹配” as soon as Fleet is one version behind.

## ES|QL rules and the Alerts table

ES|QL rules copy **KEEP output columns** onto the alert. Highlighted fields (`investigation_fields`) only render when those names exist **and have values** on the alert.

- After `STATS`, `EVAL`/`RENAME` to **ECS** names and `KEEP` them: `host.name`, `user.name`, `source.ip`, `host.ip`, `destination.ip`, `related.ip`, `related.user`, `event.action`, `event.count`.
- Do **not** KEEP internal join aliases (`join_ip`, `host_key`, `auth_cnt`). Analysts cannot use them, and the Host/User/IP columns stay empty.
- Keep IP columns as `ip` (do not `TO_STRING` then write into `source.ip`); the alerts index maps `source.ip` as `ip` and a string value can be dropped.
- `investigation_fields.field_names` must match the KEEP list.

## Investigation guide language

`note` is the Alerts flyout **调查指南**. Write it in the same language as the dashboards (Chinese for CN packages): what the alert means, what each highlighted field is, Discover queries for source events (ES|QL aggregations often leave 源事件 empty), and false positives. `description` / `false_positives` likewise. Never tell analysts to look at `join_ip`.

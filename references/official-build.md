# Official build path

Primary guide: [Build an integration](https://www.elastic.co/docs/extend/integrations/build-new-integration)

Related pages (follow from that hub as needed):

- [Quick start: Sample integration](https://www.elastic.co/docs/extend/integrations/quick-start)
- [Edit ingest pipelines](https://www.elastic.co/docs/extend/integrations/edit-ingest-pipeline)
- [Finishing touches](https://www.elastic.co/docs/extend/integrations/finishing-touches) (README template, icons, vars UX)
- Ingest processor reference (Elasticsearch docs) for grok/dissect/json/date/convert/pipeline

Tooling: [`elastic-package`](https://github.com/elastic/elastic-package) CLI.

## Command cheat sheet

```bash
# From an empty git workspace dedicated to packages
elastic-package create package
cd <package>
elastic-package create data-stream

# ECS mappings import
mkdir -p _dev/build
# write _dev/build/build.yml with ecs.import_mappings: true

elastic-package format
elastic-package lint
elastic-package build
elastic-package check          # format+lint+build batch

# Fleet UI upload needs the built .zip (elastic-package build writes under build/)
# If elastic-package is missing, use the fallback zip layout:
#   ../build/<name>-<version>.zip with root folder <name>-<version>/
#   Helper: _dev/build_fleet_zip.sh  OR:
#   NAME=... VER=...; STAGE=../build/$NAME-$VER; mkdir -p "$STAGE"
#   rsync -a ./ "$STAGE/"; (cd ../build && zip -r "$NAME-$VER.zip" "$NAME-$VER")

# Optional local stack
elastic-package stack up -v
elastic-package install

# Pipeline tests live under data_stream/<ds>/_dev/test/pipeline/
elastic-package test pipeline -v
```

## Versioning

- Patch `x.y.Z`: bugfix  
- Minor `x.Y.z`: backward-compatible features  
- Major `X.y.z`: breaking field/input changes  

Update `manifest.yml` version **and** top entry in `changelog.yml`.

## ECS version vs Stack version

Pick ECS to match the **destination cluster**:

| Cluster | Guidance |
| --- | --- |
| Elasticsearch 9.x | Use a 9.x-era ECS git tag close to the cluster minor |
| Elasticsearch 8.x | Use 8.x-compatible `git@v8.…` in `build.yml` |
| Unknown | Detect `GET /` (or Kibana status) version first, then choose |

Authoritative schemas: https://github.com/elastic/ecs (`generated/ecs/` at the chosen tag). Core ECS names/types rarely break across nearby minors; still verify new fields and `event.*` allowed values against that tag.

## Finding existing packages

1. Kibana → Integrations (search vendor name, CEF, syslog).  
2. https://github.com/elastic/integrations/tree/main/packages  
3. Docs search for “&lt;vendor&gt; integration”.

When an official package exists, prefer configuration guidance over duplication.

## Upload / install options

- `elastic-package install` against a stack  
- Kibana → Management → Integrations → Upload custom package (zip from `elastic-package build`)  
- Elastic Package Registry / private registry for production rollout

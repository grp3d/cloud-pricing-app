# Edge-case manifests (018-app-cloud-deployment, T007)

Hand-made manifests for `tests/unit/test_manifest.py`, each a complete document for snapshot
`2026-10-05` in the shape of `tests/fixtures/contracts/manifest.schema.json`. Each one breaks
exactly one rule from data-model.md §3: a non-`succeeded` status, a bad file path (`..`,
absolute, wrong date, wrong region), an unsupported major or table schema version. The
`minor_bump_extra_field` one must be *accepted* (a 1.x minor bump only adds optional fields).

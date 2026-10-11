# Peek MVP Registry (unsigned)

Central recipe registry. **MVP: unsigned** — `registry.json` has no
`signing_keys` and publish emits no `index.json.sig`.
Do not use for real users until `TODO(signing)` is done.

## Layout

- `registry.json` — id, `base_url`, policy. Update `base_url`/`repo` after creating the GitHub repo.
- `recipes/<id>/recipe.yaml` — source of truth, folder name == `id`.
- `scripts/validate_v2.py` — `format: 2` checks (required keys, folder == id,
  version, params, fetch, rows/fields/key/limit, title/columns/link rules).
- `scripts/build_index.py` — emits `dist/index.json` + `dist/r/<id>/<version>.json`.

## Local use

```
pip install pyyaml
python3 scripts/validate_v2.py
python3 scripts/build_index.py --out dist
python3 -m json.tool dist/index.json
```

Serve `dist/` (or push to `main` — `publish.yml` deploys it to GitHub Pages).

## Client

Point the app at `<base_url>/index.json`. Cache bundles by SHA-256.
`TODO(signing)`: verify `index.json.sig` with the embedded key before trusting the index.

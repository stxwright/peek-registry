# Contributing (MVP)

1. One recipe per folder: `recipes/<id>/recipe.yaml`, folder name == `id`.
2. New recipe: `version: 1`. Update: `version` = previous + 1, `id` unchanged.
3. Before pushing:
   ```
    python3 scripts/validate_v2.py
   python3 scripts/build_index.py --out dist
   ```
4. Push to `main` — CI re-validates, rebuilds, and publishes to Pages.

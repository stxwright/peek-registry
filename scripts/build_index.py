"""Build the published static index from recipes/*/recipe.yaml.

Usage: python3 scripts/build_index.py [--out dist]
Reads registry.json for the registry id, writes:
  <out>/index.json
  <out>/r/<id>/<version>.json   (canonical bundle per recipe)

Canonical form: JSON with sorted keys and no insignificant whitespace.
Index sequence: current Unix time (anti-rollback marker for clients).

TODO(signing): emit index.json.sig (Ed25519 detached) once keys exist.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


def canonical(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    with open(root / "registry.json", "r", encoding="utf-8") as f:
        registry = json.load(f)

    out = root / args.out
    recipe_files = sorted((root / "recipes").glob("*/recipe.yaml"))
    if not recipe_files:
        print("No recipes found in recipes/")
        return 1

    entries = []
    for rpath in recipe_files:
        with open(rpath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rid = data["id"]
        if rid != rpath.parent.name:
            print(f"FAIL: id {rid!r} != folder {rpath.parent.name!r}")
            return 1
        version = data["version"]
        bundle_bytes = canonical(data) + b"\n"
        digest = hashlib.sha256(bundle_bytes).hexdigest()
        rel = f"r/{rid}/{version}.json"
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bundle_bytes)
        entries.append({
            "id": rid,
            "version": version,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "listed": True,
            "bundle": {"path": rel, "sha256": digest, "size": len(bundle_bytes)},
        })

    entries.sort(key=lambda e: e["id"])
    now = int(time.time())
    index = {
        "format": 1,
        "registry_id": registry["id"],
        "generated_at": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sequence": now,
        "recipes": entries,
    }
    (out / "index.json").write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} recipes to {out}/index.json (sequence {now})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

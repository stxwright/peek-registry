"""Build the published static index from recipes/*/recipe.yaml.

Usage: python3 scripts/build_index.py [--out dist]
Reads registry.json for the registry id, writes:
  <out>/index.json
  <out>/r/<id>/<version>.json   (canonical bundle per recipe)

Canonical form: JSON with sorted keys and no insignificant whitespace.
Index sequence: newest source-commit timestamp over recipes/ + registry.json
(anti-rollback marker bound to content, not the build clock), wall clock
only as fallback outside a git checkout. dist/ is a pure emitter artifact:
r/ is wiped at the start so orphan and superseded bundles never survive.

TODO(signing): emit index.json.sig (Ed25519 detached) once keys exist.
"""
import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


def canonical(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def source_sequence(root: Path) -> int:
    """Newest commit timestamp over the published sources.

    A wall clock lets a rebuilt old commit look fresh and defeat client
    anti-rollback. Commit time only moves when content moves, so stale
    content can never outrank what clients hold.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%ct",
             "--", "recipes", "registry.json"],
            capture_output=True, text=True, timeout=15, check=False)
        ts = int((out.stdout or "").strip())
        if ts > 0:
            return ts
    except Exception:
        pass
    print("note: git source timestamp unavailable, falling back to wall clock")
    return int(time.time())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    with open(root / "registry.json", "r", encoding="utf-8") as f:
        registry = json.load(f)

    out = root / args.out
    # dist/ is a pure build artifact: wipe r/ so orphan bundles (deleted
    # recipes) and superseded versions never survive a rebuild.
    rdir = out / "r"
    if rdir.is_dir():
        shutil.rmtree(rdir)
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
    seq = source_sequence(root)
    index = {
        "format": 1,
        "registry_id": registry["id"],
        "generated_at": datetime.fromtimestamp(seq, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sequence": seq,
        "recipes": entries,
    }
    (out / "index.json").write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} recipes to {out}/index.json (sequence {seq})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

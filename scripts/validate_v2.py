"""Validate v2 recipes (hand-writable minimal format).

Usage: python3 scripts/validate_v2.py
Exit 0 = all pass, 1 = failures.

v2 recipe shape:
  format: 2
  id: <reverse-domain>            # == folder name
  version: <int >= 1>
  name: <= 60 chars
  description: <= 280 chars
  params: {key: default}          # optional, plain strings
  fetch:
    url: "https://.../{param}/"  # placeholders only after host
    allow: [hosts]               # >= 1, https only
    every: <seconds>             # default 900, >= 300 (>= 900 with render: js)
    render: static | js          # default static
    wait: "<css>"                # render: js only
  rows: "<css>"                  # optional; absent = single item (document)
  fields: {name: "<css>" | {sel, attr}}   # >= 1; {sel} string or
                                          # {sel, attr?, scope?}; scope is
                                          # row (default, relative to the item)
                                          # or page (evaluated once against the
                                          # document, e.g. a stop name in the
                                          # page header; merged into every row
                                          # so titles resolve from row zero)
  key: <field>                   # required iff rows present; empty key drops row
  limit: <1..100>                # default 10, rows only
  title: "<template>"            # optional
  columns: [field, ...]          # required, 1..10: aligned table
                                  # (single-item recipes transpose to label/value rows)
  link: "https://..."            # optional, host must be in allow
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9-]+)+$")
REF_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def err(msg):
    return msg


def check_selector(sel, where, errors):
    if not isinstance(sel, str) or not sel.strip():
        errors.append(f"{where}: selector must be a non-empty string")
        return
    if len(sel) > 500:
        errors.append(f"{where}: selector too long (> 500)")


def validate(data, folder, known_versions):
    errors = []
    if data.get("format") != 2:
        return [f"format must be 2, got {data.get('format')!r}"]
    rid = data.get("id", "")
    if not isinstance(rid, str) or not ID_RE.match(rid):
        errors.append(f"id {rid!r} must match reverse-domain pattern")
    if rid != folder:
        errors.append(f"id {rid!r} != folder {folder!r}")
    ver = data.get("version")
    if not isinstance(ver, int) or ver < 1:
        errors.append(f"version must be an integer >= 1, got {ver!r}")
    elif folder in known_versions and ver <= known_versions[folder]:
        pass  # monotonicity against git history is a review concern, not local
    name = data.get("name", "")
    if not isinstance(name, str) or not (1 <= len(name) <= 60):
        errors.append("name must be 1..60 chars")
    desc = data.get("description", "")
    if not isinstance(desc, str) or not (1 <= len(desc) <= 280):
        errors.append("description must be 1..280 chars")

    params = data.get("params", {})
    if not isinstance(params, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in params.items()
    ):
        errors.append("params must be a map of string -> string")
        params = {}

    fetch = data.get("fetch")
    if not isinstance(fetch, dict):
        errors.append("fetch is required")
        fetch = {}
    url = fetch.get("url", "")
    allow = fetch.get("allow", [])
    if not isinstance(url, str) or not url.startswith("https://"):
        errors.append("fetch.url must be an https URL")
    else:
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            host = ""
        if "{" in host:
            errors.append("fetch.url host must be literal (placeholders only after host)")
        if isinstance(allow, list) and host not in allow:
            errors.append(f"fetch.url host {host!r} must be in fetch.allow")
    if not isinstance(allow, list) or not allow or not all(
        isinstance(h, str) and h and "{" not in h for h in allow
    ):
        errors.append("fetch.allow must list >= 1 literal hostnames")
    every = fetch.get("every", 900)
    if not isinstance(every, int) or every < 300:
        errors.append(f"fetch.every must be >= 300, got {every!r}")
    render = fetch.get("render", "static")
    if render not in ("static", "js"):
        errors.append(f"fetch.render must be static|js, got {render!r}")
    if render == "js" and every < 900:
        errors.append("fetch.every must be >= 900 with render: js")
    if "wait" in fetch and render != "js":
        errors.append("fetch.wait only applies to render: js")
    if "wait" in fetch:
        check_selector(fetch["wait"], "fetch.wait", errors)

    rows = data.get("rows")
    group_values: set[str] = set()
    if isinstance(rows, str) or rows is None:
        if rows is not None:
            check_selector(rows, "rows", errors)
    elif isinstance(rows, list):
        if not (1 <= len(rows) <= 10):
            errors.append("rows list must hold 1..10 groups")
        else:
            for i, group in enumerate(rows):
                where = f"rows[{i}]"
                if not isinstance(group, dict):
                    errors.append(f"{where} must be a mapping")
                    continue
                sel = group.get("sel")
                if not isinstance(sel, str):
                    errors.append(f"{where}.sel is required")
                else:
                    check_selector(sel, f"{where}.sel", errors)
                values = group.get("values", {})
                if not isinstance(values, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) for k, v in values.items()
                ):
                    errors.append(f"{where}.values must be a map of string -> string")
                else:
                    group_values.update(values.keys())
                for gk in group:
                    if gk not in ("sel", "values"):
                        errors.append(f"{where}: unknown key {gk!r}")
    else:
        errors.append("rows must be a selector string or a list of groups")

    fields = data.get("fields")
    if not isinstance(fields, dict) or not fields:
        errors.append("fields must be a non-empty map")
        fields = {}
    for fname, fdef in fields.items():
        if isinstance(fdef, str):
            check_selector(fdef, f"fields.{fname}", errors)
        elif isinstance(fdef, dict) and isinstance(fdef.get("sel"), str):
            check_selector(fdef["sel"], f"fields.{fname}.sel", errors)
            if "attr" in fdef and not isinstance(fdef["attr"], str):
                errors.append(f"fields.{fname}.attr must be a string")
            if "scope" in fdef and fdef["scope"] not in ("row", "page"):
                errors.append(f"fields.{fname}.scope must be row|page")
            for fk in fdef:
                if fk not in ("sel", "attr", "scope"):
                    errors.append(f"fields.{fname}: unknown key {fk!r}")
        else:
            errors.append(f"fields.{fname} must be a selector string or {{sel, attr, scope}}")

    def is_row_field(fdef):
        return not (isinstance(fdef, dict) and fdef.get("scope") == "page")

    key = data.get("key")
    if rows is not None:
        if not isinstance(key, str) or key not in fields or not is_row_field(fields[key]):
            errors.append("key is required with rows and must name a row-scoped field")
    elif key is not None and key not in fields:
        errors.append("key must name a field")

    limit = data.get("limit", 10)
    if not isinstance(limit, int) or not (1 <= limit <= 100):
        errors.append(f"limit must be 1..100, got {limit!r}")

    columns = data.get("columns")
    if not isinstance(columns, list) or not (1 <= len(columns) <= 10) or not all(
        isinstance(c, str) and (
            (c in fields and is_row_field(fields[c])) or c in group_values)
        for c in columns
    ):
        errors.append("columns is required and must list 1..10 row-scoped field or group-value names")
    title = data.get("title", "")
    if title is not None and not isinstance(title, str):
        errors.append("title must be a string")

    # Every {ref} must resolve to a param, field, or group value.
    known = set(params) | set(fields) | group_values
    for label, tmpl in [("title", title or "")]:
        for ref in REF_RE.findall(tmpl):
            if ref not in known:
                errors.append(f"{label}: {{{ref}}} is not a param, field, or group value")

    link = data.get("link")
    if link is not None:
        if not isinstance(link, str) or not link.startswith("https://"):
            errors.append("link must be an https URL")
        else:
            try:
                lhost = urlparse(link).hostname or ""
            except Exception:
                lhost = ""
            if isinstance(allow, list) and lhost not in allow:
                errors.append(f"link host {lhost!r} must be in fetch.allow")
        for ref in REF_RE.findall(link):
            if ref not in set(params):
                errors.append(f"link: {{{ref}}} must be a param")

    # No unknown top-level keys (strict, like v1).
    allowed_top = {"format", "id", "version", "name", "description", "params",
                    "fetch", "rows", "fields", "key", "limit", "title", "columns", "link"}
    for k in data:
        if k not in allowed_top:
            errors.append(f"unknown key: {k!r}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    recipes_dir = root / "recipes"
    recipe_files = sorted(recipes_dir.glob("*/recipe.yaml"))
    if not recipe_files:
        print(f"No recipes found in {recipes_dir}")
        return 1
    ok = True
    for rpath in recipe_files:
        rel = rpath.relative_to(root)
        with open(rpath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            print(f"FAIL: {rel}\n  - must be a mapping")
            ok = False
            continue
        if data.get("format", 1) != 2:
            print(f"SKIP: {rel} (not format 2)")
            continue
        errors = validate(data, rpath.parent.name, {})
        if errors:
            ok = False
            print(f"FAIL: {rel}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"PASS: {rel}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

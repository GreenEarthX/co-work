#!/usr/bin/env python
"""
Import canvas documents from the Supabase `plant-data` bucket into the backend.

Increment 3 of `docs/supabase-cutover-endpoints.md`. Measured 2026-09-20 the
bucket holds 1,476 objects / 90 MB:

    canvas (live)        64     users/{owner}/{slug}.json
    canvas versions   1,193     versions/users/{owner}/{slug}/{stamp}.json
    site infra            4     users/{owner}/{slug}.infrastructure.json
    custom library        6     users/{owner}/custom-library.json
    root / legacy       209     {slug}.json at the bucket root — unscoped seeds
                                from before per-user paths; owned by nobody

OWNERSHIP IS AN INPUT, NOT AN INFERENCE

The paths embed the same ad-hoc ids as the `plants` table (`admin-001`,
`user-003`, …), none of which is an `auth_users.user_id`. Pass the same
`--map` / `--drop` arguments used for `scripts/import_plants.py`; an unmapped
owner stops the run before anything is written.

HISTORY IS CAPPED ON THE WAY IN

Only the newest MAX_VERSIONS_KEPT snapshots per document are fetched — the
retention rule the app already applies. Migrating all 1,193 would download
~90 MB to delete most of it on the first prune.

USAGE

    ./venv/bin/python scripts/import_canvas_blobs.py --dry-run \\
        --map admin-001=admin_greenearthx_com \\
        --map user-003=t-marwenc_greenearthx_com \\
        --map etfuels-thierry=thierry_groell_etfuels_com \\
        --drop user-001 --drop user-002 --drop tmp-diag \\
        --drop b05dcc50-56da-442c-b845-658720ff3c9f
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import canvas_store  # noqa: E402
from app.core.config import settings  # noqa: E402

CLIENT = Path(__file__).resolve().parents[2] / "frontend/src/lib/backendClient.ts"
BUCKET = "plant-data"


def _credentials() -> tuple[str, str]:
    src = CLIENT.read_text(encoding="utf-8")
    url = re.search(r'FALLBACK_BACKEND_URL\s*=\s*"([^"]+)"', src).group(1)
    key = re.search(r'FALLBACK_PUBLISHABLE_KEY\s*=\s*\n?\s*"([^"]+)"', src).group(1)
    return url, key


def _list(url: str, key: str, prefix: str) -> list[dict]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}",
               "Content-Type": "application/json"}
    out, offset = [], 0
    while True:
        req = urllib.request.Request(
            f"{url}/storage/v1/object/list/{BUCKET}",
            data=json.dumps({"prefix": prefix, "limit": 100, "offset": offset}).encode(),
            headers=headers)
        batch = json.load(urllib.request.urlopen(req, timeout=30))
        out += batch
        if len(batch) < 100:
            return out
        offset += 100


def _walk(url: str, key: str, prefix: str = "", depth: int = 0) -> list[str]:
    found: list[str] = []
    for entry in _list(url, key, prefix):
        path = f"{prefix}{entry['name']}" if prefix.endswith("/") or not prefix \
            else f"{prefix}/{entry['name']}"
        if entry.get("id") is None and depth < 4:
            found += _walk(url, key, path + "/", depth + 1)
        elif entry.get("id"):
            found.append(path)
    return found


def _fetch(url: str, key: str, path: str) -> bytes:
    req = urllib.request.Request(
        f"{url}/storage/v1/object/{BUCKET}/{urllib.parse.quote(path)}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _classify(path: str) -> tuple[str, str, str, str] | None:
    """(owner, kind, slug, version_id) or None for an object with no owner."""
    parts = path.split("/")
    if path.startswith("versions/users/") and len(parts) == 5:
        _, _, owner, slug, stamp = parts
        return owner, "canvas", slug, stamp.removesuffix(".json")
    if path.startswith("users/") and len(parts) == 3:
        owner, name = parts[1], parts[2]
        if name == "custom-library.json":
            return owner, "library", "", ""
        if name.endswith(".infrastructure.json"):
            return owner, "site", name.removesuffix(".infrastructure.json"), ""
        if name.endswith(".json"):
            return owner, "canvas", name.removesuffix(".json"), ""
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--map", action="append", default=[], metavar="OLD=NEW")
    p.add_argument("--drop", action="append", default=[], metavar="OLD")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    mapping: dict[str, str] = {}
    for pair in args.map:
        old, _, new = pair.partition("=")
        if not old or not new:
            p.error(f"--map expects OLD=NEW, got {pair!r}")
        mapping[old] = new
    dropped = set(args.drop)

    url, key = _credentials()
    print("listing the bucket…")
    paths = _walk(url, key)
    classified = [(path, _classify(path)) for path in paths]
    unowned = [path for path, c in classified if c is None]
    owned = [(path, c) for path, c in classified if c is not None]

    owners = collections.Counter(c[0] for _, c in owned)
    print(f"{len(paths)} objects: {len(owned)} owned, {len(unowned)} unscoped "
          f"(bucket-root legacy seeds — no owner, never imported)")

    unresolved = [o for o in owners if o not in mapping and o not in dropped]
    if unresolved:
        print("\nREFUSING TO IMPORT — owner ids neither mapped nor dropped:")
        for owner in sorted(unresolved, key=lambda o: -owners[o]):
            print(f"  {owner!r:<44} {owners[owner]:>4} objects")
        return 2

    accounts: set[str] = set()
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    try:
        accounts = {r[0] for r in conn.execute("SELECT user_id FROM auth_users")}
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    unknown = {n for n in mapping.values() if accounts and n not in accounts}
    if unknown:
        print(f"\nREFUSING TO IMPORT — no such account(s): {sorted(unknown)}")
        return 2

    # Group so history can be capped per document before anything is fetched.
    live: list[tuple[str, tuple]] = []
    versions: dict[tuple[str, str], list[tuple[str, tuple]]] = collections.defaultdict(list)
    for path, c in owned:
        owner, kind, slug, version_id = c
        if owner in dropped:
            continue
        if version_id:
            versions[(mapping[owner], slug)].append((path, c))
        else:
            live.append((path, c))

    keep = canvas_store.MAX_VERSIONS_KEPT
    planned_versions: list[tuple[str, tuple]] = []
    for key_, items in versions.items():
        items.sort(key=lambda it: it[1][3], reverse=True)   # newest stamp first
        planned_versions += items[:keep]

    print(f"\nplan: {len(live)} live documents + {len(planned_versions)} snapshots "
          f"(capped at {keep} per document, from {sum(len(v) for v in versions.values())})")
    for old, new in sorted(mapping.items()):
        print(f"  {old:<44} → {new}")
    for old in sorted(dropped):
        print(f"  {old:<44} → (dropped)")
    if args.dry_run:
        print("dry run — nothing fetched or written")
        return 0

    canvas_store.init_db()
    written = failed = 0
    for path, (owner, kind, slug, version_id) in live + planned_versions:
        try:
            content = _fetch(url, key, path)
            canvas_store.put_blob(mapping[owner], kind, slug, content,
                                  version_id=version_id)
            written += 1
            if written % 50 == 0:
                print(f"  {written} written…")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ! {path}: {exc}")

    print(f"\n{written} objects imported, {failed} failed")
    for new in sorted(set(mapping.values())):
        print(f"  {new}: {canvas_store.count_for_owner(new)} documents")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a reproducible MPV official-generator-derived corpus.

The DIKU distribution does not publish the paper's original static archive;
it publishes a generator and solver instead.  This script therefore produces
an explicitly named derived corpus.  It never labels the output as the
original MPV archive.  The generated JSON keeps the exact generator inputs,
source hashes and seed rule needed for an independent regeneration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "benchmarks" / "data" / "public" / "mpv_official_generator_derived"
SOURCE_URLS = {
    "3dbpp.c": "https://di.ku.dk/~pisinger/new3dbpp/3dbpp.c",
    "test3dbpp.c": "https://di.ku.dk/~pisinger/new3dbpp/test3dbpp.c",
    "readme.3dbpp": "https://di.ku.dk/~pisinger/new3dbpp/readme.3dbpp",
}
# Hashes observed from the official DIKU files on 2026-09-01.
SOURCE_SHA256 = {
    "3dbpp.c": "eb67adddba4c201a42654be04cd9b2316a8e2825c398d79531d0d9884833c0c3",
    "test3dbpp.c": "f7fbe2238b54862b4bafaa3d7f0e9120072f1730860b534d7f17f566da2b82ed",
    "readme.3dbpp": "96d061562afa161629aa52370abe0d8d4f1c0e5b4dc6561e64a340cd3e7251ec",
}

WRAPPER = r'''
#define binpack3d mpv_stub_binpack3d
#define main mpv_original_main
#include "test3dbpp.c"
#undef main
#undef binpack3d

void mpv_stub_binpack3d(int n, int W, int H, int D,
                        int *w, int *h, int *d,
                        int *x, int *y, int *z, int *bno,
                        int *lb, int *ub,
                        int nodelimit, int iterlimit, int timelimit,
                        int *nodeused, int *iterused, int *timeused,
                        int packingtype) {
  (void)n; (void)W; (void)H; (void)D; (void)w; (void)h; (void)d;
  (void)x; (void)y; (void)z; (void)bno; (void)lb; (void)ub;
  (void)nodelimit; (void)iterlimit; (void)timelimit;
  (void)nodeused; (void)iterused; (void)timeused; (void)packingtype;
}

int main(int argc, char **argv) {
  if (argc != 5) return 2;
  int n = atoi(argv[1]);
  int bindim = atoi(argv[2]);
  int type = atoi(argv[3]);
  long seed = atol(argv[4]);
  box items[MAXBOXES];
  itype W, H, D;
  srand48x(seed);
  maketest(items, items + n - 1, &W, &H, &D, bindim, type);
  printf("%d %d %d %d\n", n, W, H, D);
  for (int i = 0; i < n; ++i)
    printf("%d %d %d\n", items[i].w, items[i].h, items[i].d);
  return 0;
}
'''


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_sources(source_dir: Path, offline: bool) -> dict[str, str]:
    source_dir.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCE_URLS.items():
        path = source_dir / name
        if not path.exists():
            if offline:
                raise FileNotFoundError(f"offline source is missing: {path}")
            with urllib.request.urlopen(url, timeout=30) as response:
                path.write_bytes(response.read())
        actual = sha256(path)
        expected = SOURCE_SHA256[name]
        if actual != expected:
            raise ValueError(f"source hash mismatch for {name}: {actual} != {expected}")
    return {name: sha256(source_dir / name) for name in SOURCE_URLS}


def compile_generator(source_dir: Path, build_dir: Path) -> Path:
    wrapper = build_dir / "mpv_generator_wrapper.c"
    wrapper.write_text(WRAPPER, encoding="ascii")
    binary = build_dir / "mpv_generator_probe"
    subprocess.run(
        ["gcc", "-std=c99", "-O2", "-I", str(source_dir), str(wrapper), "-lm", "-o", str(binary)],
        check=True,
        capture_output=True,
        text=True,
    )
    return binary


def run_generator(binary: Path, n: int, bindim: int, generator_type: int, seed: int) -> tuple[tuple[int, int, int], list[tuple[int, int, int]]]:
    completed = subprocess.run(
        [str(binary), str(n), str(bindim), str(generator_type), str(seed)],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = completed.stdout.splitlines()
    if len(rows) != n + 1:
        raise ValueError(f"generator returned {len(rows) - 1} items, expected {n}")
    header = tuple(int(value) for value in rows[0].split())
    if len(header) != 4 or header[0] != n:
        raise ValueError(f"invalid generator header: {rows[0]!r}")
    container = (header[1], header[2], header[3])
    items = [tuple(int(value) for value in row.split()) for row in rows[1:]]
    if any(len(item) != 3 or any(value < 1 for value in item) for item in items):
        raise ValueError("generator produced a non-positive or malformed item")
    if any(item[axis] > container[axis] for item in items for axis in range(3)):
        raise ValueError("generator produced an item larger than its bin")
    return container, items


def canonical_payload(
    instance_id: str,
    n: int,
    bindim: int,
    generator_type: int,
    replicate: int,
    seed: int,
    container: tuple[int, int, int],
    items: list[tuple[int, int, int]],
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "corpus": "MPV_OFFICIAL_GENERATOR_DERIVED",
        "instance_id": instance_id,
        "problem": "fixed-orientation identical-bin 3D bin packing",
        "container": list(container),
        "items": [
            {"id": f"item-{index:03d}", "size": list(size), "orientation": "fixed"}
            for index, size in enumerate(items)
        ],
        "generator": {
            "source_urls": SOURCE_URLS,
            "source_sha256": source_hashes,
            "license_note": "official DIKU code states research and academic use only",
            "n": n,
            "bindim": bindim,
            "type": generator_type,
            "replicate": replicate,
            "seed": seed,
            "seed_rule": "official main uses srand(v+n), with v=1..10; wrapper reproduces seed=n+replicate",
            "packingtype": "not used by generator probe",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--n", type=int, action="append", dest="sizes")
    parser.add_argument("--type", type=int, action="append", dest="types")
    parser.add_argument("--bindim", type=int, default=100)
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    sizes = args.sizes or [30, 60, 90]
    types = args.types or [1, 6, 7, 8, 9]
    if args.bindim < 1 or args.replicates < 1 or any(n < 1 or n > 200 for n in sizes):
        raise SystemExit("bindim/replicates must be positive and n must be in 1..200")
    if any(generator_type < 1 or generator_type > 9 for generator_type in types):
        raise SystemExit("generator type must be in 1..9")
    source_dir = args.source_dir or Path(tempfile.mkdtemp(prefix="mpv-official-source-"))
    source_hashes = fetch_sources(source_dir, args.offline)
    with tempfile.TemporaryDirectory(prefix="mpv-official-build-") as build_name:
        binary = compile_generator(source_dir, Path(build_name))
        args.output.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "corpus": "MPV_OFFICIAL_GENERATOR_DERIVED",
            "source_urls": SOURCE_URLS,
            "source_sha256": source_hashes,
            "generator_binary_sha256": sha256(binary),
            "license_note": "official DIKU code states research and academic use only",
            "seed_rule": "seed=n+replicate, matching official v+n for v=1..10",
            "parameters": {"sizes": sizes, "types": types, "bindim": args.bindim, "replicates": args.replicates},
            "instances": [],
        }
        for n in sizes:
            for generator_type in types:
                for replicate in range(1, args.replicates + 1):
                    seed = n + replicate
                    container, items = run_generator(binary, n, args.bindim, generator_type, seed)
                    instance_id = f"MPV-GEN-T{generator_type}-N{n}-R{replicate:02d}"
                    payload = canonical_payload(instance_id, n, args.bindim, generator_type, replicate, seed, container, items, source_hashes)
                    path = args.output / f"{instance_id}.json"
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    manifest["instances"].append({"instance_id": instance_id, "path": path.name, "sha256": sha256(path), "item_count": n, "container": list(container), "type": generator_type, "seed": seed})
        manifest["instances"].sort(key=lambda row: row["instance_id"])
        manifest["corpus_sha256"] = hashlib.sha256(("\n".join(row["sha256"] for row in manifest["instances"]) + "\n").encode("ascii")).hexdigest()
        (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    print(f"generated={len(manifest['instances'])} corpus_sha256={manifest['corpus_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

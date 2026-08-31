from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = RAW / "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    files = []
    for path in sorted(RAW.rglob("*")):
        if not path.is_file() or path == OUT:
            continue
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    OUT.write_text(json.dumps({"schema_version": 1, "files": files}, indent=2) + "\n")
    print(f"manifest: {len(files)} files -> {OUT}")


if __name__ == "__main__":
    main()

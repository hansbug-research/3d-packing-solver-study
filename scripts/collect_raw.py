from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"


def main() -> None:
    RAW.mkdir(exist_ok=True)
    copied = 0
    for source in sorted((ROOT / "results").glob("*.json")):
        shutil.copy2(source, RAW / source.name)
        copied += 1
    public = ROOT / "results" / "public"
    for source in sorted(public.glob("*.json")):
        shutil.copy2(source, RAW / source.name)
        copied += 1

    # Keep every experiment-side artifact: stdout/stderr, resource reports,
    # certificates and debug files are part of the reproducibility record.
    source_raw = ROOT / "results" / "raw"
    destination_raw = RAW / "experiments"
    if source_raw.is_dir():
        for source in sorted(path for path in source_raw.rglob("*") if path.is_file()):
            destination = destination_raw / source.relative_to(source_raw)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
        print(f"copied {copied} result/raw files")
    else:
        print(f"copied {copied} JSON result files; no results/raw directory found")


if __name__ == "__main__":
    main()

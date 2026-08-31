from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model import (
    RESULTS_DIR,
    build_plan_rows,
    canonical_json,
    coverage_csv,
    load_catalogs,
    plan_jsonl,
    plan_summary,
    validate_plan_rows,
)


def generated_files() -> dict[Path, str]:
    suites, implementations = load_catalogs()
    rows = build_plan_rows(suites, implementations)
    validate_plan_rows(rows, len(suites["suites"]), len(implementations["implementations"]))
    return {
        RESULTS_DIR / "suite-implementation-plan.jsonl": plan_jsonl(rows),
        RESULTS_DIR / "coverage.csv": coverage_csv(rows),
        RESULTS_DIR / "plan-summary.json": canonical_json(plan_summary(rows, suites, implementations)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic B01-B32 x implementation execution plan")
    parser.add_argument("--check", action="store_true", help="fail if generated artifacts are missing or stale")
    args = parser.parse_args()

    files = generated_files()
    if args.check:
        stale = [path for path, expected in files.items() if not path.exists() or path.read_text() != expected]
        if stale:
            for path in stale:
                print(f"PLAN_STALE: {path}", file=sys.stderr)
            return 1
        print(f"PLAN_OK: {len(files)} generated artifacts are current")
        return 0

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
        print(path.relative_to(RESULTS_DIR.parents[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

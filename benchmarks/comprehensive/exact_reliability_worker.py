from __future__ import annotations

"""Process-boundary worker for exact B29 fault tests."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "campaign"))
from exact_suite import Bin, Case, Item, _solve_mip, rotations, solve_cp_sat  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.input.read_text())
    items = tuple(Item(item["id"], tuple(int(x) for x in item["size"]), 1,
                       rotations(tuple(int(x) for x in item["size"]))) for item in raw["items"])
    bins = tuple(Bin(item["id"], tuple(int(x) for x in item["size"]), int(item["max_weight"]),
                   int(item["cost"])) for item in raw["bins"])
    case = Case("reliability-fault", items, bins, "OPTIMAL", None, "B29 process boundary")
    if args.backend == "cp_sat":
        result = solve_cp_sat(case, 60.0)
    else:
        result = _solve_mip(case, args.backend, 60.0)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

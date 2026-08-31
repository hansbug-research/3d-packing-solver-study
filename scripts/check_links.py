"""Check relative Markdown links and image targets without requiring network access."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".cache", ".venv", "node_modules"}
TARGET = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
        and path.relative_to(ROOT).parts[:2] != ("sources", "snapshots")
    )


def relative_targets(path: Path) -> list[str]:
    targets: list[str] = []
    in_fence = False
    fence = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            continue
        if in_fence:
            continue
        for raw_target in TARGET.findall(line):
            target = raw_target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#"):
                continue
            targets.append(parsed.path)
    return targets


def main() -> int:
    failures: list[str] = []
    for source in markdown_files():
        for target in relative_targets(source):
            if not target:
                continue
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                failures.append(f"{source.relative_to(ROOT)} -> {target} (escapes repository)")
                continue
            if not resolved.exists():
                failures.append(f"{source.relative_to(ROOT)} -> {target} (missing)")
    if failures:
        for failure in failures:
            print(f"LINKS_FAIL: {failure}")
        return 1
    print("LINKS_OK: all relative Markdown links and images resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
